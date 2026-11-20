#!/usr/bin/env python3
"""aarch64 build on an x86_64 host (qemu-user binfmt): run Chromium's x86_64 clang/lld natively.

Everything in an aarch64 flatpak build runs under qemu, which makes compiling Chromium 5-10x slower. The kernel
still runs x86_64 ELF files natively inside the aarch64 sandbox, so this swaps the LLVM binaries for the x86_64
build of the same LLVM revision (Chromium ships both from one commit):

- _build_tools/llvm      the aarch64 toolchain tree (lib/clang/*/lib has the aarch64 runtimes), bin/ replaced
- _build_tools/llvm-x64  Chromium's x86_64 prebuilt of the same revision
- _build_tools/x86libs   the few x86_64 glibc/zlib/libgcc_s libraries those binaries need, copied from the host's
                         x86_64 org.freedesktop.Sdk before the build

Each x86_64 binary gets its PT_INTERP rewritten to <builddir>/x/ld.so (same length or shorter than
/lib64/ld-linux-x86-64.so.2) and finds the other libraries through its RUNPATH ($ORIGIN/../lib). clang.cfg and
clang++.cfg make aarch64-unknown-linux-gnu the default target, for callers that don't pass --target (rustc's
linker calls, GN's host toolchain, which is also arm64 here).

Only for the cross build on nor-pc (homelab configs/nor-pc/ungoogled-chromium-hdr/build-arm64.sh). A native
aarch64 build skips it: x86libs/ then only has its README.
"""
import os
import shutil
import struct
import sys

ROOT = os.getcwd()
LLVM = os.path.join(ROOT, "_build_tools/llvm")
LLVM_X64 = os.path.join(ROOT, "_build_tools/llvm-x64")
X86LIBS = os.path.join(ROOT, "_build_tools/x86libs")
INTERP_DIR = os.path.join(ROOT, "x")
INTERP = os.path.join(INTERP_DIR, "ld.so")
TARGET = "aarch64-unknown-linux-gnu"


def elf_x86_64(path):
    with open(path, "rb") as f:
        h = f.read(20)
    return len(h) == 20 and h[:4] == b"\x7fELF" and h[4] == 2 and struct.unpack_from("<H", h, 18)[0] == 62


def set_interp(path, interp):
    data = bytearray(open(path, "rb").read())
    e_phoff, = struct.unpack_from("<Q", data, 0x20)
    e_phentsize, e_phnum = struct.unpack_from("<HH", data, 0x36)
    for i in range(e_phnum):
        off = e_phoff + i * e_phentsize
        p_type, = struct.unpack_from("<I", data, off)
        if p_type != 3:  # PT_INTERP
            continue
        p_offset, = struct.unpack_from("<Q", data, off + 8)
        p_filesz, = struct.unpack_from("<Q", data, off + 32)
        new = interp.encode() + b"\0"
        if len(new) > p_filesz:
            sys.exit(f"interpreter path {interp} longer than the {p_filesz - 1} bytes in {path}")
        data[p_offset:p_offset + p_filesz] = new.ljust(p_filesz, b"\0")
        with open(path + ".tmp", "wb") as f:
            f.write(data)
        os.chmod(path + ".tmp", os.stat(path).st_mode)
        os.replace(path + ".tmp", path)
        return True
    return False


def main():
    if not os.path.exists(os.path.join(X86LIBS, "ld-linux-x86-64.so.2")):
        print("x86-toolchain: no x86_64 libraries staged, native build, nothing to do")
        return
    if not os.path.exists(os.path.join(X86LIBS, "libc.so.6")):
        sys.exit(f"x86-toolchain: libc.so.6 missing in {X86LIBS}")

    os.makedirs(INTERP_DIR, exist_ok=True)
    shutil.copy2(os.path.join(X86LIBS, "ld-linux-x86-64.so.2"), INTERP)
    lib = os.path.join(LLVM, "lib")
    for name in os.listdir(X86LIBS):
        if name != "ld-linux-x86-64.so.2":
            shutil.copy2(os.path.join(X86LIBS, name), os.path.join(lib, name))

    src_bin = os.path.join(LLVM_X64, "bin")
    dst_bin = os.path.join(LLVM, "bin")
    swapped = 0
    for name in sorted(os.listdir(src_bin)):
        s, d = os.path.join(src_bin, name), os.path.join(dst_bin, name)
        if os.path.lexists(d):
            os.remove(d)
        if os.path.islink(s):
            os.symlink(os.readlink(s), d)
            continue
        shutil.copy2(s, d)
        if elf_x86_64(d) and set_interp(d, INTERP):
            swapped += 1
    for drv in ("clang", "clang++"):
        with open(os.path.join(dst_bin, drv + ".cfg"), "w") as f:
            f.write(f"--target={TARGET}\n")
    print(f"x86-toolchain: {swapped} x86_64 binaries in {dst_bin}, interpreter {INTERP}, default target {TARGET}")


if __name__ == "__main__":
    main()
