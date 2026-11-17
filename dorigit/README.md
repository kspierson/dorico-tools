# dorigit: version control for Dorico

Every save of a Dorico project becomes a version you can browse, compare **in musical terms** ("Trumpet 1, bar 16: staccato-tenuto removed"), label as a milestone, and open again. It works alongside Dorico: no plugins, and your files are never modified.

| | |
|---|---|
| **Status** | Working prototype: core + CLI tested; desktop app smoke-tested on Windows. See [docs/STATUS.md](docs/STATUS.md) |
| **How it works** | [docs/DESIGN.md](docs/DESIGN.md) |
| **Variants & merging (design)** | [docs/MERGE.md](docs/MERGE.md): variants, notation-based merge editor, copyist fold-in, film conform and inserts |
| **Remote backup/sync (design)** | [docs/SYNC.md](docs/SYNC.md): GitHub / folder / S3 remotes |
| **Format research** | [docs/RESEARCH.md](docs/RESEARCH.md) (how `.dorico` / `score.dtn` were decoded) |
| **Building** | [docs/DEV_SETUP.md](docs/DEV_SETUP.md) |

## Layout

```
../engine/crates/dorico-format   read/write .dorico + score.dtn, musical model, diffs, playback setup
                       (moved to the shared engine, Project S; dorigit depends on it by path)
crates/dorigit-core    git-backed snapshot store, playback policy, restore, folder watcher
crates/dorigit-cli     `dorigit` command line (also a git textconv driver)
app/                   Tauri 2 desktop app (Svelte 5 + TypeScript UI)
research/              research scripts (merge probe, test-file generator) on the shared engine
research/refs/         reference rounds: starter .dorico files + README of what to add in Dorico
scripts/               dev-env (forwards to engine/scripts), Windows cross-build
```

## Quick start (development, WSL)

```sh
../engine/scripts/setup-wsl-toolchain.sh && . scripts/dev-env.sh
cargo test                          # the Cargo workspace is the repo root; runs from any folder
cargo run --release -p dorigit-cli -- diff "Cue v1.dorico" "Cue v2.dorico"
scripts/build-windows.sh            # → dist/windows/dorigit-app.exe
```

## CLI

```
dorigit show FILE                     musical listing (use as git textconv: `dorigit setup-git REPO`)
dorigit diff OLD NEW [--json]         musical diff of two files
dorigit snapshot FILE [--milestone N] record a version
dorigit import FILES...               build history from existing copies (in Dorico save order)
dorigit families | log FILE           list projects / versions
dorigit changes FILE ID [--against ID]
dorigit restore FILE ID [--to PATH]   rebuild a version as a new file
dorigit milestone FILE ID NAME
dorigit watch [DIRS...]               snapshot on every save (foreground)
dorigit verify FILES... | dump FILE   codec checks / raw XML
```
