# Source this in WSL before building anything in this repo:  . engine/scripts/dev-env.sh
# Puts the user-space toolchain on PATH (this WSL has no system gcc and no sudo):
#   - Rust (~/.cargo/bin), zig 0.17 (C/C++ compiler and linker) and the cc/c++/ar shims
#     (made by engine/scripts/setup-wsl-toolchain.sh)
#   - cmake + ninja for finale2dorico's C++ extractor (finale2dorico/docs/STATUS.md)
#   - uv (Python versions and packages; ~/.local/bin)
# Safe to source more than once. See engine/docs/DEV_SETUP.md.
_opt="$HOME/.local/opt"
for _d in "$HOME/.local/bin" "$_opt/ninja-1.12.1" "$_opt/cmake-3.31.6-linux-x86_64/bin" "$HOME/.cargo/bin" \
          "$_opt/zig-shims" "$_opt/zig-x86_64-linux-0.17.0"; do
  case ":$PATH:" in *":$_d:"*) ;; *) [ -d "$_d" ] && PATH="$_d:$PATH" ;; esac
done
export PATH
unset _d _opt
