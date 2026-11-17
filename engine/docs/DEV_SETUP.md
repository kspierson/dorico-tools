# Engine development setup

Everything builds in WSL in user space (no gcc, no sudo). Native Windows builds of the dorigit
app are in `dorigit/docs/DEV_SETUP.md` §B.

## Toolchain

```sh
engine/scripts/setup-wsl-toolchain.sh   # once: rustup, zig 0.17 + cc/c++/ar shims, cargo-zigbuild
. engine/scripts/dev-env.sh             # every shell: Rust, zig, shims, cmake/ninja, uv on PATH
```

`dorigit/scripts/dev-env.sh` forwards to the engine one, so old instructions still work.

## Rust (one workspace at the repo root)

```sh
cargo test                                        # all default members (engine crates, dorigit core + CLI)
cargo clippy -p dorico-format -p dorico-model -p dorico-paths -p doricokit-py --all-targets -- -D warnings
cargo fmt --all                                   # rustfmt.toml: 120 columns
DORICO_SAMPLES="/mnt/c/Users/kspie/Documents/Dorico Projects" \
  cargo test -p dorico-format --release --test real_files     # 64 DTN round trips
DORICO_REAL_FILES=1 cargo test -p dorico-model --release --test real_files
dorigit/scripts/build-windows.sh                  # dorigit app + CLI for Windows (output in dorigit/dist/windows)
```

The dorigit Tauri app (`dorigit/app/src-tauri`) is a member but not a default member: it only
builds for Windows from here.

## Python (uv workspace at the repo root)

```sh
uv sync                                    # Python 3.15 (.python-version) + .venv + builds doricokit
uv sync --reinstall-package doricokit      # after changing Rust code
uv run python -m doricohp.apply IN.dorico OUT.dorico --style Romantic
uv run doricohp-apply IN.dorico OUT.dorico # same, via the entry point
uv run python -m unittest discover -s engine/tests/python
```

- `engine/python/pyproject.toml` builds `doricokit` with **maturin** from
  `engine/crates/doricokit-py`. The extension lands next to the Python files as
  `engine/python/doricokit/_native.abi3.so` (git-ignored), built for the stable ABI from 3.12 up.
- Workspace members: `engine/python`, `dorico-hp`, `finale2dorico` (`uv run f2d ...`, `uv run doricohp-apply ...`).
- `python3 -m doricohp...` / `python3 -m f2d ...` (system Python) also work after one `uv sync`:
  both tools add `engine/python` to their path when `doricokit` isn't installed.

### Windows wheel (not working yet)

```sh
cd engine/python && uvx --from 'maturin>=1.16,<2' maturin build --release \
  --target x86_64-pc-windows-gnu --zig -i python3.12 -F pyo3/generate-import-lib
```

fails at link time: `undefined symbol: PyInit_doricokit._native` (maturin puts the dotted module
name into the export list for the GNU target). Fix options in `STATUS.md` ("Waiting on you" 6).

## Tests

| What | Command |
|---|---|
| Everything, fast | `engine/scripts/test-all.sh` |
| Everything, whole corpus | `engine/scripts/test-all.sh --full` |
| Golden outputs | `uv run python engine/tests/golden/golden.py check [--only PREFIX] [--fast]`; `record` to re-baseline (only with the user's OK) |
| Codec vs old Python | `uv run python engine/tests/parity/codec_vs_python.py` |
| Positions/ids vs old Python | `uv run python engine/tests/parity/positions_vs_python.py` |
| Model vs old readers | `PYTHONDONTWRITEBYTECODE=1 uv run python engine/tests/parity/model_vs_python.py [-v]` |

Corpora are configured in `engine/tests/corpus.toml` (override with `DORICO_<NAME>` env vars);
tests skip what isn't reachable. The user's files are only read, never written.
