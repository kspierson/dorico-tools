#!/bin/sh
# Recreate the WSL/Linux build toolchain in user space (no sudo needed):
#   - Rust via rustup (+ Windows GNU target for cross-builds)
#   - zig: used as the C compiler/linker, since this machine has no gcc
#   - cargo-zigbuild: cross-compiles Windows .exe files with zig
#   - small cc/c++/ar shims that call zig (put on PATH by engine/scripts/dev-env.sh)
# Safe to re-run. Versions match what was used on 2026-10-25.
set -e
ZIG_VERSION=0.17.0
ZIGBUILD_VERSION=v0.24.0
OPT="$HOME/.local/opt"
mkdir -p "$OPT"

if [ ! -x "$HOME/.cargo/bin/rustup" ]; then
  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs -o /tmp/rustup-init.sh
  sh /tmp/rustup-init.sh -y --profile minimal --no-modify-path -c clippy,rustfmt
fi
"$HOME/.cargo/bin/rustup" target add x86_64-pc-windows-gnu

ZIG_DIR="$OPT/zig-x86_64-linux-$ZIG_VERSION"
if [ ! -x "$ZIG_DIR/zig" ]; then
  curl -sSfL "https://ziglang.org/download/$ZIG_VERSION/zig-x86_64-linux-$ZIG_VERSION.tar.xz" | tar xJ -C "$OPT"
fi

if [ ! -x "$HOME/.cargo/bin/cargo-zigbuild" ]; then
  curl -sSfL "https://github.com/rust-cross/cargo-zigbuild/releases/download/$ZIGBUILD_VERSION/cargo-zigbuild-x86_64-unknown-linux-musl.tar.xz" \
    | tar xJ -C /tmp
  find /tmp -maxdepth 2 -name cargo-zigbuild -type f -exec mv {} "$HOME/.cargo/bin/" \; -quit
fi

SHIMS="$OPT/zig-shims"
mkdir -p "$SHIMS"
for pair in cc:cc gcc:cc c++:c++ g++:c++; do
  name=${pair%%:*}; mode=${pair##*:}
  cat > "$SHIMS/$name" <<SHIM
#!/bin/sh
# C/C++ compiler shim backed by zig (no system gcc). Drops LLVM-style target
# triples from Rust/cc-rs (host target is implied) and a linker flag zig warns about.
for a in "\$@"; do
  shift
  case "\$a" in
    --target=*|-target=*|-Wl,-O1) ;;
    *) set -- "\$@" "\$a" ;;
  esac
done
exec $ZIG_DIR/zig $mode "\$@"
SHIM
done
printf '#!/bin/sh\nexec %s ar "$@"\n' "$ZIG_DIR/zig" > "$SHIMS/ar"
chmod +x "$SHIMS"/*
echo "Toolchain ready. Use:  . engine/scripts/dev-env.sh  (from the repo root)"
