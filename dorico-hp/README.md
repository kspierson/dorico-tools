# dorico-hp: Human Playback for Dorico

Rebuilds (and goes beyond) Finale's Human Playback as an **Apply** step that writes
playback-only data into a copy of a Dorico project: Dorico's expression maps, percussion
maps and playback options stay in charge; Apply adds what Dorico doesn't do.

Python 3.12+ (the repo pins 3.15 via uv) plus the shared engine package `doricokit` (Rust,
in `../engine`; since 2026-10-29 it does the .dorico reading/writing). Setup once from the repo
root: `. engine/scripts/dev-env.sh && uv sync` (see `../engine/docs/DEV_SETUP.md`). After that
both `uv run python -m doricohp...` and plain `python3 -m doricohp...` work. Research and design notes: `research/NOTES.md`
(start there), `research/dorico-integration.md` (what Apply may and may not touch).

## Use

```sh
# write a processed copy (never touches the original)
python3 -m doricohp.apply In.dorico Out.dorico --style Romantic
python3 -m doricohp.apply In.dorico Out.dorico --only timing,vibrato --dry-run   # report only (kinds: velocity,timing,vibrato,dynamics)

# what a project's playback setup does per instrument (plug-in, expression map, dynamics controller)
python3 -m doricohp.playback In.dorico

# audition the rules outside Dorico (MIDI), from a Dorico project or a Finale file
python3 -m doricohp.render In.dorico out.mid --style Standard
```

Re-running Apply on its own output first undoes the previous run (record in
`Out.dorico.hp-apply.json`). Notes that already carry your own Play-mode velocity/offset
edits are left alone.

## Settings

Layers, each overriding the one before:

1. `doricohp/data/defaults.toml`: every rule's constants, with their sources.
2. Style: Finale's 17 HP presets (`doricohp/data/hp-presets.tsv`, from Finale.exe):
   rhythmicFeel, rhythmicAccents, rubato, mood, and the interpretation switches.
3. Library: `doricohp/data/libraries.toml`, matched on the expression map / plug-in name
   (SWAM strings/brass/woodwinds, LASS, LASS 3, Infinite Brass/Woodwinds, Pianoteq…),
   with per-instrument entries inside.
4. Project: `In.hp.toml` next to the project (or `--project-file`), same keys, plus
   `[style]` (name and any HP parameter), `[library.<name>]` and `[instrument.<word>]`.

Example `MyPiece.hp.toml`:

```toml
[style]
name = "Romantic"
mood = 50

[instrument.horn]
vibrato.max_depth = 40

[balance]
harp = -2.5
```

## What Apply writes (current code)

| data | written | rule / source |
|---|---|---|
| attack velocity (instruments whose map puts dynamics on a controller) | yes | HP metric accents + level-dependent attack; lighter under leggiero/brillante, firmer under marcato |
| played start offset | yes | HP rhythmic feel (scaled down for notes shorter than a quaver); per-library attack latency |
| played end | yes, always explicit | Dorico's own length for the note (playback options + map overrides), short articulations capped in ms (`[articulation]`), ≥ 25 ms gap before the next unslurred note. Needed because played offsets switch off Dorico's length percentages |
| passage words → articulation | yes (via lengths/attacks) | "stacc." (custom technique → pt.staccato, its own words too, or text), spicc., legato, ord., leggiero, brillante, sempre… (`doricohp/passages.py`). Unslurred notes, plus a slur's last note before a rest; light words (brillante…) ≈ 40 ms. Techniques linked to your own playback techniques (`pt.user.*`) are left to the expression map |
| open hairpins (no end dynamic) | in velocity now, dynamics lane later | read as a local swell: back to the earlier level by the next phrase (`[dynamics] open_hairpin = "swell"`, or `"stay"`) |
| vibrato CC curves (SWAM…) | yes | per-library profile (bloom, espressivo peak, release); never on a controller the map uses |
| dynamics lane: balance, automatic espressivo, phrase rules, open-hairpin returns | yes (since 2026-11-01) | Play mode's Dynamics lane (`kDynamic`, absolute Dorico levels from `doricokit.dynlevels`), drawn only where the shaping differs from the written dynamics, accents added back (`doricohp/lane.py`); left alone where you've drawn in the lane yourself |
| velocity for velocity-dynamics instruments | via the dynamics lane | test I2: Dorico derives velocity from the lane level with the same curve; per-note velocity still not written |
| rubato | no | waiting for test L (playback-only tempo) |

Each run prints a per-instrument report (library matched, map, dynamics controller, what
was written, and warnings such as Dorico's own beat stress/humanise being on).

Status, open questions and next steps: `research/NOTES.md` → "Handoff: start here".

## Layout

- `doricohp/` – `project.py` (read/write .dorico; codec and zip from `doricokit`),
  `notation.py` (notation for the rules; a view over the shared `doricokit.model`), `playback.py` (playback options, expression maps,
  instrument routing), `model.py` (engine input from Dorico or Finale), `profiles.py`,
  `passages.py` (passage words), `engine.py` (rules), `render.py` (MIDI), `apply.py`
  (writer), `smf.py` (MIDI reader), `musx.py` (raw EnigmaXML + HP settings from .musx).
  Several of these are slated to move into the shared engine (Project S,
  `../PLANNED_WORK.md` §2).
- `tools/` – capture generation and analysis (Finale HP measurements), score-vs-playback
  comparisons (`compare_versions.py` markings, `compare_played.py` played ms per note),
  Ghidra scripts, FinaleScripts.
- `tests/` – unit tests: `python3 -m unittest discover -s tests`.
- `research/` – findings. `captures/` – Finale HP MIDI captures and engine renders.
