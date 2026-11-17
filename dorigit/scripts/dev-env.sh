# Source this in WSL before building:  . scripts/dev-env.sh
# The toolchain setup is shared by every tool in the repo now: this forwards to
# engine/scripts/dev-env.sh (Rust, zig shims, cmake/ninja, uv). See engine/docs/DEV_SETUP.md.
for _f in ../engine/scripts/dev-env.sh engine/scripts/dev-env.sh ../../engine/scripts/dev-env.sh \
          "$HOME/dev/dorico-test/engine/scripts/dev-env.sh"; do
  if [ -f "$_f" ]; then . "$_f"; break; fi
done
unset _f
