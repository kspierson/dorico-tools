#!/bin/sh
# Run on every engine change (PLANNED_WORK.md §2.8):
#   engine/scripts/test-all.sh          Rust tests, Python parity, fast golden subset
#   engine/scripts/test-all.sh --full   + real-file Rust tests, codec parity on the whole corpus,
#                                        every golden case (~10 min; before handing work back)
# Corpus-dependent steps skip themselves when the user's files aren't reachable.
set -e
cd "$(dirname "$0")/../.."
. engine/scripts/dev-env.sh
FULL=; [ "$1" = "--full" ] && FULL=1

step() { printf '\n== %s\n' "$*"; }

step "cargo test (workspace default members)"
cargo test -q

step "clippy (engine crates)"
cargo clippy -q -p dorico-format -p dorico-model -p dorico-paths -p dorico-timeline -p doricokit-py --all-targets -- -D warnings

step "uv sync (rebuild doricokit if Rust changed)"
uv sync -q --reinstall-package doricokit

step "Python unit tests (engine, finale2dorico)"
uv run python -m unittest discover -s engine/tests/python -q
(cd finale2dorico && PYTHONDONTWRITEBYTECODE=1 uv run python -m unittest discover -s tests -q)

PROJECTS=$(uv run python -c "from doricokit import paths; print(paths.corpus()['projects'])")
if [ -n "$FULL" ]; then
  if [ -d "$PROJECTS" ]; then
    step "real-file Rust tests (byte round trip, reference file, divisi/bars on real projects)"
    DORICO_SAMPLES="$PROJECTS" cargo test -q -p dorico-format --release --test real_files
    DORICO_REAL_FILES=1 cargo test -q -p dorico-model --release --test real_files
  fi
  step "codec parity: Rust vs old Python on the whole corpus"
  uv run python engine/tests/parity/codec_vs_python.py
  step "positions + ids parity on the whole corpus"
  uv run python engine/tests/parity/positions_vs_python.py
  step "read model vs the old Python readers (test oracles: f2d read.py, dorico-hp notation.py)"
  PYTHONDONTWRITEBYTECODE=1 uv run python engine/tests/parity/model_vs_python.py
  step "golden outputs (all)"
  uv run python engine/tests/golden/golden.py check
else
  step "codec parity (first 5 projects)"
  uv run python engine/tests/parity/codec_vs_python.py --limit 5
  step "read model parity (first 3 projects)"
  PYTHONDONTWRITEBYTECODE=1 uv run python engine/tests/parity/model_vs_python.py --limit 3
  step "golden outputs (fast subset)"
  uv run python engine/tests/golden/golden.py check --fast
fi
printf '\nall green\n'
