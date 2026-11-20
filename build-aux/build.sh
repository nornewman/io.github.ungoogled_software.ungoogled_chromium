#!/bin/bash -ex

ln_overwrite_all() {
  rm -rf "$2"
  mkdir -p "$(dirname "$2")"
  ln -s "$1" "$2"
}

# Link our verisons of Node and OpenJDK into Chromium so the build scripts will
# use them. For OpenJDK especially, this is a workaround for:
# https://bugs.chromium.org/p/chromium/issues/detail?id=1192875
ln_overwrite_all /usr/lib/sdk/node24 third_party/node/linux/node-linux-x64
ln_overwrite_all /usr/lib/sdk/openjdk21 third_party/jdk/current

# GN invokes rustc directly rather than through Cargo, so this wrapper adapts
# Chromium's Rust output paths and sysroots for sccache.
# (Not for the aarch64 cross build: the wrapper and sccache would run under qemu.)
cross=; [[ -e _build_tools/x86libs/ld-linux-x86-64.so.2 ]] && cross=1
[[ -n $cross ]] || export RUSTC_WRAPPER=$PWD/rustc-cache.py

# hdr-max-cll-157: compile the code the HDR backport touches first, so a backport
# error shows up in minutes instead of after the whole browser build.
ninja -C out/Release -j$FLATPAK_BUILDER_N_JOBS components/viz/service:service ui/ozone/platform/wayland:wayland
ninja -C out/Release -j$FLATPAK_BUILDER_N_JOBS chrome chrome_crashpad_handler
[[ -n $cross ]] || /app/bin/sccache --show-stats
