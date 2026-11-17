# engine: the shared Dorico engine (Project S)

One implementation of everything the Dorico tools share: reading and writing `.dorico`
projects, the score model, paths to Dorico's install and user data, and (to come) editing,
factory data, playback setup, MIDI and findings. Written in Rust; Python tools use it through
the `doricokit` package until they are ported (the end goal is all Rust).

| | |
|---|---|
| Plan | `../PLANNED_WORK.md` §2 |
| Status, decisions, open questions | [docs/STATUS.md](docs/STATUS.md) |
| Building and testing | [docs/DEV_SETUP.md](docs/DEV_SETUP.md) |
| API changes | [docs/CHANGES.md](docs/CHANGES.md) |
| Module review (maturity, gaps, suggested modules) | [docs/MODULE_REVIEW.md](docs/MODULE_REVIEW.md) |
| Requests from tool sessions | [REQUESTS.md](REQUESTS.md) |

```text
crates/dorico-format   .dorico zip, score.dtn codec + XML form, positions, tree helpers, IDs,
                       dorigit's listing model/diff, playback-setup reader
crates/dorico-model    the one read model: flows, bars, parts, staves, voices, notes, dynamics, marks
crates/paths           dorico-paths: Dorico install/AppData/Documents, WSL <-> Windows, test corpora
crates/vi-render       headless VST2 host (Windows exe): render MIDI through a VI, inspect parameters/state
crates/doricokit-py    Python bridge (doricokit._native); removed when Python is gone (S14)
python/doricokit       the Python package all Python tools import (cubase.py: Cubase track archives)
scripts/               dev-env.sh, setup-wsl-toolchain.sh, test-all.sh
tests/                 corpus.toml, golden/, parity/, oracles/, python/, dorico-files/ (A–H), dorico-check/
```
