# stagecraft

Stage placement and audio-chain profiles for virtual instruments: make a mix of libraries
(SWAM, Sample Modeling, LASS, Infinite Series, Spitfire, Pianoteq, Kontakt …) sound like one
ensemble in one space, in Dorico (writing) and in Cubase/Logic (final mixes from dry stems).
Plan: [PLANNED_WORK.md §7](../PLANNED_WORK.md#7-project-e-stage-placement-and-audio-chain-profiles)
(Project E). Resume from [docs/STATUS.md](docs/STATUS.md).

Rust crate in the repo-root Cargo workspace. Builds on `dorico-format::mixer` (engine).

## Commands

```sh
. engine/scripts/dev-env.sh            # WSL toolchain (see engine/docs/DEV_SETUP.md)
cargo build --release -p stagecraft
B=./target/release/stagecraft
D="/mnt/c/Users/kspie/Documents/Dorico Projects"

# placement inventory of a project: mixer, inserts, sends, VSS2 and Altiverb settings
$B inventory "$D/Harry Potter Cues Plus 5 + LASS3.dorico" > report.md
$B inventory --summary "$D"/*.dorico         # one row per project
$B inventory --json …                        # everything, incl. undecoded VSS2 fields

# capture VSS2 settings as impulse responses (needs vi-render.exe, see engine/crates/vi-render)
$B capture --project "$D/Harry Potter Cues Plus 5 + LASS3.dorico" --pin "Cl 2" --checks
$B capture --project "$D/…" --checks                 # every VSS2 instance of the project
$B capture --room-from "$D/…" --preset "…/Presets/LA Scoring Strings/LASS 1.Violins Ensemble.vss2preset"
# -> stagecraft/captures/<pin>/: ir-true-stereo.wav (LL, LR, RL, RR; starts at the plug-in's
#    input, so VSS2's 4 ms latency is included), ir-from-L/R.wav, capture.json (measurements,
#    seat numbers); local only (git-ignored)

# E3: every VSS2 setting in use (identical sounds once) + the preset library in chosen rooms
P=/mnt/c/Users/kspie/OneDrive/Documents/parallax-audio/Presets
$B library --dry-run "$D"/*.dorico                       # what would be captured
$B library "$D"/*.dorico --presets $P --preset-room "$D/Harry Potter Cues Plus 5 + LASS3.dorico"
# -> stagecraft/captures/library/<sound id>/ + library.json + library.md (tables by room);
#    a stopped run picks up where it left off

# how a setting's reflections move over time (click train + steady tones through VSS2)
$B motion stagecraft/captures/library/<sound id>

# E5: stage files (stagecraft's placement engine; docs/STAGES.md)
$B stage from-project "$D/Harry Potter Cues Plus 5 + LASS3.dorico" --out stagecraft/captures/stages/hp5.toml
$B stage render stagecraft/captures/stages/hp5.toml --out stagecraft/captures/stages/hp5
$B stage check                             # VSS2-compatible model vs the captures
$B stage from-project "$D/…" --space stagecraft/stages/film-stage-starter.toml --out stagecraft/captures/stages/hp5-film.toml
$B serve stagecraft/captures/stages/hp5-film.toml   # the editor: http://localhost:8417/

# table of Virtual Sound Stage 2 preset files
$B presets "/mnt/c/Users/kspie/OneDrive/Documents/parallax-audio/Presets"
```

Read-only: never writes to projects or presets. Generated reports are in
[docs/inventory/](docs/inventory/).

## Layout

| File | What |
|---|---|
| `src/inventory.rs` | E1 inventory (Markdown/JSON/summary) |
| `src/vss2.rs` | Virtual Sound Stage 2 state + `.vss2preset` decoder; room and main-microphone decoder; sound id |
| `src/altiverb.rs` | Altiverb 7 state (IR + parameters) |
| `src/capture.rs` | E2: VSS2 → impulse responses (sweeps via vi-render, checks, seat numbers: microphone taps, tone, reflections) |
| `src/library.rs` | E3: all settings in use + presets, deduplicated by sound, captured; index tables |
| `src/motion.rs` | how VSS2's reflections move (click train, steady tones) |
| `src/stage.rs` | E5: placement engine: stage files, taps, IRs, VSS2-compatible stages, check |
| `stages/vss2-compat.toml` | VSS2's behaviour as numbers (measured in E3/E5) |
| `stages/film-stage-starter.toml` | stagecraft's own film-stage space (starting values) |
| `src/serve.rs`, `editor/index.html` | the stage editor (`stagecraft serve`) |
| `src/audio.rs` | WAV, FFT, sweeps, deconvolution, convolution, measurements |
| `tests/real_files.rs` | checks on the user's project and presets (skip when not reachable) |
| `captures/` | captured IRs and renders (git-ignored: personal) |
| `docs/STATUS.md` | state, findings, next steps |
| `docs/FORMATS.md` | how the states and Dorico's mixer data are laid out |
| `docs/STAGES.md` | stage files: every setting, VSS2's values, how close the model is |
| `docs/inventory/` | generated reports (all projects summary, key projects, presets) |
