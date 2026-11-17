#!/bin/sh
# Build Windows executables from WSL/Linux (no Windows toolchain needed).
#   scripts/build-windows.sh            -> dist/windows/dorigit-app.exe, dorigit.exe
# Needs: Rust (+ x86_64-pc-windows-gnu target), zig, cargo-zigbuild, node/npm.
# See docs/DEV_SETUP.md. Release builds for distribution should use the
# Windows-native path there (MSVC + `npm run tauri build`) to get an installer.
set -e
cd "$(dirname "$0")/.."
. scripts/dev-env.sh
export RC_x86_64_pc_windows_gnu="$PWD/scripts/zig-rc-as-llvm-rc"
(cd app && npm run build)
cargo zigbuild --release --target x86_64-pc-windows-gnu -p dorigit-app --features custom-protocol
cargo zigbuild --release --target x86_64-pc-windows-gnu -p dorigit-cli
mkdir -p dist/windows
R=../target/x86_64-pc-windows-gnu/release   # the Cargo workspace (and target/) is at the repo root
# GNU builds load WebView2Loader.dll at runtime; ship it next to the exe.
cp $R/dorigit-app.exe $R/dorigit.exe $R/WebView2Loader.dll dist/windows/
ls -la dist/windows
