# Planned work: shared modules, house styles, ad lib harp glissandi

*Created 2026-10-28; updated 2026-10-29 with the user's answers and the shared-modules plan;
progress notes 2026-10-30.
Planning document; Project S is being built (live state in `engine/docs/STATUS.md`), A is not started, B started 2026-11-01 (playback model done, §4.9; on hold until the user has Dorico 6). C (VI profiles) started 2026-11-01 for SWAM; D (configuration manager) and §8 added 2026-11-01, not started. E (stage placement / audio-chain profiles, §7) started 2026-11-01: tool `stagecraft/`, E1 inventory, E2 capture pilot (user: captured vs live VSS2 "extremely subtle") and E3 capture library done (live state in `stagecraft/docs/STATUS.md`). §8 ensemble intonation (dorico-hp) added 2026-11-03 for review, not started. Each section is written so an implementing session
can start from it directly.*

**Priority order (user, 2026-10-29):** shared modules first, because every tool and every later
project builds on them. House styles and harp glissandi follow.

Contents

1. [Shared context: the tools in this repo](#1-shared-context-the-tools-in-this-repo)
2. [Project S: shared modules (highest priority)](#2-project-s-shared-modules-highest-priority)
3. [Project A: house styles (Modern, Classic, Film)](#3-project-a-house-styles-modern-classic-film)
4. [Project B: ad lib harp glissandi](#4-project-b-ad-lib-harp-glissandi)
5. [Project C: VI playback profiles and expression maps](#5-project-c-vi-playback-profiles-and-expression-maps)
6. [Project D: score configuration manager and project templates](#6-project-d-score-configuration-manager-and-project-templates)
7. [Project E: stage placement and audio-chain profiles](#7-project-e-stage-placement-and-audio-chain-profiles)
8. [Smaller items](#8-smaller-items)
9. [Readiness gates and suggested order](#9-readiness-gates-and-suggested-order)
10. [Original requests](#10-original-requests)

**Decisions so far**

| Decision | Answer (date) |
|---|---|
| Target Dorico version | **Dorico 5** (5.1.60) for now; 6.x features are listed as "later" (2026-10-29) |
| Full score pitch | **Concert pitch** preferred, switchable per layout in Dorico (2026-10-29) |
| *Full Orchestra Template* | Built for player setup and playback (writing and mock-ups), **not** engraving. Not an engraving reference (2026-10-29) |
| Fonts | Music font **Bravura** for now. Explore other SMuFL fonts (Sebastian etc.) per score use case later. Text fonts open; the site's fonts are candidates only (the logo is design, not a constraint) (2026-10-29) |
| Engine session | Started 2026-10-29; S0–S4 done by 2026-10-30, S5 next. Live state: `engine/docs/STATUS.md` |
| Engine location / names | Top-level `engine/`, Python package `doricokit` (2026-10-29) |
| Language | Rust foundation + shared Python is approved. **End goal: everything in Rust, no Python**; the more Rust the better (2026-10-29) |
| Compiled Python dependency | OK (2026-10-29) |
| Bootstrap Finale reader (`enigma.py`) | Test-only, then deprecated and removed. It is **not** the converter: the converter (`f2d convert`) uses the C++ extractor + `facts.py` (2026-10-29) |
| dorigit Python prototype | **Retired 2026-10-30** (user's OK); its two scripts live on in `dorigit/research/` |
| Dynamics and other markings | Stick to **accepted musical standards**. Tools never create non-standard markings. A custom one already in a score (converted or hand-made) is **respected**: read and kept, never silently dropped or "corrected". (Correction 2026-10-30: "possibile" is a standard Dorico modifier, allowed only on f or p; the ET "f possibile" is fine.) **Update 2026-10-30:** Dorico handles custom dynamics gracefully (they render as expected), so tools should **support** any custom dynamic that exists in a score: decode and show it readably, keep it byte-exact through history/restore/merge, and never create one |
| Bar numbers | As Dorico shows them: pick-up = bar 0; bar-number changes followed; subordinate numbers "35a", "35b" confirmed in Dorico (2026-10-30) |
| Python tooling | Highest Python version the dependencies allow (3.12 minimum), managed with **uv**. uv 0.13.6 installed in WSL (`~/.local/bin`) on 2026-10-29; newest stable Python is 3.15.2 (WSL system: 3.14.4) (2026-10-29) |
| Apps / UI | Three apps sharing one UI kit: **dorigit**, **Score Workbench**, **Playback** (working names) (§2.11, approved 2026-10-29) |
| Engine session 1 setup | Tar backup before moves (`~/dev/dorico-test-backups/`), `git mv` for tracked files; **one Cargo workspace at the repo root** (engine crates + dorigit); no edits under `finale2dorico/` while the converter session is active; scope S0–S3 + S4 engine side (2026-10-29) |

---

## 1. Shared context: the tools in this repo

| Tool | Folder | What it does | Resume notes |
|---|---|---|---|
| **dorigit** | `dorigit/` | Git-like history for Dorico projects. Rust: `dorico-format` (codec, XML, container, model, diff, playback setup), `dorigit-core` (store, watcher), CLI, Tauri 2 + Svelte 5 app | `dorigit/docs/STATUS.md` |
| **finale2dorico** (`f2d`) | `finale2dorico/` | Finale `.mus`/`.musx` → `.dorico`. C++ `f2d-extract` (musxdom, finale-mus-reader) → `facts.py` → Score IR → Dorico writer. Reviewer (`f2d review`). Planned cleaner and editor. PDF and Remote Control research tools | `finale2dorico/docs/STATUS.md` |
| **dorico-hp** | `dorico-hp/` | Finale Human Playback rebuilt for Dorico. HP engine, profiles, MIDI render, **Apply** (writes velocity, played offsets and CC curves into a copy of a `.dorico`) | `dorico-hp/research/NOTES.md` |
| **latency-reporter** | `latency-reporter/` | VST3 insert that reports a fake latency (README brief only). Separate C++ plug-in; not part of the shared modules | `latency-reporter/README.md` |
| **stagecraft** | `stagecraft/` | Stage placement and audio-chain profiles (Project E, §7): inventory of mixer/VSS2/Altiverb settings (built), VSS2 capture, profiles for Dorico/Cubase/Logic (planned) | `stagecraft/docs/STATUS.md` |

Ground rules carried over from the existing projects:

- Tools write a **new file** (or a dorigit snapshot) and never overwrite the user's project.
- Dorico encodings are learned from **reference files the user saves in Dorico** (the "Round"
  method in `finale2dorico/experiments/`).
- dorico-hp's Apply writes playback data only. Notation edits belong to the editor tools.
- Never ship Steinberg data; read factory data from the user's Dorico install.
- The user handles all git commits.

---

## 2. Project S: shared modules (highest priority)

### 2.1 Goal

Every capability exists **exactly once** and every tool uses it. Reading Finale files,
reading/writing/editing Dorico projects, Dorico install data, playback setup, MIDI, reports and
paths each live in one module. A fix or feature added for one tool then benefits all of them.
Each tool becomes a thin layer: its CLI or UI plus its own domain logic (the HP engine, the git
store, conversion rules).

This plan replaces the earlier proposal in `finale2dorico/docs/SHARED_ENGINE.md` (2026-10-26). It
keeps that proposal's direction (a Rust engine based on dorigit's tested codec, with Python
bindings) and adds a full module map, a migration path and safety checks.

**Progress (2026-10-30, engine session 2):** S0–S4 done for all three tools. The read model
(`dorico-model`) is in use by f2d's reviewer, dorico-hp's `notation.py` and dorigit's listing
bar numbers (pick-ups, bar-number changes, subordinate numbers confirmed in Dorico).
`dorigit/prototype/` is retired (scripts ported to `dorigit/research/`). The thin
`read.py`/`notation.py` views stay until their callers move to Rust (S5 for Apply, S12 for the
reviewer). **Next: S5 edit layer.** Live state, decisions to confirm and open questions:
**`engine/docs/STATUS.md`**.

**Status (2026-10-29, before the engine session):** the engine session hadn't started.
The finale2dorico converter is being developed **at the same time** in its own session, so the
engine work must not break or block it. Moves that touch `finale2dorico/` (S7, S8) are
coordinated with that session; see §2.8. **§2.12 is the starting brief for the engine session.**

### 2.2 What exists today (codebase review, 2026-10-29)

Line counts are approximate. "Copies" means separate implementations of the same thing.

| Capability | Where it lives now | Duplication / problem |
|---|---|---|
| **DTN codec** (`score.dtn` ⇄ tree) + XML form | dorigit `crates/dorico-format/src/dtn.rs`, `xml.rs` (reference; byte-exact on 64 real files) | **4 Python copies** that differ only in their header comments: `dorigit/prototype/dorigit/dtn.py`, `dorico-hp/doricohp/dtn.py`, `finale2dorico/f2d/dtn.py`, `finale2dorico/research/tools/dtn.py`. *2026-10-29: crate now `engine/crates/dorico-format`; dorico-hp's and f2d's copies replaced by `doricokit` (one kept as a test oracle); the prototype's went with the prototype (retired 2026-10-30)* |
| **`.dorico` container** (zip) | dorigit `container.rs` | `dorico-hp/doricohp/project.py`, `finale2dorico/f2d/dorico/writer.py` (`write`), dorigit `prototype/container.py` |
| **Positions / fractions** (Dorico `"3/8"` strings, 480 ticks per crotchet) | dorigit `ratio.rs` | `doricohp/project.py` (`frac`, `frac_str`, `TICKS_PER_CROTCHET`), `f2d/dorico/tree.py` (`fstr`), ad hoc parsing elsewhere |
| **Tree builders and property tables** | f2d `dorico/tree.py` (`L`, `E`, `A`, `prop`, `ptable`, `event_head`) | doricohp `project.py` (`leaf`, `elem`, `items`, `get_prop`, `set_prop`); dorigit `dtn.rs` Node helpers |
| **ID allocation** (`idGenerators`) | doricohp `project.py` (editing) | f2d `writer.py` (own counters when building); dorigit `MERGE.md` design (renumbering) |
| **Read model** (flows, players, instruments, staves, bars, events at bar/beat) | dorigit `model.rs` (~690) | **3 more**: dorigit `prototype/model.py` (~390), `doricohp/notation.py` (~275), `f2d/dorico/read.py` (~265). Bar positions computed 3 ways (`model.rs`, `_bar_starts`, `_bars`). Dynamics decoded 3 ways (`model.rs`, `decode_intensity`, `_level`); dorigit's first decoder had forte/piano swapped |
| **Edit an existing project** (load → change → save, rest untouched) | Only `doricohp/project.py` + `apply.py` (velocity, play offsets, automation lanes, idempotent re-apply) | Needed by the cleaner, apply-style (Project A), harpgliss (Project B) and dorigit merge, but locked inside dorico-hp |
| **Build a project from scratch** | f2d `dorico/writer.py` (~1,260), `layout.py`, `library.py`, `tree.py` | None (unique), but it lives inside one tool |
| **Dorico install and factory data** (find Dorico, instruments, names, factory library, new-project defaults) | f2d `dorico/install.py`, `library.py`, `data/*.json|xml` | dorico-hp `tools/dorico_maps.py` reads the install and AppData separately; install paths written out in several places |
| **Playback setup** (plug-ins, expression maps, endpoints) | dorigit `playback.rs` (VST setup) | doricohp `playback.py` (expression maps, setup): overlapping |
| **Finale reading** | f2d: C++ `extract/src/main.cpp` (~950) + `finale/facts.py` (~1,150) + bootstrap `finale/enigma.py` (~640) + `finale/musx.py` | `doricohp/musx.py` (second `.musx` decoder; not dead: dorico-hp research uses `python3 -m doricohp.musx --hp` for HP settings and its raw EnigmaXML dump, so the shared reader needs both before it goes). dorico-hp gets Finale data by running `python -m f2d ir` from the relative path `../finale2dorico` |
| **Score IR** (tool-neutral score model) | f2d `ir.py` (~350) | dorico-hp reads its JSON (`model.from_f2d`); no schema or version number |
| **Score transforms** (explode shared staves, doublings) | f2d `explode.py`, `doublings.py` | Converter-only; the cleaner wants explode/implode for MusicXML-imported projects |
| **Time** (tempo map, seconds, timecode) | `engine/crates/timeline` (`dorico-timeline`, 2026-10-31; `doricokit.timeline`) | Old copies still in use: doricohp `model.py` (`seconds`, `bpm_at`, `ms_per_crotchet`: ignores beat units and repeats, defaults to 100 bpm), `render.py` (`to_ticks`, tempo meta events), `smf.py` (`seconds` of a MIDI file, belongs to `midi`). Switch dorico-hp after the reference export (engine/docs/TIMELINE.md) |
| **MIDI** | doricohp `smf.py` (read), `render.py` (write) | Two VLQ implementations; tools `compare_midi.py`, `analyze_capture.py` |
| **Reports / findings** | f2d `review.py` (findings JSON), `convert --report`; dorigit diff JSON | No common schema; the cleaner, apply-style, harpgliss and Apply reports will all need one |
| **Dorico automation** | f2d `research/tools/dorico_remote.ps1` (Remote Control API), `pdf_pages.ps1`, `pdf_index.py` | dorigit plans its own Remote Control use |
| **Paths and test corpora** | Hardcoded or env vars per tool: `G:\Scores`, HPCaptures, Dorico Projects (`DORICO_SAMPLES`), Dorico install dirs, AppData | Different conventions per tool |
| **Build toolchain** (WSL: user-space Rust, zig shims, cmake/ninja) | dorigit `scripts/dev-env.sh`, `build-windows.sh` | f2d's extractor build borrows dorigit's zig shims by path |
| **Format knowledge** | dorigit `docs/RESEARCH.md`, f2d `docs/RESEARCH.md`, dorico-hp `research/*.md` | Overlapping notes on the same structures |
| **UI** | dorigit app (Tauri 2 + Svelte 5) | The user wants one UI for all tools |

What's already in good shape:

- f2d is cleanly layered: `dtn` → `tree`/`install`/`library` → `writer`, with `ir` in the middle.
- dorigit's codec is byte-exact and fully tested.
- dorico-hp's Apply is the one working "edit existing project" path, re-apply tested.

### 2.3 Target architecture

```text
 apps & CLIs   dorigit (app, cli, store) │ f2d (convert, review, clean, edit) │ dorico-hp (apply, render)
               future: house-style apply, harpgliss │ one shared UI shell (Tauri + Svelte)
                        ── JSON in/out, shared findings schema, shared CLI conventions ──
 domain        score-ir + transforms │ finale-read │ dorico-build │ dorico-edit │ review framework
 core          dorico-model │ dorico-install (factory data) │ dorico-playback │ midi │ automation (remote, pdf)
 foundation    dorico-format (dtn, xml, container, positions, tree helpers, ids) │ paths & corpus config
```

Tool-specific logic stays in each tool: the HP engine and profiles (dorico-hp), the snapshot store
and watcher (dorigit), conversion heuristics and experiments (f2d).

**Module map**

Every module **ends in Rust** (user, 2026-10-29). The last column shows where each one starts
and when it reaches Rust (see §2.4 for the order).

| Module | Responsibility | Merged from | Used by | Start → Rust |
|---|---|---|---|---|
| `dorico-format` | DTN/XML codec, container, positions (`Ratio` ⇄ Python `Fraction`), tree/property helpers, ID allocator | dorigit crate + the 4 `dtn.py` + `tree.py` / `project.py` helpers | everything | Rust already; helpers ported in S3 |
| `dorico-model` | Read model: flows, players, instruments, staves, bars (pick-ups, bar-number changes), events with bar/beat, dynamics (levels, groups, links), techniques, trills, slurs, glissandi, harp pedals, tempos, layouts, options, library | dorigit `model.rs` + `read.py` + `notation.py` (superset) | dorigit diffs, f2d review/clean, dorico-hp, house-style lint | Rust (extend dorigit's) in S4 |
| `dorico-edit` | Edit existing projects: transaction (load → change → save), untouched data byte-identical, ID allocation, add/remove/modify events and element-table entries, automation lanes, options/library edits, **tagging tool-owned items** so tools can re-run or undo | doricohp `project.py`/`apply.py` plumbing, generalised | dorico-hp Apply, cleaner, apply-style, harpgliss, dorigit merge | **Rust directly** in S5 (designed from the Python plumbing) |
| `dorico-install` | Find Dorico (version-aware: 5 now, 6 later), user data dirs, instruments/names/sound IDs, factory library, new-project defaults, expression maps and playback templates in AppData | f2d `install.py`, `library.py`, `data/`; dorico-hp `dorico_maps.py` | f2d, dorico-hp, house-style | Rust in S6 |
| `dorico-playback` | Playback setup (plug-ins, endpoints), expression maps, automation-lane encoding | dorigit `playback.rs` + doricohp `playback.py` | dorigit policy, dorico-hp | Rust in S6 |
| `paths` | One config for Dorico dirs, AppData, Documents, corpora (Dorico Projects, HPCaptures, `G:\Scores`, `D:\…\Film Scores`), with env-var overrides and WSL ⇄ Windows path conversion | scattered constants | all tools and tests | Rust in S1 (+ binding) |
| `midi` | SMF read/write, comparison helpers | doricohp `smf.py`, `render.py` writer, `compare_midi.py` | dorico-hp, harpgliss validation, latency-reporter tests | Rust in S9 |
| `findings` / `review` | One findings/report schema (check, severity, flow, player, bar, beat, message, change made) + a check registry so any tool can add checks (style lint, gliss lint) | f2d `review.py` shape | reviewer, cleaner, Apply, apply-style, harpgliss, UI | Schema + registry in Rust in S9; reviewer checks ported after S4 |
| `score-ir` | Tool-neutral score model with a **JSON schema and version**, backward compatible | f2d `ir.py` | f2d, dorico-hp (in-process, no subprocess), future MusicXML reader | Python (moved in S8) → Rust types with serde (same JSON) in S13 |
| `score-transforms` | IR transforms: explode/implode shared staves, doublings | f2d `explode.py`, `doublings.py` | converter, cleaner | Python (S8) → Rust in S13 |
| `dorico-build` | Create projects from Score IR: players, instruments, flows, events, layouts, library | f2d `writer.py`, `layout.py`, `library.py`, `tree.py` | f2d convert, test-file generators (Round files, specimens) | Python (S8, while the converter changes daily) → Rust in S13 |
| `finale-read` | Finale `.mus`/`.musx` → Score IR: C++ extractor (musxdom, finale-mus-reader, smufl-mapping) + `facts.py`, `musx.py`. `enigma.py` = test oracle only, then removed | f2d `extract/`, `finale/*`; drop `doricohp/musx.py` | f2d, dorico-hp, house-style evidence (style facts) | C++ + Python (S7) → C++ linked into Rust via `cxx`, `facts.py` ported to Rust in S13 |
| `automation` | Dorico Remote Control client (open, switch mode, export PDF), PDF render/text tools | f2d `research/tools/*.ps1`, `pdf_index.py` | review loops, house-style validation, dorigit "save & snapshot" | Rust client in S9 (PowerShell kept for research) |

### 2.4 Language strategy

| Option | Summary | For | Against |
|---|---|---|---|
| A. Rust first | Port everything to Rust now; Python tools call it through bindings | One implementation for the app and the CLIs | Large port before any benefit; f2d and dorico-hp are changing fast in Python |
| B. Shared Python package only | Merge the Python copies into one package | Fastest | dorigit keeps its own Rust codec and model, so duplication stays; goes against the agreed direction |
| **C. Rust-first, with a temporary Python bridge (approved 2026-10-29)** | All **new shared code is written in Rust**. Foundation, model, edit, install, playback, MIDI and findings go straight to Rust, exposed to the Python tools through **PyO3** (`doricokit`). Only code that is still changing daily inside an active tool (the converter's IR, writer, transforms and Finale facts) moves once into `doricokit` as Python, and is ported to Rust when that tool settles | Removes all duplication right away; no big-bang port; doesn't disturb the converter session; reuses the prototype → Rust parity method dorigit already proved | Python tools gain one compiled dependency (accepted); a Rust/Python boundary to maintain until the end state |

**End state (user's goal): everything runs on Rust, with no Python.** The PyO3 bridge exists only
for the transition. Each tool's Python code disappears as its pieces are ported, and the bridge
itself is removed when the last Python tool is gone (S14).

Rules:

- At any moment each capability has **one** runtime implementation. A Python module is deleted as
  soon as its Rust port passes the parity tests.
- New shared code goes into Rust. Python is only for (a) code inside a tool that is still under
  rapid development and (b) throw-away research scripts.
- No pure-Python fallback codec. Old copies survive only as test oracles under `tests/`, never
  importable by tools.
- The Finale C++ code stays C++ (it wraps external libraries). It stays a CLI that prints JSON
  until S13, then links into Rust via `cxx`.

**Port order to Rust** (most stable and most shared first):

1. codec + container (done)
2. paths, positions and tree helpers
3. read model
4. edit
5. install and playback
6. MIDI and findings
7. reviewer checks
8. IR types (serde, same JSON)
9. transforms
10. Finale facts (with the extractor via `cxx`)
11. the Dorico writer
12. the HP engine (dorico-hp's planned real-time VST3 plug-in needs native code anyway)
13. each tool's CLI

**Python version under the bridge:** 3.14 if PyO3 and maturin support it when S2 starts (check
the PyO3 release notes; WSL already has 3.14.4), otherwise the newest supported version, 3.12 at
the least. One version for every tool, pinned with uv (§2.10).

### 2.5 Proposed repository layout

```text
Cargo.toml                   Rust workspace root (engine crates + dorigit crates/app; decided 2026-10-29)
pyproject.toml               uv workspace root (members: engine/python, finale2dorico, dorico-hp)
uv.lock                      one lockfile for every Python tool (like package-lock.json)
.python-version              pinned Python version (uv installs it)
engine/
  crates/
    dorico-format/           moved from dorigit/crates (dorigit depends on it by path)
    dorico-model/            split out of dorico-format when it grows
    dorico-edit/             written in Rust from the start (S5)
    dorico-install/  dorico-playback/  midi/  findings/  paths/  automation/
    doricokit-py/            PyO3 bindings (temporary bridge; removed in S14)
  python/doricokit/          the one Python package all Python tools import (pyproject: maturin backend)
    format, model, edit, install, playback, midi, findings, paths   thin wrappers over Rust
    ir/  build/  transforms/  finale/     Python until ported (S13)
  native/finale-extract/     moved from finale2dorico/extract (C++; build/ git-ignored)
  data/                      derived data (new-project defaults etc.; never Steinberg files)
  docs/                      FORMAT.md (merged research), IR.md (schema), API.md, CHANGES.md
  tests/                     corpus.toml (paths via `paths`), parity/, golden/,
                             dorico-files/ (shared Dorico test projects, e.g. A–H moved from dorigit/prototype)
  scripts/                   dev-env.sh (Rust + zig + cmake), test-all.sh, build-windows.sh
dorigit/                     app, CLI, store, watcher (depends on engine crates)
finale2dorico/               `f2d` CLI, conversion heuristics, experiments, docs (imports doricokit)
dorico-hp/                   HP engine, profiles, Apply CLI, captures, research (imports doricokit)
latency-reporter/            unchanged
```

### 2.6 Contracts between modules

- **Python API surface**: `doricokit.format.Node` keeps the current Python `Node` interface
  (`tag`, `value`, `children`, `child()`, `find()`, `text()`), so switching tools over is mostly an
  import change.
- **Score IR**: JSON with `ir_version`, a schema in `engine/docs/IR.md`, additive changes only.
  Breaking changes need a version bump and a note in `CHANGES.md`. dorico-hp imports the IR in
  process instead of starting a subprocess.
- **Findings schema** (shared by every report): `{tool, check, severity, flow, player, staff,
  bar, beat, position, message, change?: {before, after}}`. **Built as v2** (2026-10-31,
  `engine/python/doricokit/findings.py`): `{check, severity, flow, player, pos, where, message,
  tool, flow_id, bar, beat, staves, events, change?}`; `pos` is the position, `staves` (Dorico
  stave IDs) is the staff, `events` (Dorico event IDs) lets a UI or rule jump to or fix the item,
  `where` keeps the readable "bar 12 beat 3". Reports carry `findings_version`.
- **CLI conventions**: `-o OUT` (never overwrite the input), `--json`, `--dry-run` for editors, and
  the same exit codes everywhere.
- **Tool-owned items**: every item a tool creates in a Dorico project is tagged (the mechanism is
  decided in S5, for example an event group ID or a property), so Apply, harpgliss and apply-style
  can find, refresh or remove their own work.

### 2.7 Migration phases (each one usable on its own; behaviour unchanged unless stated)

Phase status (update as phases finish): **S0 ✅, S1 ✅, S2 ✅ (Windows wheel pending), S3 ✅,
S4 ✅** (tools switched 2026-10-29; prototype retired 2026-10-30; thin views kept until S5/S12),
**S5 next** (details in `engine/docs/STATUS.md`).

| Phase | Work | Safety check | Size |
|---|---|---|---|
| **S0 Baseline** | Record golden outputs. dorigit: `real_files` test. f2d: regenerate the current Round files and the full Finale regression (1,363 files), then hash the outputs; MusicXML oracle 59/59; `compare_mus`. dorico-hp: Apply on its test project, hash the result; engine-v1 MIDI captures. Write `engine/tests/golden/`. Answer the decisions in §2.9 | Golden set recorded | S |
| **S1 Skeleton** | Create `engine/` (Rust workspace) and the uv workspace root (§2.10); move `dorico-format` into `engine/` (dorigit depends on it by path); shared `dev-env.sh`; `paths` crate + `corpus.toml`; move the shared Dorico test files (A–H, 29 MB, now in `dorigit/prototype/experiments/dorico-tests/`) to `engine/tests/dorico-files/` and update the docs that point to them | `cargo test` + dorigit app builds unchanged; dorico-hp tests find the moved files | S |
| **S2 Codec bindings** | `doricokit-py` (PyO3, maturin, built by uv) for codec + container + paths; switch f2d and dorico-hp to it; delete the 4 `dtn.py` copies and the duplicate container code; build wheels for WSL and Windows (maturin with zig; to verify) | Corpus byte round-trip in Python; all golden outputs identical | M |
| **S3 Foundation helpers** | In Rust: positions/ticks, tree and property helpers (merging `tree.py` + `project.py`), ID allocator; exposed through `doricokit` | Golden outputs identical | S |
| **S4 One read model** | Extend dorigit's Rust model into the superset (reviewer's dynamics groups/links, techniques, trills, ranges; dorico-hp's chords and articulations; pick-ups and bar-number changes, which are a dorigit gap too). Move `f2d review` and `doricohp/notation.py` onto it, then delete `read.py` and `notation.py`. **Retire `dorigit/prototype/`:** its only remaining uses are the optional `DORIGIT_PY_PARITY` listing test (no longer needed once the Rust model is the reference), `merge_probe.py` (port it to a Rust test or move it to `dorigit/research/`) and the test files (already moved in S1) | Each old reader's output matches the new model on the corpus (listing-equality method from dorigit); reviewer findings identical | L |
| **S5 Edit layer (Rust)** | `dorico-edit` crate, designed from dorico-hp's project/Apply plumbing: transactions, byte-identical untouched data, ID rules (from dorigit MERGE.md), events, element tables, automation lanes, options/library edits, tool-owned tagging. dorico-hp Apply moves onto it first (it already works this way). Then it becomes the base for the cleaner (`CLEANER.md` step 1) and dorigit merge | No-op edit = byte-identical file on the corpus; Apply golden output identical; Dorico opens edited test files (user check) | M |
| **S6 Install, factory data, playback** | Merge `install.py`, `library.py`, `dorico_maps.py`, `playback.rs`, `playback.py` into `dorico-install` + `dorico-playback`, version-aware (Dorico 5; 6 later) | Converter output identical; dorigit playback policy tests | M |
| **S7 Finale reading** *(coordinate with the converter session)* | Move the extractor, `facts.py` and `musx.py` into `doricokit.finale`; one CMake build in `engine/native`; dorico-hp imports it; delete `doricohp/musx.py`. **Demote `enigma.py`** (the small Python `.musx` reader, not the converter): first move the tables `facts.py` imports from it (`ARTIC_GLYPHS`, `CLEF_MAP`, `DEFAULT_CLEFS`, `DYNAMIC_GLYPHS`, `EDU`, ...) into their own module. Then drop the `--reader bootstrap` / `auto` fallback from `f2d` and move `enigma.py` under `tests/` as an oracle (`compare_readers.py`). Remove it entirely once the Rust port of `facts.py` (S13) has its own oracles | MusicXML oracle 59/59, `compare_mus`, real-score oracle, golden IR JSON identical | M |
| **S8 Build + IR + transforms** *(coordinate with the converter session)* | Move `ir.py` (add `ir_version` + schema), `writer.py`, `layout.py`, `library.py`, `explode.py` and `doublings.py` into `doricokit` as Python. f2d becomes CLI + heuristics + experiments. Do it at a quiet point in converter work (between Rounds) so the two sessions don't edit the same files | Round files byte-identical | M |
| **S9 Ancillary (Rust)** | `midi` crate (one SMF reader/writer), `findings` schema + check registry, `automation` (Remote Control client: PDF export, open file); bindings for the Python tools | Reviewer findings identical; MIDI captures identical | M |
| **S10 Docs** | `engine/docs/FORMAT.md` merges the three research docs (tool docs keep tool-specific findings and link to it); `SHARED_ENGINE.md` archived | — | S |
| **S11 Shared UI kit + apps** | Shared Svelte UI kit and Tauri plumbing, then the apps from §2.11. Rust features are called directly; Python features (until ported) through sidecar CLIs speaking JSON (findings schema) | UI smoke tests (dorigit's headless-Edge method) | L |
| **S12 Reviewer checks to Rust** | Port the reviewer's checks onto the Rust model and findings registry | Findings identical | M |
| **S13 Converter-side ports** | When the converter settles: IR types in Rust (serde, same JSON), transforms, `facts.py` (with the C++ extractor linked via `cxx`), then the Dorico writer. Then remove `enigma.py` | Round files byte-identical; all Finale oracles | L |
| **S14 Python removal** | Port the HP engine and remaining tool code (the real-time VST3 plug-in needs it native anyway), then each tool's CLI. Remove `doricokit-py`, the uv workspace and all Python except research scripts | Every golden output identical; tools ship as Rust binaries | L |

Quick wins that S0–S3 make safe:

- delete the unused `doricohp/musx.py`
- delete `research/tools/dtn.py`
- replace dorico-hp's subprocess call into `../finale2dorico` with an import
- move the Dorico test files out of `dorigit/prototype/` (S1) so the prototype can be retired in S4 *(all four done 2026-10-29/30)*

### 2.8 Working agreement for parallel sessions

- **The converter session is active at the same time.** The engine session doesn't edit
  `finale2dorico/` files except in the agreed S2, S7 and S8 moves. Before each of those moves,
  check that session's latest `finale2dorico/docs/STATUS.md` and record the hand-over there
  ("these files now live in `engine/...`"). The converter session then imports from `doricokit`
  and stops editing the old copies.
- One session **owns** `engine/` (the user's plan from 2026-10-28). Tool sessions may make small
  engine changes only with tests and a `CHANGES.md` entry. Bigger needs go into
  `engine/REQUESTS.md` for the owner.
- `engine/scripts/test-all.sh` runs Rust tests, every tool's unit tests and a fast golden subset.
  Run it on every engine change. The full corpus run happens before sessions hand work back to
  the user.
- APIs are deprecated before they are removed. IR and findings are versioned.
- Each tool's `STATUS.md` notes the engine changes it relies on.
- What each pending project gains:

  | Project | Gains |
  |---|---|
  | Cleaner | Edit layer |
  | House styles | Options and library model, edit layer, Remote Control PDF export, lint checks |
  | Harpgliss | Edit layer, slurs/glissandi/harp pedals in the model, MIDI |
  | dorigit | Richer diffs: technique and dynamic names, options and library changes |
  | dorico-hp | In-process Finale reading, one model |
  | f2d | Shared build and install layers |

### 2.9 Decisions (answered 2026-10-29) and remaining questions

| # | Question | Answer |
|---|---|---|
| Q-S1 | Engine session started? | No. Start it **next**, while the converter session continues → brief in §2.12 |
| Q-S2 | `engine/` + `doricokit`? | Yes |
| Q-S3 | Option C? | Yes, **as Rust-first as possible**; end goal all Rust, no Python (§2.4) |
| Q-S4 | Compiled dependency for the Python tools? | Yes |
| Q-S5 | Bootstrap Finale reader? | Test-only, then removed (S7, S13). Confirmed it is **not** the converter: `f2d convert` defaults to the C++ extractor + `facts.py`; `enigma.py` is only the fallback `--reader bootstrap` for `.musx` when the extractor isn't built (plus tables `facts.py` imports, which move out first) |
| Q-S6 | Retire `dorigit/prototype/`? | Yes, once not needed. **Done 2026-10-30**: test files moved in S1; `merge_probe.py` and `make_test_files.py` ported to `doricokit` in `dorigit/research/` (identical output); parity test dropped (golden tests pin the listing) |
| Q-S7 | One UI? | Group by purpose: not one monolith, not many tiny apps; dorigit likely stays separate → proposal §2.11 |
| Q-S8 | Python version? | Highest the dependencies allow (3.15 if PyO3/maturin support it, else 3.14; 3.12 minimum); **uv** for versions and packages (§2.10) |
| Q-S9 | Three-app grouping (§2.11)? | Yes (working names for now) |
| Q-S10 | Install uv? | Yes. **Done 2026-10-29**: uv 0.13.6 in `~/.local/bin` (official installer, shell profiles not changed). Windows install later, when Windows builds need it |

No open questions remain for Project S.

### 2.10 Python tooling with uv (until Python is gone)

uv plays the role npm plays in Node:

| npm | uv |
|---|---|
| `package.json` | `pyproject.toml` |
| `package-lock.json` | `uv.lock` |
| workspaces | `[tool.uv.workspace]` |
| `npm install` | `uv sync` |
| `npm run x` / `npx x` | `uv run x` / `uvx x` |
| `.nvmrc` | `.python-version` (uv downloads and installs that Python) |

Setup (S1–S2):

- **uv is installed** in WSL: 0.13.6 in `~/.local/bin` (2026-10-29). Update with
  `uv self update`. Install it on Windows later for shared use.
- **Root `pyproject.toml`** with `[tool.uv.workspace] members = ["engine/python", "finale2dorico",
  "dorico-hp"]`, plus `.python-version` set to the newest stable Python that PyO3 and maturin
  support. On 2026-10-29 uv offers 3.15.2; WSL's system Python is 3.14.4; minimum 3.12. Install it
  with `uv python install`. The whole repo uses one Python version.
- **Each tool gets a `pyproject.toml`**:
  - `requires-python = ">=3.12"`
  - dependency `doricokit` through `[tool.uv.sources] doricokit = { workspace = true }`
  - entry points such as `f2d = "f2d.__main__:main"` and `doricohp = ...`, so commands become
    `uv run f2d convert ...` (today: `python3 -m f2d ...`)
- **`engine/python/doricokit`** uses maturin as its build backend, so `uv sync` compiles the Rust
  extension. This needs dorigit's Rust + zig setup (`dev-env.sh`). After changing Rust code,
  rebuild with `uv sync --reinstall-package doricokit`; document this in `engine/docs`.
- **Tests:** the existing `unittest` suites keep working (`uv run python -m unittest ...`); adding
  pytest is optional.
- **Until a tool is switched over in S2**, it keeps running with plain `python3 -m ...`, so the
  converter session isn't disrupted.

### 2.11 Apps and UI grouping (approved 2026-10-29)

Principles for deciding where a feature lives:

1. **Same object, same app.** Features that work on the same thing (the notation of one project,
   or the playback of one project) live together, because they feed each other.
2. **Same moment in the work.** Writing/engraving preparation and mock-up/playback production are
   different sittings with different settings worlds (house styles vs library profiles).
3. **Different lifecycle, separate app.** Something that runs in the background all the time
   (dorigit's watcher) shouldn't be bundled with on-demand tools.
4. **One family.** All apps share one UI kit (components, design tokens, findings viewer, bar/beat
   navigator, diff view, file picker, job runner, settings/paths) and the same engine. They feel
   like one product and hand work to each other.
5. **Every feature also has a CLI** (for batch work and automation); apps are front ends to the
   same engine calls.

Proposed apps:

| App | Purpose | Contains | Why separate |
|---|---|---|---|
| **dorigit** | Version control for scores | Watcher (tray), history, diffs, restore, milestones, merge/conflicts | Background lifecycle; useful on its own; the user's stated preference |
| **Score Workbench** (working name) | Prepare and check notation | Finale → Dorico import (later MusicXML), reviewer, cleaner, batch editor, **house styles** (templates, specimens, apply-style, style lint), **harpgliss** and later notation helpers | All act on one project's notation in one flow: open/convert → findings → preview fixes → save a new file. Splitting them would mean constant app switching |
| **Playback** (working name) | Shape the performance | Human Playback Apply, library/instrument/project profiles, vibrato curves, expression-map and playback-setup inspector, listening A/B, stem-export helpers, latency settings | Different object (performance data, not notation), different settings world, and dorico-hp's rule that Apply never touches notation. The UI split mirrors that rule |

Not apps:

- **latency-reporter**, and later a real-time HP plug-in, are VST3 plug-ins.
- The engine itself is a library.

Integration:

- Workbench and Playback can snapshot before and after their changes through the `dorigit-core`
  **library** (not the dorigit app), so every tool change is in the history and can be undone.
  dorigit's diff view shows what a tool changed.
- "Open in Dorico at bar N" (Remote Control) is a shared action.
- Findings from any tool open in the same viewer.

Repo layout for the UI (S11):

- `ui-kit/`: an npm workspace package with the shared Svelte components.
- `dorigit/app/`: stays where it is.
- `apps/workbench/`, `apps/playback/`: new Tauri apps.
- A root `package.json` with npm workspaces holds them together, like the uv workspace for
  Python.

Build order:

1. CLIs first (exist).
2. UI kit, extracted from dorigit's existing Svelte components.
3. Workbench (the reviewer/cleaner/converter UI is needed first).
4. Playback.

If Workbench and Playback turn out to be used together most of the time, they can merge into one
app with two workspaces later. The shared kit keeps that cheap.

### 2.12 Starting brief for the engine session

*Session 1 ran on 2026-10-29: the engine now has its own resume notes in
`engine/docs/STATUS.md`; start there. This brief stays as the original plan.*

**Read first:**

- this §2
- `dorigit/docs/STATUS.md` and `DEV_SETUP.md` (Rust + zig toolchain in WSL, Windows builds)
- `finale2dorico/docs/STATUS.md` (that session is **active**; check before touching its files)
- `dorico-hp/research/NOTES.md`
- `finale2dorico/docs/SHARED_ENGINE.md` (history)

**Rules:**

- The user handles all commits and pushes; leave changes uncommitted.
- Keep `engine/docs/STATUS.md` (state, gaps, session log), like the other tools.
- Update this section's phase table as phases finish.
- Don't edit `finale2dorico/` except during the agreed S2/S7/S8 moves (§2.8), or `dorigit/` and
  `dorico-hp/` beyond the import switches each phase needs. Note each switch in that tool's
  STATUS.md.

**First session:**

1. **S0 baseline** (read-only). Record golden outputs for dorigit and dorico-hp. f2d's outputs
   change daily, so for f2d take the golden snapshot right before each move that touches it, not
   once.
2. **uv** (already installed). Add the workspace root and `pyproject.toml` files without changing
   how the tools run. Pick the Python version from PyO3's supported list.
3. **S1 skeleton**: `engine/` workspace, move `dorico-format` (dorigit's tests and app build must
   pass), `paths` crate, move test files A–H and fix the docs that point to them.
4. **S2 codec bindings**: `doricokit-py`. Switch dorico-hp first (not under active development),
   then f2d at a point agreed with the converter session.
5. Then **S3**, then **S4** (one read model, the largest step).

**Done means**, for every phase:

- golden outputs identical (or every difference explained and approved)
- `test-all.sh` green
- docs updated
- the user told which files moved

---

## 3. Project A: house styles (Modern, Classic, Film)

### 3.1 Goal

A personal Dorico **house style** that is publish-ready but easy for musicians to read. It blends
published concert scores with film session scores (for example 4 bars per page and large bar
numbers centred under each bar). Two stricter sibling styles come with it:

| Style | Use | Character |
|---|---|---|
| **Modern** (the personal house style) | Default for new work | Film-score readability (few bars per page, big bar numbers, large time signatures) with publication-quality engraving |
| **Classic** | Concert and published work, transcriptions of traditional band and orchestra pieces | Conventional engraving: bar numbers at system starts or small every bar, empty staves hidden, serif text |
| **Film** | Real film and TV sessions | Session-score conventions: every staff always shown, fixed bars per page, large bar numbers under every bar, cue/title/page header, timecode |

All three share one engraving base (music font, line thicknesses, spacing). They differ in layout
options, text styles and page templates. All three default to **concert pitch**, switchable per
layout.

### 3.2 Evidence gathered so far (2026-10-28)

**Layout survey with the existing Finale reader.** I ran `f2d-extract` on the listed folders. A
throw-away scratch script read each file's `layout` block. For staff size, 4 spaces × 24 Evpu ×
system scaling is converted to mm.

| Source | Files | Page | Score staff | Part staff | Bars per system (median, range) | Staves shown |
|---|---|---|---|---|---|---|
| Horner, *Avatar* (session score) | 53 `.mus` | 8.5 × 14 in (legal), all 53 | 3.1–3.2 mm | 7.2 mm | **4** in 32 of 53 cues; 4–6 overall | 33 on every system (nothing hidden) |
| Beltrami, *The Thing* (session score) | 14 `.mus` (no-extension Finale files not included yet) | 11 × 17 in, all | 3.3–4.2 mm | 6.6–7.2 mm | "MT" orchestrator files: 4–5; "BR" files: 7–11 | 27–33 |
| Williams, *Asteroid Field* (concert) | 1 | A4 | 3.0 mm | 8.5 mm | 7 (5–8) | 28 |
| Williams, *E.T. Adventures on Earth* (concert, Hal Leonard) | 1 | 11 × 17 in | 4.2 mm | 7.2 mm | 6 | 27–28 |
| Williams, *Superman* concert / *Superman.MUS* | 2 | A4 / Letter | 2.5–2.6 mm | 7.2 mm | 6–6.5 (4–9) | 27–37 |

Caveat: Finale stores the page assignments from its last layout pass, so page counts can be stale
(E.T. reports 62 systems on 6 pages). Bars per system and staff sizes are reliable. The PDFs are
the ground truth for anything visual.

**Rendered pages** (via `pdf_pages.ps1`):

- *Avatar* PDF p. 101 (cue 2m2r, bars 9–12). One 4-bar system per page. Bar numbers are **large,
  bold, sans serif, centred in each bar under the system**, every bar. Header: title left (italic),
  page number centred, **cue number large at top right**. Every staff is shown even when it is
  resting. Sans-serif staff labels, full names on every page, player numbers stacked on the
  staff ("1 3", "5 7"). Paired players share staves. Bracket groups with family names. Cue
  notes are marked "Cue (don't play):" with a dashed line. "div. a3".
- *E.T.* PDF p. 5 (bars 25–30). Six bars per system. Bar numbers are **small italic, every bar,
  under the bottom staff at the barline**. Abbreviated names with player numbers ("Fl. 1 2",
  "Picc (Fl.3)", "Ob. 2 (E.H.)"). Serif text, empty staves still shown on this page. Footer with
  catalogue number and "Title – page" at bottom left.
- Already noted in `finale2dorico/docs/FILM_SCORES.md`: large time signatures across groups of
  staves, bold bar numbers under the system, cue notes, "div. a3", unnamed synth grand staff.

**The user's Dorico setup.** *Full Orchestra Template NEW FULL v5.dorico* differs from a fresh
Dorico 5.1.60 project in about 125 values. Examples:

- large narrow sans-serif time signatures
- A3 page with a 2.8 pt staff space
- "change to" instrument-change labels
- many line, slur and tie thickness values

The user confirmed (2026-10-29) the template was built for player setup and playback, not
engraving. So the styles start from **Dorico 5.1.60 defaults**, not from the template. The
template is still useful the other way round: style templates can be made by combining a house
style with the template's **player setup and playback** (see §3.4 item 1). No saved Engraving,
Layout or Notation Options defaults exist in `%APPDATA%\Steinberg\Dorico 5` (checked).

**Dorico option names relevant to the brief** (from `finale2dorico/f2d/data/new_project_layout_options.xml`,
which is Dorico 5.1.60's new-project defaults):

| Concern | Dorico file tag (Layout Options unless noted) | Default |
|---|---|---|
| Fixed bars per system | `castingOffOptions/fixNumberOfBarsPerSystem`, `numberOfBarsPerSystem` | false, 4 |
| Systems per frame (page) | `castingOffOptions/numberOfSystemsPerFrame` | 10 |
| Bar number frequency | `barNumberLayoutOptions/barNumberFrequency` (`kEverySystem`, every bar, every n: enum values to confirm) | kEverySystem |
| Bar number interval | `barNumberInterval` | 10 |
| Bar number horizontal position | `barNumberHorizonalPosition` (sic) (`kCenteredOnBarline`; **whether a "centred in bar" value exists is to be confirmed**) | kCenteredOnBarline |
| Bar number placement | `barNumberPlacement` (`kAbove`; below-system / per-staff values to confirm) + `addBarNumbersToStaveProfile` | kAbove |
| Bar number enclosure | `barNumberEnclosureType` | kNone |
| Bar number text style | `barNumbersParagraphStyle` (library paragraph style) | — |
| Large time signatures | `timeSignatureType` (`kNormal`/`kLarge`/…), `timeSignatureGlyphStyle` | kNormal |
| Empty staves | `hideEmptyStavesPolicy` (`kNever`, `kAfterFirstSystem`, `kAllSystems`) | kNever |
| Condensing | `condensingLayoutOptions/enableCondensing` | — |
| Timecode | `timecodeAtStartOfSystem*`, `timecodeFrequency` | kEverySystem, below |
| Page and staff size | `pageSizeAndMarginOptions/pageWidth|pageHeight`, `defaultSpaceSize` (pt) | Letter, 4.96 |
| Vertical justification | `verticalJustificationOptions/*`, `verticalStaveGapOptions/*` | — |

Engraving Options live in `scoreOptions/engravingOptions` and Notation Options in
`scoreOptions/defaultNotationOptionsForFlow`. Fonts, paragraph and character styles, line styles
and playing techniques live in the project library (`scorelibrary.dtn`). Page templates (headers
and footers) live in the layouts/library as well; their location still has to be confirmed.

### 3.3 Fonts

**Decided (2026-10-29): Bravura is the music font for all three styles for now.** The site's
logo font (Leland) is a design choice, not a constraint. The other SMuFL fonts get an
**optional exploration** to see which the user likes, possibly one per score use case. This
exploration (A4b) doesn't block building the styles: switching the music font later is one
Library > Font Styles change, plus a check of the engraving options that depend on the font.

**SMuFL fonts to explore.** These are installed on Windows with SMuFL metadata
(`C:\Program Files\Common Files\SMuFL\Fonts`), so Dorico 5 should accept them; confirm each one in
Library > Font Styles.

| Music font | Look | Possible use |
|---|---|---|
| **Bravura** | Dorico default; bold, traditional European engraving | Classic, Modern |
| **Leland** | MuseScore's font; the quaver in the KP logo is Leland | Modern (ties to your brand mark) |
| **Finale Maestro** | Classic Finale look, the look of the John Williams concert scores | Classic, Film |
| **Sebastian** | Lighter, elegant engraving | Classic, Modern |
| **Leipzig** | Verovio's font, lighter | Classic (secondary) |
| Finale Broadway / Jazz / Ash, **Petaluma** | Handwritten / copyist | Not for these styles (maybe a jazz variant later) |
| **Golden Age** | (to look at) | — |

**Text fonts.**

- Installed: Academico (Dorico default, Century Schoolbook-like), Crimson (the older Crimson,
  not Crimson Pro), MaestroTimes, Finale Copyist Text, Finale Lyrics, plus each music font's
  "Text" companion.
- **From kenpierson.com** (`src/app.css`): headings **Crimson Pro** (serif, with italics), body
  and labels **Manrope** (sans), brand mark **Gilda Display** (display serif, regular weight
  only), mono JetBrains Mono, backup sans Instrument Sans.
- These are not installed on Windows yet. They are open-licence (SIL OFL) Google fonts, so they
  can be installed and embedded in PDFs (check each licence when installing).
- Manrope has no italics, so expressive text (*espressivo*, *dolce*) needs the serif's italic.

**Candidate pairings** (for the specimen review):

| Use | Modern | Classic | Film |
|---|---|---|---|
| Title / headers | Gilda Display (brand) | Crimson Pro or Academico | Manrope Bold / Gilda Display for the cue title |
| Staff labels, bar numbers, rehearsal marks, tempo | Manrope (bar numbers Bold) | Crimson Pro / Academico | Manrope (bar numbers ExtraBold, large) |
| Expressive text, lyrics | Crimson Pro Italic | Crimson Pro Italic / Academico Italic | Crimson Pro Italic |
| Music font | **Bravura** (decided) | **Bravura** (decided) | **Bravura** (decided) |

**Review methods.** A4a covers text fonts and is needed for the styles. A4b covers SMuFL music
fonts and is optional: the same specimen with only the music font changed (Bravura, Sebastian,
Finale Maestro, Leland, Leipzig, Golden Age), shown full score next to part, one sheet per
use case (Modern, Classic, Film).

- Build a specimen project: one page per pairing with a title block, full-score system, part
  excerpt, bar numbers, rehearsal mark, tempo, expressive text, dynamics, lyrics line and
  technique text.
- Generate it with `dorico-build` once Project S has it; before that, use a Dorico project the
  user sets up from a checklist.
- Export PDFs and compare them side by side.
- Criteria:
  - legibility at 3–4 mm staff (full score) and at stand distance (parts)
  - how well the music and text weights match
  - italic quality
  - numeral clarity for bar numbers
  - fit with the brand

### 3.4 What a "style" is in Dorico (deliverables)

1. **Project templates** per style and ensemble preset: full orchestra, strings, wind band,
   chamber and solo. A template = house-style options + library, combined with the player setup
   and playback from the user's existing templates (for example *Full Orchestra Template NEW FULL
   v5*). Created in Dorico with *File > Save as Project Template* (confirm the menu item in
   Dorico 5 and where user templates are stored).
2. **A library export** (`.doricolib`, *Library > Library Manager > Export*) with paragraph and
   character styles, fonts, line styles, playing techniques and page templates, for applying a
   style to existing projects (including converted Finale scores).
3. **Option sets** for Engraving, Layout (full score and part) and Notation Options. Optionally
   *Save as Default* for one style (see Q-A2).
4. **A spec sheet**: the style matrix (§3.6) with the reason and the reference for each row. It is
   the source of truth; templates are generated from it or checked against it.
5. **Tools** (on Project S):
   - `f2d edit apply-style --from STYLE.dorico In.dorico -o Out.dorico` copies options, library
     items and page templates into any project (the "Apply a house style" idea in
     `finale2dorico/docs/UTILITIES.md` §2).
   - `f2d convert --style film|classic|modern` for converted scores.

### 3.5 Phases

**A1: Style facts from Finale (finale-read work).** Add a `style` block to the extractor's output.
musxdom already exposes everything needed:

| Finale data (musxdom) | Gives |
|---|---|
| `options::PageFormatOptions`, `others::Page`, `others::StaffSystem`, `others::StaffUsed` | page, margins, staff size, bars and staves per system (**already emitted**) |
| `others::MeasureNumberRegion` (start/multiple fonts, enclosures, offsets, alignment, `showOnStart`, `showOnEvery`, `incidence`, `hideFirstMeasure`, `showMmRange`) | bar-number style: frequency, position, font, size, bold or italic, boxed |
| `options::FontOptions`, `FontDefinition`, `options::TextOptions` | music font and text fonts per category |
| `options::TimeSignatureOptions` + per-staff time-signature display / staff styles | large time signatures and which staves show them |
| Staff full/abbreviated names, `MultiStaffInstrumentGroup`, staff groups/brackets | label conventions, brackets, group names |
| Page text assignments (headers and footers) | title, page number, cue number placement and fonts |
| `MusicSpacingOptions`, `LineCurveOptions`, `BeamOptions`, `StemOptions`, `TieOptions`, `BarlineOptions`, `MultimeasureRestOptions`, `RepeatOptions`, `TupletOptions` | engraving values to compare with Dorico's |
| Hidden staves per system (`hide_mode`, `StaffUsed`) | empty-staff policy |

**A2: Corpus survey and visual review.**

- Corpus:
  - Film: Avatar 53, The Thing 14 + 6 extensionless, Superman.MUS.
  - Concert: the John Williams concert scores.
  - Classic: Finale's `Music Files/Repertoire` (602 well laid-out pieces) plus any published
    scores the user names (Q-A6).
- Render 2–3 pages per source and write a short checklist per page.
- Measure text sizes and fonts from the vector PDFs (add font/size extraction to `pdf_index.py`).
- Note: *The Thing*'s folder on disk is `Complete Score (pdf"sib)` (with a quote character);
  quote the path carefully in PowerShell. 17 of its scores are Sibelius files, but their PDFs are
  usable.
- Deliverable: `house-style/EVIDENCE.md`.

**A3: Dorico option catalogue and enum discovery.**

- Build a catalogue of every option path with type, default and enum values, from Dorico 5's
  new-project file, the user's projects and the install. It goes into `engine/docs`.
- For unknown enums, run one **reference round**: the user saves one file per setting group.
  Groups:
  - bar numbers: every bar, centred in bar, below the system, boxed, bold
  - casting off: fixed bars per system, 1 system per frame
  - large time signatures
  - empty staves, condensing
  - timecode and markers
  - page templates: cue-number header
  - parts: multi-rests, cues
  - font styles

  Diff each file against a fresh project.
- Confirm where *Save as Default* writes, where user project templates live, and the
  `.doricolib` format.

**A4: Decisions.** A4a text-font specimen review (§3.3), then fill in the style matrix with the
user. A4b (optional, any time): the SMuFL music-font exploration.

**A5: Build.**

- Generate the templates from the matrix with `dorico-build`/`dorico-edit`. Fallback: a step-by-step
  Dorico checklist.
- The user registers them with *Save as Project Template* and exports the library.
- Keep them in `house-style/templates|libraries/`, tracked with dorigit.
- Build `apply-style`.

**A6: Validation.**

- Apply each style to a test set: Avatar 2m2r, a Thing cue, E.T., Asteroid Field, one Repertoire
  piece and one of the user's cues (for example Obi-Wan End Credits).
- Export PDFs through Remote Control and compare them with the checklist.
- Add style-lint checks to the reviewer:
  - options that differ from the style
  - manual layout overrides that break the casting-off rule
  - local fonts instead of paragraph styles
  - hidden bar numbers
- The user reviews printed full score and parts.

### 3.6 Style matrix (draft: starting proposals for the user to confirm)

| Decision | Modern (house) | Classic | Film | Evidence / note |
|---|---|---|---|---|
| Score page | 11 × 17 in (Tabloid) | 9 × 12 or 10 × 13 in; A4/Letter for small ensembles | 11 × 17 in (Avatar used 8.5 × 14) | Survey §3.2 |
| Score staff size | 3.7–4.2 mm for full orchestra, fixed per ensemble preset | 3.0–3.7 mm | 3.2–4.2 mm | Survey |
| Bars per system | Fixed 4 (dense music: manual 2–3) | Natural casting off (≈ 6–8) | Fixed 4, 1 system per page | Avatar median 4; JW concert 6–7 |
| Systems per page (full score) | 1 | as fits | 1 | |
| Bar numbers | Every bar, centred in the bar, below the system, large bold sans | System starts, above the top staff, small; or every bar small italic at the bottom (Hal Leonard) | Every bar, centred in the bar, large bold sans, below the system (option: also above the top staff for very tall scores) | Avatar p. 101, E.T. p. 5 |
| Time signatures | Large, narrow sans, at system-object positions | Normal | Large, narrow sans | FILM_SCORES.md |
| Staff labels | Full on the first system, short after | Full first, short after | Full every page | Avatar, E.T. |
| Player numbers on shared staves | Stacked numbers ("1 3") | "1 2" with abbreviation | Stacked numbers | both |
| Empty staves | Hide after the first system (**Q-A3**) | Hide after the first system | Never hide | Avatar shows all |
| Condensing | On | On | On | Avatar pairs players |
| Concert or transposed | **Concert** (decided) | **Concert** default, transposed layout one switch away | **Concert** (C score) | user 2026-10-29 |
| Fonts | see §3.3 | see §3.3 | see §3.3 | specimen review |
| Header | Title left, page centre, cue/movement right | Title page + outside-corner page numbers, copyright footer | Title left (italic), page centre, cue number large right; composer/orchestrator/timing on first page | Avatar |
| Timecode / markers | Optional | Off | On (start of system, below), markers from video | Dorico timecode options |
| Rehearsal marks | Boxed letters, large | Boxed letters | Boxed, large, plus bar numbers | |
| Dynamics size | Slightly larger than default | Default | Larger | measure in A2 |
| Cue notes | Dorico cues with "Cue (don't play)" label convention | Dorico default | "Cue (don't play):" + dashed line | Avatar |
| Divisi | Dorico divisi with "div. a3" labels | Default | Same | Avatar |
| Parts page / staff | 9 × 12 in, 7.0–7.2 mm | 9 × 12 in, 7.0 mm | 9 × 12 in (or Letter), 7.2 mm, cue-number header, bar numbers every bar | Survey (parts 6.6–7.2 mm) |
| Parts bar numbers | Every system + boxed at rehearsal marks | Every system | Every bar | |
| Spacing / justification | Wider note spacing, generous staff gaps | Default | Wide | measure in A2 |
| Glissando look | Curved (Project B) | Straight | Straight | Q-B5 |

### 3.7 Out of scope

Playback options stay with dorico-hp profiles and the user's playback templates; the style
templates reuse the user's existing player and playback setup. Sibelius files: PDFs only.

### 3.8 Open questions for the user

1. ~~Q-A1 template settings~~: answered. The template is for players and playback; engraving
   starts from Dorico defaults.
2. **Q-A2** Should one style become Dorico's own default (*Save as Default*), or should styles only
   come from templates?
3. **Q-A3** Modern: hide empty staves (shorter scores) or always show them (stable staff positions)?
4. ~~Q-A4 pitch~~: answered. Concert pitch, switchable.
5. **Q-A5** Fonts: music font answered (Bravura for now; SMuFL exploration later, A4b). Still
   open: text fonts (specimen A4a); any commercial text fonts you own that should be included?
6. **Q-A6** Which published scores count as "Classic" references?
7. **Q-A7** Ensemble presets needed for templates?
8. ~~Q-A8 Dorico version~~: answered. Dorico 5.

---

## 4. Project B: ad lib harp glissandi

### 4.1 Goal

Support idiomatic, publish-ready **ad lib harp glissandi** in Dorico 5:

- **Notation**: curved lines (single arcs and multi-wave "ad lib" curves) that look right in
  Engrave and Print modes. Also a wavy variant and the plain straight line.
- **Playback**: every note of the gliss plays, following the harp pedal setting (or the written
  pitch-set cell), along the ad lib shape (up and down), with its pacing and dynamic shape.

### 4.2 The target notation (from the user's references)

- **Steinberg forum image**: one long, smooth, sinuous curve. It starts at an 8va note and wanders
  down over the bar in three or four waves (each lower than the last). No intermediate noteheads;
  the line is thin with an even thickness.
- **MuseScore image** (top harp staff):
  - A written **pitch-set cell** first: seven beamed 32nd notes rising, the first octave written
    out.
  - Then **"gliss. ad lib."** and a gently curved line that arcs over the bar to a
    **parenthesised target note**.
  - The line continues in arcs through more parenthesised turning points and ends on a tied high
    note, with a hairpin underneath.
  - The lower half of the image shows the curve built from a slur with its Bézier handles pulled,
    the classic engraver's workaround.
- **harpnotation.com (single glissando)**:
  - Thin straight line; "gliss." optional.
  - Start and end notes in parentheses if not accented, or omitted if approximate.
  - Show the notes used with a **pedal diagram** or by writing out the **first octave in 32nds**.
  - Add the duration if unclear.
  - Both hands can gliss, in the same or opposite directions; the right hand is limited in the low
    register.
  - Ad lib and curved lines aren't covered there.

**Still needed from the user (ask at implementation start; don't guess):**

1. The user's **notated ad lib harp glissando example** (image or PDF, and the source file if any).
2. The user's **"notational interpretation"** of it.
3. Which **harp VI** they use (and whether it has gliss samples or keyswitches).
4. ~~Dorico version~~: answered. Dorico 5.

### 4.3 Variants to support

| ID | Variant | Look | In Dorico 5 |
|---|---|---|---|
| G1 | Straight single gliss | Straight line, optional "gliss." | Native (`GlissandoLineEventDefinition`, `kGlissandoLineType` kFlatLine); the converter already writes it |
| G2 | Wavy gliss | Straight path, trill-like wiggle | Native `kWavyLine`. A true **sawtooth** needs Dorico 6.2.30+ (gliss "Line style" property): later |
| G3 | Curved single arc | One smooth arc between two notes | Not native (forum consensus) |
| G4 | Ad lib multi-wave curve | Smooth curve through turning points, across bars | Not native |
| G5 | Pitch-set cell + G3/G4 | Beamed 32nd cell + "gliss. ad lib." + curve + parenthesised notes + hairpin | Partly (the cell and text are native; the curve isn't) |

### 4.4 Prior evidence in this repo

- `dorico-hp/research/hp-engine.md` (Harp): Finale Human Playback **extrapolates the written cell**.
  The notated 7-note cell in 32nds was played as 57–104 notes, repeated up through the range,
  evenly spaced in one bar and **accelerating** in the other (0.29 → 0.03 crotchet apart). That is
  a measured pacing model.
- `dorico-hp/research/dorico-integration.md`: gliss playback is "Dorico for the line; Apply only for
  timing refinements". Apply cannot add notes.
- `finale2dorico`:
  - Glissando encoding (from/to note + block instance IDs; can cross voices and staves).
  - Harp pedal diagrams and changes are already written.
  - The corpus has 969 glissandi plus 327 `tabSlide` straight glissandi.
  - Willow and Trex contain harp glissandi.
- Dorico behaviour (docs and forum; to confirm in tests):
  - Harp gliss playback follows the **harp pedal diagram**.
  - Per-line playback type: Auto / Continuous / Chromatic / White notes / None.
  - Playback option `glissandoPlaybackOptions.delayedStart`.
  - No "hidden note" property. Workarounds: hide notehead and stem, colour alpha, suppress
    playback, slash regions, players excluded from layouts.
  - Curved glissandi: modified slurs (visual only), or two straight glissandi with a stemless
    turning-point note.

### 4.5 Design options

**Visual (V)**

| ID | Approach | Pros | Cons / unknowns |
|---|---|---|---|
| V1 | **Slur-based curve**: one slur per wave segment, chained through turning-point notes. The tool computes Bézier control points for smooth joins (Catmull-Rom → cubic Bézier) | In Dorico (Engrave and Print); the classic engraver technique | Slur geometry may be offsets from Dorico's default (**R1**); slur thickness tapers; slurs affect playback (legato) |
| V2 | Native gliss line made invisible (colour alpha 0) **plus** V1 for the look | Keeps Dorico's gliss playback and semantics | Does the gliss line accept colour/alpha? (**R3**) |
| V3 | Sawtooth via a custom line style on a native gliss | Fully native | **Dorico 6.2.30+ only**: later |
| V4 | Post-process exported SVG/PDF for print | Exact curves | Print only; fallback |

**Playback (P)**

| ID | Approach | Pros | Cons / unknowns |
|---|---|---|---|
| P1 | **Native harp gliss playback between turning-point notes**: a chain of gliss lines (low → high → low ...) following pedals | Native, pedal-aware, in the harp's own staves | Note spacing within segments is Dorico's (**R4**); hidden turning points may change spacing (**R2**) |
| P2 | **Shadow playback player**: a second harp player excluded from every layout gets written-out notes (pedal-aware pitches, HP-style pacing, velocity following the hairpin); the visible gliss is set to suppress playback | Full control of every note | Do excluded players play? (**R5**); keep in sync by re-running the tool |
| P3 | dorico-hp Apply refinements (velocity, timing) on top of P1/P2 | Reuses dorico-hp | Refines existing notes only |
| P4 | VI gliss samples via expression map | Most realistic for some libraries | Library-specific (§4.2 item 3) |

**Recommended MVP:** V1 + P1, then P2 as an "exact ad lib" option, then P3/P4.

### 4.6 Proposed workflow and tool (`harpgliss`, an editor command on `dorico-edit`)

1. **Author in Dorico with native items:**
   - start note and end/turning-point notes (parenthesised where wanted)
   - plain gliss lines between them
   - optional cell, pedal diagram, "gliss. ad lib." and hairpin
   - an ad lib marker: a dedicated hidden playing technique, or a bar range on the command line
2. **Run** `f2d edit harpgliss In.dorico -o Out.dorico [--style curve|wave|straight]
   [--playback native|shadow] [--pacing even|accel|decel|hp]`.
3. **The tool:**
   - reads the gliss chain and pedals
   - builds a **gliss spec**
   - writes the V1 slurs
   - sets the gliss lines' appearance (V2) and playback type
   - for P2, refreshes the shadow player's notes
4. **Re-runnable and removable** through `dorico-edit`'s tool-owned tagging. Reports use the shared
   findings schema.
5. **Converter link (later):** finale-read detects curved harp glissandi in Finale files (slur or
   custom-curve shapes plus "gliss." text on harp staves) and emits the same gliss spec.

```text
GlissSpec
  harp_player, staff(s) / hand(s)
  start: note ref (pitch, time), parenthesised?
  points: [ {time, pitch, kind: turn|target|end, visible: bool, parenthesised: bool} ]
  pitch_set: pedal setting at start (HarpPedalEventDefinition) | explicit cell notes
  shape: straight | wavy | curve | wave(n per bar) ; tension 0..1 ; thickness
  pacing: even | accel | decel | hp-model(params) ; notes_per_second range
  dynamics: follow hairpins/dynamics | explicit velocity curve
  text: "gliss." | "gliss. ad lib." | none
  playback: native | shadow | none ; delayed_start
```

### 4.7 Phases

- **B0 Inputs.** §4.2 items 1–3 from the user, written in as acceptance criteria.
- **B1 Evidence.**
  - Survey the Finale corpus for harp glissandi (smart shapes on harp staves near "gliss"/"ad lib"
    text; Avatar, The Thing, John Williams) and render the PDF pages.
  - Collect 5–10 published examples.
- **B2 Dorico 5 reference round** (combine with A3):
  - **R1 Slurs**: shapes dragged in Engrave mode. Learn whether offsets are absolute or relative
    and their units; also style, thickness, cross-voice slurs, and slurs to hidden or other-voice
    notes.
  - **R2 Hidden turning points**: hide notehead/stem/ledger lines/accidental, alpha 0, rest
    removal, and the effect on spacing.
  - **R3 Gliss lines**: every `kGlissandoLineType`, the playback-type property, colour/alpha.
  - **R4 Harp gliss playback**: export MIDI and measure pitches, timing, `delayedStart`, mid-gliss
    pedal changes, hand-to-hand and grace-note glissandi (with the shared `midi` module).
  - **R5 Shadow player**: do players excluded from all layouts play? Does suppress playback mute
    the visible gliss?
  - **R6 Pitch-set cell**: the idiomatic Dorico way to write the 32nd cell.
- **B3 Curve geometry.** Smooth multi-segment curves, even-thickness look, collision avoidance,
  system breaks, cross-staff segments. Prototype with an SVG preview first.
- **B4 Build** `harpgliss` on `dorico-edit`: V1 + P1, then P2.
- **B5 Validation.** Visual check in Engrave and Print modes against the references; playback via
  MIDI export (every pitch-set note present, pacing as chosen); the user listens with their harp VI.
- **B6 Extras.** Converter support, dorico-hp gliss profile options (P3), VI gliss samples (P4),
  sawtooth when the target moves to Dorico 6.2.30+ (V3).

### 4.8 Open questions for the user

1. The example, interpretation and harp VI (§4.2).
2. **Q-B2** Turning points visible (parenthesised) or invisible (curve only)? Probably both, per
   gliss.
3. **Q-B3** Is a playback-only harp player acceptable in projects (P2)?
4. **Q-B4** Default ad lib pacing: even, or Finale HP-style accelerating?
5. **Q-B5** Should the house styles fix the gliss look (for example Modern = curved, Classic/Film =
   straight)?

### 4.9 Started 2026-11-01: the user's direction and the reference MIDI

**Direction (user, 2026-11-01).** This supersedes parts of §4.1–4.5:

- Notation: **sawtooth** and **wavy** ad lib glissandi (not curved slurs). Upgrading to
  **Dorico 6** is acceptable for this. Dorico **6.2.30** added a per-line **Line style** property
  for glissandi, plus an engraving option *Draw wiggly glissando lines using* (project default).
  Built-in wiggly lines exist; a sawtooth may need a custom line style (to check, R3).
- **Playback first.** Notation will follow a house style that is not defined yet (Project A).
- Generated playback may use **hidden notes** and/or a **hidden staff**.

**Reference file:** `C:\Users\kspie\Documents\HPCaptures\midi\trex-harp.mid`. The user crafted it by
ear from the audio recording. It has three harp tracks, but each ad lib gliss stands for **one
harp**: the tracks only let sweeps overlap. PPQ 1024, Finale-style export (tempo event every bar),
♩ = 176.32 (dotted crotchet ≈ 117.5; one quaver ≈ 170 ms). Bars 3–17 and 22–25 are 6/8, the rest
12/8. MIDI bar numbers have no pick-up, so they match the description below.

How the score notates them (user's description; handwritten score):

| Gliss | Score start | Score end | Text / line |
|---|---|---|---|
| 1 | m14 beat 1: C6 (2 ledger lines above), "open beam (single)" | m18 beat 1: quaver with no notehead (stem + flag) | "gliss. ad lib.", wavy line |
| 2 | m26 beat 1: dotted minim E5, no visible stem (maybe a scan issue) | m28 beat 4 (12/8): quaver on B4 with an X head (or no head) | "gliss. ad lib.", wavy line |

Both have a pedal diagram before them.

**What the MIDI does.** Tools in the scratchpad: SMF read by `doricohp.smf`; times in quavers.

Gliss 1 is a clean **triangle wave**: down/up sweeps alternate, each one ending on its turning note.

| Sweep | Pitches | Quavers (from m14) | Notes | Speed |
|---|---|---|---|---|
| lead-in ↑ | B3 → C7 | 3.0–6.0 (m14 beat 2 → m15 beat 1) | 23 | 45 n/s |
| ↓ | C6 → G♯3 | 6.0–9.6 | 17 | 28 n/s |
| ↑ | G♯3 → C6 | 9.5–13.1 | 17 | 28 n/s |
| ↓ | C6 → E3 | 13.0–16.3 | 20 | 36 n/s |
| ↑ | E3 → A5 | 16.25–20.3 | 18 | 26 n/s |
| ↓ | A5 → G♯3 | 20.25–24.0 (= m18 beat 1) | 16 | 25 n/s |

- Pitch set of the wave: C C♯ E F♯ G♯ A B, i.e. pedals **D♭ C♮ B♮ | E♮ F♯ G♯ A♮**.
- The lead-in uses a **different** set (C C♯ E F G A♯ B: F♮ G♮ A♯). So either it's separate
  notation with its own pedals, or a pedal change sits on m15 beat 1 (open question).
- The wave itself starts at **m15** beat 1 on C6, not m14. In m14 only the fast lead-in plays,
  starting on beat 2. The notated C6 at m14 beat 1 doesn't sound (open question).

Gliss 2 (m26 beat 1 → m28 beat 4) is mostly a triangle wave, with one stretch where the sweeps
**overlap**: three rising sweeps in a row, sawtooth-like.

| Sweep | Pitches | Quavers (from m26) | Notes | Note |
|---|---|---|---|---|
| ↑ | G4 → F6 | 0.0–2.1 | 14 | fast (39 n/s); F6 is outside the set (F♯ elsewhere) |
| ↓ | E6 → A♯3 | 2.0–5.75 | 18 | |
| ↑ | A♯3 → G5 | 6.0–8.8 | 13 | |
| ↑ | C♯4 → G♯5 | 8.25–10.5 | 12 | overlaps the sweep before; **velocity 64** (track 3) |
| ↑ | G3 → A♯5 | 9.75–12.7 | 17 | overlaps again |
| ↓ | E6 → A♯3 | 12.5–14.9 | 18 | fastest (45 n/s) |
| ↑ | A♯3 → A♯5 | 15.0–17.8 | 15 | velocity 64 |
| ↓ | A♯5 → G3 | 17.75–20.3 | 17 | |
| ↑ | G3 → F♯6 | 20.25–24.0 | 21 | velocity 64; top note 74 |
| ↓ | F♯6 → G3 | 24.0–27.1 | 21 | |
| ↑ | G3 → A♯5 | 27.0–30.1 | 17 | |
| ↓ | A♯5 → G3 | 30.0–33.05 (= m28 beat 4) | 17 | |

- Pitch set: C♯ D♯ E F♯ G G♯ A♯, i.e. pedals **D♯ C♯ B♭ | E♮ F♯ G♮ A♭**.
- A lead-in in m25 rises B4 → G♯6 with yet another set: C♮ D♭ E♮ F♮ G♯ A♭ B♮. Its repeated G♯5
  is the harp's **enharmonic double** (G♯ + A♭), which a pedal-aware generator must reproduce.
- The **notated pitches are not played**: the start E5 is reached mid-sweep (the MIDI starts on G4)
  and the end "B4" sounds as G3. So the start and end notes mark **time** (and a rough register),
  not exact pitches. For gliss 1 the start C6 does match the first wave note.

**Playback model taken from both examples** (parameters for the generator):

| Parameter | Observed |
|---|---|
| Shape | Turning points (time, pitch). Mostly alternating up/down; occasional overlapping same-direction sweeps |
| Range | About G♯3/E3 up to C6/F♯6, roughly 2–2.5 octaves. The outer points vary from wave to wave |
| Sweep length | 2.1–4.1 quavers (0.36–0.70 s), **not locked to beats**; the last sweep lands exactly on the end note |
| Pacing inside a sweep | **Even** (constant step); the **last step into a turn is ~1.5–2× longer** (a small hang) |
| Speed | 25–36 notes/s typical; lead-ins and some sweeps 39–45 n/s |
| Turns | The turning string sounds **twice** about 10–20 ms apart (end of one sweep, start of the next) |
| Pitches | Every string of the pedal set, enharmonic doubles included; no gaps (a small exception at the gliss 1 top: A5 → C6 skips B5) |
| Note lengths | Step length, no overlap, last note longer. The harp VI rings anyway |
| Velocity | Flat 127 (tracks 1 and 2); 64 on track 3. CC7 alternates between 95 and 110 per track (meaning to confirm) |
| Keyswitch | Note 2 (D-1 in this naming), velocity 64, ~8 ms, before some sweeps and at m1. Probably the harp VI's articulation switch (to confirm) |
| Instrument | Program 46 (GM harp), bank 0/0 |

**Playback approaches, updated for Dorico 6** (detailed version of P1/P2 in §4.5):

| ID | How | Pros | Cons / unknowns |
|---|---|---|---|
| P1a | **Hidden voice on the harp's own staff**: turning points as hidden notes (head, stem and rests hidden) joined by native gliss lines (playback Auto, so it follows the pedals). The visible wavy/sawtooth line is set to playback None | Native, pedal-aware, one instrument | Dorico's pacing (even? `delayedStart`?); turning points off the beat need odd rhythms; hidden items may shift spacing; overlaps need a 2nd hidden voice; one velocity per gliss |
| P1b | P1a on a **hidden staff** (extra harp player excluded from every layout) | Visible staff stays clean; no spacing side effects | Same pacing limits; a second harp instrument to keep in sync |
| P2 | **Written-out notes on a hidden staff**: the generator writes every string (grid rhythm) and dorico-hp's play offsets move each note to its exact time, with per-note velocity | Exact: can reproduce the crafted MIDI note for note; overlaps and dynamics are free | Needs the S5 edit layer (add notes); pedal changes are the tool's job |

Suggested order: build the **generator** (spec → notes, plus "fit" from crafted MIDI, plus a MIDI
writer for listening) now: it needs neither Dorico nor S5. Then do a small **Dorico 6 reference
round**: P1a/P1b entered by hand, MIDI exported and compared with the generator and with
`trex-harp.mid`. That shows how close native playback gets, and therefore whether P2 is worth the
edit-layer work.

**User's answers (2026-11-01):**

- The m14 rising sweep is **separate notation** with its own pedals; the gliss 1 wave runs m15
  beat 1 → m18 beat 1 in practice. The user will check the bar numbers in the score. The m25
  lead-in to gliss 2 is treated the same way.
- Overlapping same-direction sweeps (the gliss 2 burst) **are intended**. The level differences
  (velocity 64 on track 3, CC7 95/110) are **crafting leftovers**: generated levels should be even,
  shaped by the score's dynamics.
- Note 2 (keyswitch) is an expression-map leftover: **ignore it**; the generator never emits it.
- Build the generator + fit first.

**Done 2026-11-01: the generator** (`doricokit.midi`, `doricokit.harp`, `doricokit.gliss`; API in
`engine/docs/CHANGES.md`, tests in `engine/tests/python/test_gliss.py`):

- `fit` turns played notes into a spec: pedals inferred, sweeps with strings, times, hang,
  skipped strings and layer. Regenerating from the spec reproduces **gliss 1: 88/88 notes at
  0 ms**, **gliss 2: 201/202** (the crafted F6 lies outside the pedals and comes back as F♯6).
  It also flags crafting slips: skipped strings A3 and B5 (gliss 1), G5 (gliss 2), and the F6.
- `plan` writes a **new** ad lib gliss from a sketch: start/end time, pedals, low/high, first/last
  pitch, sweep length, optional U/D pattern with overlapping same-direction sweeps, hang, repluck,
  velocity/breakpoints, seed. Re-planned from the fitted stats, gliss 2 comes out with 198 notes at
  28–40 notes/s (crafted: 202, 25–42).
- Listening files were written to the session scratchpad, at the source bar positions with
  velocity 127 (as crafted): `trex-gliss{1,2}-planned-seed{1,2}.mid`, plus the fitted specs as JSON.
  They can be regenerated with `uv run python -m doricokit.gliss fit <trex-harp.mid> --start 15
  --end 18 --replan OUT.mid --velocity 127 [--seed N]` (gliss 2: `--start 26 --end 28+9/2`).

**After listening (user, 2026-11-01):**

- **Principle: mimic what a live harpist physically does and can do**, especially at turns and in
  overlapping glissandi. The generator plans that way; `physical_checks` flags anything else.
- **Turns: the turning string sounds once** (`repluck` now off by default). The next sweep starts
  on the neighbouring string one regular step later. The crafted reference re-plucks every turn,
  so `fit` now reports those.
- The slightly longer last step into a turn (`hang`, about 1.2–1.5) is fine.
- Hands: an up/down wave stays in one hand; an overlapping restart in the same direction is taken
  by the other hand, so at most two sweeps sound at once.
- The examples sound good overall. **Preferred: gliss 1 seed 1, gliss 2 seed 2** (the two gliss 2
  seeds were close). Both are kept as fixtures, `engine/tests/gliss/trex-gliss{1,2}-pick.json`
  (plan arguments + resulting spec), and a test checks they are reproduced exactly. Re-planned
  without the re-plucks: gliss 1 88 notes, gliss 2 193 (same turning points as the versions heard).
- Still to decide, when real harpist limits matter: register limits per hand (harpnotation.com:
  the right hand is limited in the low register), the fastest playable sweep, and travel time
  when a hand jumps back to restart. Not modelled yet; no numbers invented.

**On hold until the user has Dorico 6 (user, 2026-11-01).** The playback model is done for now.
Resume when the user has upgraded to Dorico 6 (6.2.30+), and then work on **both**:

- **Notation**: sawtooth and wavy ad lib gliss lines (the per-line *Line style*, a custom line
  style if no built-in sawtooth fits), "gliss. ad lib.", start/end note conventions (headless,
  X, parenthesised), and the pedal diagram, all toward the house style (Project A).
- **The link between notation and playback**: read the notated gliss (start/end notes, line,
  pedals) and turn it into the planned playback, via hidden notes or a hidden staff in the
  project (P1a/P1b/P2 above).

When resuming, ask the user which Dorico 6 version they have, then start with the reference
round below.

**Next (once on Dorico 6):**

1. The user listens to the re-planned picks without re-plucked turns
   (`v2-gliss1-seed1.mid`, `v2-gliss2-seed2.mid`, in the session scratchpad's `listen/` folder).
2. **Dorico 6 reference round** for P1a/P1b: how Dorico paces a native harp gliss, what playback
   type None does on a gliss line, whether hidden notes and rests change spacing, and whether a
   player excluded from every layout still plays. Compare with `gliss.compare`.
3. Glue: read the start/end notes, gliss line and pedal mark from a project through
   `doricokit.model` + `timeline`, then plan. Writing the result into the project (P2) waits for
   the S5 edit layer.

---

## 5. Project C: VI playback profiles and expression maps

*Added 2026-11-01 (user request). Started for SWAM in the dorico-hp session:
`dorico-hp/research/vi/swam.md`.*

### 5.1 Goal

Expression maps (and percussion maps) that make each virtual instrument play as well as it can
from correctly written notation, with Dorico and with dorico-hp's Apply, optionally in
**style variants** (e.g. classical vs jazz flute, film vs chamber strings). That needs a
rigorous understanding of how each VI responds: controllers, velocity, legato detection,
keyswitches, latency, release, built-in humanising.

### 5.2 One session per VI family

Each session gets the same brief (5.3) and writes `dorico-hp/research/vi/<family>.md`:

| Family | Maps today (`AppData/Roaming/Steinberg/Dorico 5/EndpointConfigs`) | Notes |
|---|---|---|
| SWAM Woodwinds 2.8 | 17 `SWAM - <instrument>` | started 2026-11-01; HP WW states decoded; measured from Cubase renders (kit in HPCaptures\\swam, `vi/swam.md`) |
| SWAM Brass | SWAM - Brass/Horns/Trumpets/Trombones/Tuba/Euphonium | separate plug-ins (`SWAM Trumpets` …) |
| SWAM Strings 3 | SWAM - Violin/Viola/Cello/Double Bass, SWAM Solo Strings | CC19 = vibrato rate and bow force in the user's instances |
| Infinite Brass (IB) | 6 `IB - …` | |
| Infinite Woodwinds (IW) | 8 `IW - …` | |
| LASS / LASS 3 | 3 LASS + `LASS 3 - Full Strings` | constant look-ahead → latency-reporter |
| Spitfire (Harp Redux, tuned percussion) | 10 `Spitfire - …` | |
| CinePerc / CineSamples | 14 + 2 | percussion maps |
| Pianoteq | 5 | velocity dynamics |
| Others | Joshua Bell Violin, Nashville Scoring Strings | |
| Not yet configured | (user to list) | Berlin Strings and VSL are used in the ET score via custom `pt.user.*` techniques |

### 5.3 Session brief

1. **Inventory**: the user's maps for the family (`dorico-hp/tools/dorico_maps.py`), plug-in
   states and MIDI mappings saved in projects (`supplementary_data/vstaudioengine/enginedata`,
   readable XML for SWAM), factory presets, the vendor manual.
2. **Behaviour**: what every controller, velocity range and keyswitch does; legato/staccato
   detection (gap and overlap thresholds); attack latency and release; built-in randomness.
   Measure with rendered tests where the manual is silent (Dorico test files the user
   opens + MIDI/audio export, or MIDI straight into the plug-in).
3. **Gaps**: which Dorico playing techniques/articulations the map ignores, which controllers
   it sends that mean something else (SWAM CC14 = Main Volume, found 2026-11-01), conflicts.
4. **Proposal to the user**: map changes (technique entries, conditions, length/velocity
   factors, init values), plug-in preset changes, and dorico-hp library-profile values
   (`dorico-hp/doricohp/data/libraries.toml`), each with the evidence. Style variants as
   alternative maps or presets.
5. **Deliver** (after the user's OK): edited maps as `.doricolib` files for the user to import,
   never written into the user's projects directly; Apply profile updates; tests.

### 5.4 Shared capabilities it needs (engine)

- A reader for expression/percussion maps (exists in dorico-hp `playback.py`, slated for
  `dorico-playback`, S6) and a **writer** (new: edit layer S5).
- A **plug-in state reader** for `enginedata` (per-slot plug-in, preset name, and for SWAM the
  MIDI mapping), so Apply can check what a CC means before writing curves on it.
- Render-and-measure helpers (MIDI in, audio/MIDI out) shared with dorico-hp's captures.
  **Built 2026-11-01**: `engine/crates/vi-render` (headless VST2 host, Windows exe run from WSL:
  render timed MIDI to WAV, list parameters with display text, get/set state chunks, sweep a
  parameter, open/screenshot the editor) + `doricokit.virender` (plug-in states per rack slot
  from `enginedata` incl. each as a ready `.vstpreset`, DLL lookup, render/info/sweep). Works with
  Pianoteq, SWAM v3 brass and SWAM Strings 3 (measured automatically); Kontakt VST2 stalls, Kontakt 7
  is VST3-only, so Kontakt libraries go through Cubase (inventory: `dorico-hp/research/vi/inventory.md`). The
  installed SWAM Woodwinds 2.8.1 build renders silence, so woodwinds are rendered in Cubase from a
  kit made by `dorico-hp/tools/swam_measure.py` (see `dorico-hp/research/vi/swam.md`).
  VST3 hosting not built. Kontakt route (2026-11-01): `doricokit.cubase.TrackArchive` generates
  Cubase 13 track archives (Kontakt 7 tracks cloned from a user-exported sample, any Dorico
  Kontakt state, MIDI parts), `dorico-hp/tools/vi_measure.py` builds one track per Kontakt slot
  with tests chosen from each channel's expression map, and analyses the batch-exported WAVs.

### 5.5 Open questions for the user

- Which VIs are "not yet configured" and should get sessions.
- Order of the sessions (suggested: SWAM Woodwinds → SWAM Strings → SWAM Brass → LASS 3 →
  IB/IW → Spitfire Harp → percussion).
- Style variants: which styles matter per family.

---

## 6. Project D: score configuration manager and project templates

*Added 2026-11-01 (user request). Planning only.*

### 6.1 Goal

Manage scores and their configuration **outside Dorico**: see and apply expression maps,
percussion maps, custom playing techniques (and their playback-technique links), custom lines,
playback templates and options, house-style settings; create and manage **project templates**;
compare configurations across projects; keep the user's own libraries in one place.

### 6.2 What Dorico keeps where (first look, 2026-11-01)

| Where | What |
|---|---|
| In each project (`score.dtn` library, `scorelibrary.dtn`) | expression/percussion maps used, playing-technique appearances + playback techniques, lines, text/paragraph styles, options (engraving, layout, notation, playback) |
| `supplementary_data/vstaudioengine/enginedata` in each project | plug-in rack, plug-in states (2–25 MB), mixer |
| `%APPDATA%\Steinberg\Dorico 5\EndpointConfigs\` | 78 saved endpoint configurations (map + plug-in per channel) |
| `%APPDATA%\Steinberg\Dorico 5\PlaybackTemplateSpecs\` | 5 user playback templates (Custom, Full Orchestral LASS3 + IB / + IB-IW / + SWAM, SWAM Solo Strings) |
| `%APPDATA%\Steinberg\Dorico 5\preferences.xml` | application preferences (~250 values) |
| Same folder | `DocumentWindowPositions.ini`, `recentFileList.xml`, `remoteclients.xml` (Remote Control), logs, AutoSave |
| Not present yet | user library defaults ("Save as Default" for options/styles), custom keyboard shortcuts: find where Dorico 5 writes them when used |
| `Documents\Dorico Projects\` | the user's templates are ordinary projects ("Full Orchestra Template NEW FULL v5", "… TEMPLATE WORK", "childrens choir template") |
| Dorico install | factory library (`scorelibrary.xml`), factory templates and maps (read, never shipped) |

### 6.3 Shape

A tool in the Score Workbench app (§2.11) built on the engine's read model and edit layer:
list a project's configuration; diff it against another project or a template; apply a chosen
set (maps, techniques, lines, options, endpoint configuration) to a **copy** of a project;
build templates from a project (strip music, keep setup); keep a versioned "configuration
library" (dorigit can version it). Shares the map reader/writer with Project C and the
house-style applier with Project A.

### 6.4 Phases

D1 inventory of everything above across the user's projects (read-only); D2 a
"configuration report" per project; D3 diff between projects/templates; D4 apply to a copy
(needs S5 edit layer); D5 template builder; D6 Dorico preferences/user-library management.

### 6.5 Open questions for the user

- Which configuration items matter most first (maps? techniques? templates?).
- Templates: one master template with variants, or several independent ones?
- Should Dorico's application preferences be managed too, or only read and documented?

---

## 7. Project E: stage placement and audio-chain profiles

*Added 2026-11-01 (user request, verbatim in §10). **Started the same day**: tool `stagecraft/`
(Rust), E1 inventory, E2 capture pilot and E3 capture library done (VSS2 simulates a Decca tree geometrically: per output, the centre and own-side microphone as delayed, scaled, filtered copies of the source, then a fixed reflection pattern with a faint treble shimmer); live state and findings in `stagecraft/docs/STATUS.md`. Project C
covers how each VI **plays** (maps, controllers); Project E covers where each VI **sits** (the
audio chain that places it in a space). They share the per-VI-family research.*

### 7.1 Goal

A set of **audio-chain profiles** for every VI the user uses, so mixed libraries (LASS, Infinite
Brass/Woodwinds, Sample Modeling brass, SWAM, Pianoteq, Spitfire, Kontakt libraries …) sound like
one ensemble recorded in one space, for orchestral and other styles. A profile says, per VI and
instrument, what to set inside the VI and what chain to put after it, for a chosen **space**
and **seat**. Virtual Sound Stage 2 (VSS2) has done most of this so far; it is VST2-only, no
longer developed (free download: https://www.musehub.com/plugin/virtual-sound-stage), and Dorico
on Mac cannot load VST2, so it is captured and then retired (decision below).

### 7.2 Decisions (user, 2026-11-01)

| Question | Answer |
|---|---|
| Where the mix happens | **Both.** Dorico for writing/mock-up playback; final mixes in a DAW from stems. Stems are exported **"in place"**: no panning and (generally) no effects per track, only the final room reverb and mastering plug-ins. So the per-track placement chain lives in the DAW for final mixes, and in Dorico for writing |
| DAW | **Cubase** on this machine (main for now); **Logic Pro** on some projects; could change |
| VSS2 | **Capture, then retire**: record each VSS2 preset as impulse responses, rebuild with light plug-ins + IRs, A/B against VSS2 until they match, then drop it |
| Spaces | **Film scoring stage, concert hall, chamber/small hall, studio (jazz/pop)**, plus **concert band** (between concert hall and small hall) with two styles for the same band work: **wind ensemble** and **military band**. The user can provide example recordings of the desired sound |
| Plug-ins | **Owned + free, light (low CPU) first.** Paid ones only listed as options, with evidence |
| Tool name | **stagecraft** (`stagecraft/`, Rust crate in the root workspace) |
| Sends on VSS2 channels | **Off** in Harry Potter Cues Plus 5 + LASS3 (user checked in Dorico), though each keeps a per-section level; the empty slot-2 inserts on the brass outputs are leftovers (Dorico shows one VSS2 per strip) |
| Brass library / LASS send | The Kontakt brass racks are **Sample Modeling brass**; LASS 3's send to the early-reflection Altiverb is **on** (user, 2026-11-01) |
| vi-render input audio | Added by the stagecraft session (user's choice, 2026-11-01) |
| E2 listening (blind A/B, live VSS2 vs captured IRs) | **"I do not hear much difference … any difference is EXTREMELY subtle."** Capture-then-retire goes ahead. The user is curious what adding VSS2's reflection motion back would cost (work and CPU) against what it adds: investigate as the work proceeds (first answer in `stagecraft/docs/STATUS.md`, E3) |
| Flute/piccolo treble boost (VSS2 Air −100) | **Intentional**: makes them "pop out" of the mix as live players do. Open to exploring ensemble balancing as a better way (§7.11) |
| Placement beyond VSS2 (E5, 2026-11-02) | Build: **real arrival times**, **physical air absorption + a separate brightness control**, **sections as wide sources**, **free microphone plans + bleed**, **a reflection layer** (per-seat sends), **floor/first reflections**. Instrument radiation patterns: not chosen for now |
| How stages are tuned (2026-11-02) | A **visual editor page** now. Later it joins the other performance tools (dorico-hp etc.) in one **Rust desktop app** like dorigit, i.e. the **Playback** app of §2.11 (Tauri + Svelte, shared UI kit): so the editor is a thin page over JSON calls into the Rust engine, which become app commands later |
| Two Altiverbs | **Intentional.** The reverb on the FX channel is the **depth layer**: each section's send level is dialled in so the front is drier and the back wetter. The reverb on the master Out is the **glue**: the reverb of the whole space, applied to the full output. Profiles keep this two-stage design (per-seat send level = part of the seat; master reverb = part of the space) |

### 7.3 What exists today (evidence, 2026-11-01, read-only)

Read from `supplementary_data/vstaudioengine/enginedata` (mixer XML + plug-in state chunks).

- **Harry Potter Cues Plus 5 + LASS3** (and *Harry Potter Cues*): VSS2 (`VirtualSoundStage2_x64`,
  VST2 fxID `Para`) on **every instrument channel** (45; pre-insert slot 1), SWAM, Kontakt
  (incl. aux outputs) and Pianoteq alike. FX channel "Fx Reverb": Altiverb 7 + REVerence
  (bypassed). Out: Altiverb 7 (slot 1) + REVerence (bypassed) + Compressor (slot 4).
  The two Altiverb states: **Todd-AO – California USA, "10.7m wide s-s"**, Dry/Wet 0.50, and
  **Todd-AO, "3.5m s-s"**, Dry/Wet 0.45; "Stage Positions On" = 0 in both. Which state belongs
  to which channel is not mapped yet (E1). Per-channel send levels not read yet (E1).
- **Full Orchestra Template NEW FULL v5** and **FLYING SAILOR**: no VSS2; only Compressor +
  REVerence on Out. The main template has no placement chain yet.
- **VSS2 state in a project**: a VST2 `CcnK/FBCh` chunk; inside, a JUCE-style tagged binary
  that includes the preset it came from, e.g.
  `C:\Users\kspie\OneDrive\Documents\parallax-audio\Presets\SWAM\Woodwinds\Flute 1.vss2preset`.
- **VSS2 preset library**: 198 `.vss2preset` files in
  `C:\Users\kspie\OneDrive\Documents\parallax-audio\Presets` (`/mnt/c/...` from WSL): SWAM
  (woodwinds 18, brass 15, strings 7, percussion 6), Samplemodeling Brass 11, LASS 5,
  Cinematic Strings 2, 8dio Adagio, Cinesamples Cinebrass Core/Pro, EastWest Hollywood
  Brass/Strings, Orchestral Tools Berlin Woodwinds, ProjectSAM True Strike, Spitfire
  (harp, percussion, solo strings), VSL (brass, percussion, strings, woodwinds).
  Format: zlib-compressed XML
  `<Preset PresetData="…" Instrument="Flute 1" Library="…" Microphone-Position="Default"/>`;
  `PresetData` is JUCE base64 (leading `608.` = byte count), not decoded yet.
  Note: the SWAM presets say `Library="Vienna Instruments Special Edition"` (VSS2 has no SWAM
  source profile, so a VSL profile stands in). VSS2's "Library" setting compensates for the
  library's own recording perspective; that is the "source profile" idea in 7.4.
- **VI-internal settings already known**: SWAM maps send CC91 = 0 (built-in reverb off),
  `dorico-hp/research/vi/swam.md`. LASS 3 look-ahead latency: `latency-reporter/README.md`.

### 7.4 What places an instrument (the model the profiles follow)

In signal order. Each layer is data in the profile; hosts get generated settings.

| Layer | What it does | Typical light implementation |
|---|---|---|
| 0. VI-internal | Turn off or set the VI's own room/stereo/distance processing: SWAM reverb (CC91=0) and stereo/room settings, Infinite Series stage positioner, Sample Modeling distance/room controls, Pianoteq mic positions and room, Kontakt libraries' mic mixes | VI settings (presets, CC init values in maps; Project C) |
| 1. Source profile | Bring each VI to a common reference ("close, ~1 m, little room"): EQ out the library's mic colour/proximity. Libraries are tagged **anechoic** (SWAM, Sample Modeling, Pianoteq without room), **semi-dry/staged** (LASS, Infinite Series with positioner, VSL dry stage) or **wet in situ** (Spitfire). Staged/wet ones get less added early reflection, because their room is already baked in; they cannot be made drier, so the others are placed toward them | EQ |
| 2. Direction | Radiation pattern: horns' bells face backward (more reflected, darker direct sound); trumpets and trombones forward; strings and woodwinds mostly upward | EQ + direct/reflected balance |
| 3. Seat | Left/right: level **and** time difference between channels (VSS2 uses timing and reflections, not just pan). Depth: lower direct level, high-frequency air loss, later arrival (about 2.9 ms per metre: a back row ~10 m behind the front strings arrives ~29 ms later), position-specific early reflections (floor, side and back walls) | stereo IR per seat (convolution), or pan + short delay + EQ; per-track delay (Cubase Track Delay costs no CPU) |
| 4. Microphone | The recording's perspective: main array (e.g. Decca tree) vs spot mics; mic frequency response and off-axis colour; spacing (time-based stereo image). VSS2's "microphone profiles" belong here | EQ or short IR |
| 5. Depth reverb (send) | Per-section send level into the shared stage reverb: front drier, back wetter (the user's FX-channel Altiverb) | send level per seat |
| 6. Glue reverb (master) | Reverb of the whole space on the full output (the user's master Altiverb; in the DAW, the "final/room" reverb) | one instance per space |
| 7. Bus/mastering | Compressor etc. | unchanged |

Layers 1–4 for one seat can collapse into **one short true-stereo convolution** (≈50–150 ms IR)
plus a delay. WAV IRs load in any host (Dorico/Cubase: REVerence; Logic: Space Designer;
cross-platform: Altiverb, or a free convolver such as MeldaProduction MConvolutionEZ; candidates
are evaluated for CPU in E6), so **the portable form of a profile is numbers + WAV IRs**, and
host-specific presets are generated from it.

**E3 finding (2026-11-01): VSS2's seat is even simpler than a convolution.** Layers 3–4 in
VSS2 are a geometric simulation of its main microphones (a Decca tree in most projects): each
output = its own capsule + the centre capsule, each the source delayed by distance/343 m/s
(within limits each room sets on the tree's position), scaled by ≈ 1/distance (the centre
9.1 dB down; fits the user's settings to a median 0.03 dB), with the "Air" setting as a fixed
EQ; then a fixed early-reflection pattern with a faint treble shimmer. VSS2 costs ≈ 1.9 % of a
core per instance (≈ one core for the main template). So a seat can be rebuilt
exactly as **two delay taps per output + one EQ** (parametric, almost no CPU), with the
reflections from a shared layer; the captured IRs remain the exact reference. Details and
fit: `stagecraft/docs/STATUS.md`.

### 7.5 Capturing VSS2 (the basis for "capture, then retire")

VSS2 is (expected to be) a fixed linear filter for a given preset, so its whole effect can be
recorded: play a sine sweep into the left input only, then the right input only, record the
stereo output, deconvolve → four IRs (L→L, L→R, R→L, R→R). Checks: capture twice and compare
(no modulation/randomness), capture at two levels (no level dependence), then **null test**
VSS2 vs the convolution on real VI audio. From the IRs we also measure each preset's direct
delay, left/right time and level differences, direct-sound EQ and early-reflection pattern,
which gives a parametric picture of VSS2's model: lets us build seats VSS2 never had, tune per
space, and use plug-in parameters instead of IRs where cheaper.

Capture route: **`engine/crates/vi-render`** (headless VST2 host, Windows exe run from WSL,
built 2026-11-01 for Project C) already loads a plug-in, sets its state chunk and renders to
WAV; it feeds **silence** into plug-in inputs today, so it needs an **input-WAV option** for
effects (request to its owner / `engine/REQUESTS.md`). Then every VSS2 state can be captured
straight from the projects (`doricokit.virender.plugin_states`) or rebuilt from
`.vss2preset` files. Fallback/cross-check: render 2–3 sweeps by hand in Cubase (sweep on an
audio track, VSS2 insert, Export Audio). The same sweep/deconvolution code measures plug-in
latency, which latency-reporter needs.

### 7.6 Spaces and seats (profile data)

A **space** = seating plan + mic perspective + depth-reverb IR/settings + glue-reverb settings.
A **seat** = position (x/y metres, facing) + send level; resolved per instrument. Spaces:

| Space | Character to aim for (refined from evidence and the user's references) |
|---|---|
| Film scoring stage | Todd-AO / AIR-style stage, Decca tree + spots; the current Altiverb setup already targets Todd-AO. **First space to build** |
| Concert hall | Audience perspective: more distance, more hall, less spot |
| Chamber / small hall | Closer, smaller room; solo and small ensembles |
| Studio (jazz/pop) | Close-miked, drier room, wider panning; big band, sax, rhythm section, other styles |
| Concert band: wind ensemble | Between concert hall and small hall; wind-ensemble seating |
| Concert band: military band | Same band work, military-band sound; defined from the user's reference recordings |

Seating plans are data with variants (e.g. American vs German string seating; band seatings).
The user's reference recordings (offered for the band styles, useful for every space) are
analysed for long-term spectrum, width and depth/reverb balance, and the mock-up is compared
to them.

Sketch (format decided in E5):

```toml
[source."SWAM Flute"]            # layer 0–1
inherent = "anechoic"
vi = { cc91 = 0 }                # built-in reverb off
eq = "irs/source/swam-flute.wav" # or parametric bands

[space.film-stage]
seating = "orchestra-american"
mic = "decca-tree"
depth_reverb = { plugin = "Altiverb 7", ir = "Todd-AO 10.7m wide s-s" }
glue_reverb  = { plugin = "Altiverb 7", ir = "Todd-AO 3.5m s-s" }   # E1 confirms which is which

[seat.film-stage."Flute 1"]      # layers 2–5
x_m = -1.5; y_m = 7.0; facing = "front"
ir = "irs/film-stage/flute-1.wav"; delay_ms = 0; send_db = -14
```

### 7.7 Host outputs

- **Dorico (writing/mock-up)**: the chain per channel replaces VSS2; Dorico has no per-track
  delay, so delay goes in a plug-in. Ways in: the user builds it once from a generated recipe
  and saves it as template/playback template (Project D); later, written into a **copy** of a
  project with the S5 edit layer. Stem export needs the per-track chain off (stems "in place"):
  a "stem mode" switch (bypass the seat chain, keep nothing but the master glue/mastering, as
  the user does now).
- **Cubase (final mix)**: per stem track the seat chain + Track Delay; depth reverb on an FX
  channel; glue + mastering on the output. Plug-in presets as `.vstpreset` (documented VST3
  format, can be generated); Cubase track presets/templates are built once by the user from
  the recipe if they can't be generated.
- **Logic Pro**: same chain with AU versions; `.aupreset` (plist) generated; Space Designer or
  a cross-platform convolver for IRs. Steinberg-only plug-ins (REVerence) don't exist in Logic,
  so profiles prefer cross-platform plug-ins and WAV IRs.

### 7.8 Phases

| Phase | Work | Needs from the user |
|---|---|---|
| **E1 Inventory** (read-only) ✅ 2026-11-01 | Engine: per-channel mixer reader (inserts, slot, enabled, gain, pan, sends + levels), joined to the plug-in states `doricokit.virender.plugin_states` already finds per rack slot; decode VSS2 states and `.vss2preset` `PresetData`; map the two Altiverbs to channels and read their key settings; run over all projects → inventory table per instrument (library profile, mic position, position, send level) in the tool's docs | nothing |
| **E2 Capture pilot** ✅ 2026-11-01 (user: A/B difference "extremely subtle") | Input-WAV option in `vi-render`; sweep + deconvolution tool; 2–3 VSS2 presets; repeatability, level and null tests; one Cubase render as cross-check. **Go/no-go for "capture, then retire"** | one short Cubase render (cross-check) |
| **E3 Batch capture + analysis** ✅ 2026-11-01 | Every VSS2 setting in use (39 projects, identical sounds once) and all 198 presets in three rooms, captured (`stagecraft library`); per-seat numbers (microphone taps, tone, reflections); model fit; reflection motion measured (`stagecraft motion`) | — |
| **E4 Source profiles** | Per VI family (same order and sessions as Project C): what "dry" means, internal settings, measured spectrum and baked-in room of a reference render | Dorico renders as in Project C |
| **E5 Spaces + seats** (started 2026-11-02: stage engine + files, VSS2-compatible stages checked against the captures, the user's chosen improvements, editor `stagecraft serve`, film-stage starter; `stagecraft/docs/STAGES.md`) | Film stage first; profile format; seating data | reference recordings per space (asked when E5 starts) |
| **E6 Host builds** | Dorico, Cubase, Logic; plug-in candidates measured for CPU; generated presets | install free plug-ins chosen |
| **E7 Listening** | Blind A/B: VSS2 vs new chain; mock-up vs reference; user picks, values tuned | listening |
| **E8 More spaces** | Concert hall, chamber, studio, concert band (wind ensemble, military band) | references |

### 7.9 Shared capabilities and where code goes

- **Engine** (`dorico-format::playback`, used by dorigit): per-channel mixer reading.
  Plug-in states per rack slot: `doricokit.virender` (exists). Offline plug-in hosting:
  `vi-render` (exists; needs audio input for effects; VST3 hosting not built, needed later to
  measure the VST3 replacement chains). Coordinate with the engine session / vi-render's
  owner before editing engine crates; otherwise file a request in `engine/REQUESTS.md`.
- **Audio measurement** (new, Rust: sweep, deconvolution, spectrum, left/right time and level
  difference, early-reflection detection, latency): shared with latency-reporter (latency
  measurement) and later dorico-hp audio captures, so it is a shared crate, not tool-private.
- **Profiles, IRs, generators**: a new tool folder (name to agree when E1 starts).
  Never commit vendor IRs or factory presets; captured IRs of the user's own VSS2 presets stay
  local (git-ignored) unless the user says otherwise.

### 7.10 Risks

- ~~VSS2 may not be fully linear~~: E2/E3 settled it: linear, direct sound fixed, reflections a fixed pattern with a slow treble shimmer (≈0.1–0.9 Hz, above ≈4 kHz).
- Libraries with baked-in room (Spitfire, LASS, staged Infinite Series) limit how dry the
  common reference can be.
- The depth and glue reverbs already add early reflections; the seat chain must not double
  them (check Altiverb's "Early Reflections On"/gains in E1).
- Per-channel convolution × 45+ channels: CPU measured in E6; parametric fallback.
- Delays for depth can smear fast passages; amounts are tuned by ear in E7.

### 7.11 Ensemble balance (user, 2026-11-01)

The user's way of working: pick the dynamics that sound right, leave every VI at a fixed gain
in the VI and mixer, and compensate for balance elsewhere, so that the mix is always
**balanced yet punchy and not washed out by reverb or reflections**, without having to think
about it. VSS2's per-section settings (flutes' treble boost, per-section reflection levels)
are one way the user has done this so far. To explore (E4/E5, ask the user when it starts):
- **Level calibration per dynamic**: each VI's output at pp … ff against what that real
  instrument produces (acoustic power differs widely: a ff flute is far softer than a ff
  trumpet), so that written dynamics give a natural balance. A fixed gain per VI (part of the
  source profile, layer 1) plus, if needed, a dynamic-to-level curve (Project C's maps).
- **Presence instead of a treble boost**: what makes a flute carry in a hall (strong
  fundamental, little masking in its register, directivity) and whether a seat EQ, an
  early/late reflection balance or a level does it more naturally than +22 dB at 16 kHz.
- **Not washed out**: per-seat direct-to-reflected ratio and the glue reverb's level/pre-delay
  are the levers; measure what VSS2 + the two Altiverbs give today (E3 numbers) as the start.

### 7.12 Mic bleed and multi-position room IRs (user, 2026-11-01; explore after E3)

The user's past technique: three Altiverb instances on buses, same room IR (e.g. Todd-AO) at
different positions/mic distances, one each for front (strings), middle (woodwinds), back
(brass; percussion sometimes separate); other sections dialled into each bus by ear to mimic
mic bleed (more brass on the string mics than strings on the brass mics). Questions: is it
worth exploring, what is sound and what is flawed, how stagecraft can do it (with the
captured IRs).

Working answer (session notes, to test in E5/E7):
- **Model**: bleed = every instrument reaching every microphone, delayed by distance/343 m/s,
  scaled by distance, instrument directivity and the mic's polar pattern, darker with
  distance. VSS2 already does exactly this for its three tree mics (E3: fits within 0.01 ms /
  ≈0.05 dB), so the same model extends to spots, outriggers and ambients: a **mic plan** per
  space (positions, patterns, mix levels) → a bleed matrix (instrument × mic: delay, gain,
  EQ), computed instead of dialled by ear.
- **Collapse offline**: everything is linear, so the whole mic plan and its mix for one
  instrument collapses into one stereo response per seat (taps or a short IR). No bus matrix
  at run time; the mic balance (tree vs spots) is a profile parameter, regenerated when changed.
- **Room tails stay shared** (the glue reverb): the diffuse tail is roughly the same at
  every mic, so three full tails mostly add wash; what differs per mic is the delayed direct
  sound and early reflections (the depth layer). Position IRs (Altiverb Todd-AO etc.) feed the
  per-zone early part; Altiverb positions can be captured like VSS2 (local only).
- **Flaws of the bus method to avoid**: bleed sent into another section's bus gets that
  position's geometry (arrives as if from the front, too early and bright, so it pulls the
  back sections forward); a bus IR with its direct sound on duplicates the dry signal at
  another delay (comb filtering); tails stacking (washed out); bleed amounts depend on each
  VI's output level, so they need the level calibration of §7.11.
- Stems "in place" (§7.2): bleed means a section's placed stem contains other sections; in
  the DAW the collapsed per-seat responses keep stems separate (bleed is applied per source).

### 7.13 Infinite Series in-player positioning (user, 2026-11-01; future, part of E4)

The Infinite Series instruments (Infinite Brass/Woodwinds) have their own **in-player
positioning**, which adds early reflections (probably no bleed). Wanted, when E4 reaches
Infinite Series:
- **Measure it** like VSS2: capture the instrument's positioner as responses per position
  setting (render a dry reference with positioning off vs on, or capture the effect directly
  if it can be isolated), giving its delays, levels, tone and reflection pattern.
- **Match across VIs**: either make other instruments match the Infinite positions (use the
  measured responses on other VIs), or adjust the Infinite ER settings so they match the
  stagecraft room and seat (same room as everyone else).
- **Or switch it off**: the user thinks the positioning/ER elements may be disableable per
  instrument; check when appropriate (VI-internal settings, layer 0 in §7.4), then place it
  like the anechoic libraries.

---

## 8. Smaller items

- **Spelling check for performance terms** (user, 2026-11-01): flag misspelled Italian (and
  other) terms in text items, playing techniques and expressions, e.g. "brilliante" →
  "brillante", with a suggested correction; never read a misspelling as the intended word in
  playback. Belongs to the reviewer/findings layer (`doricokit.findings`), usable by f2d's
  reviewer and dorico-hp; the list of terms is shared with dorico-hp's `passages.py`.
- **Ensemble intonation: a dorico-hp Apply kind** (user, 2026-11-03; *for the user to review,
  not started*). Came from the "anti-pitch-correction" plug-in idea in the plug-ins workspace:
  full brief in `~/dev/vst-plugins/PLANNED_WORK.md` §4 (Project I). Modeled VIs (SWAM, Sample
  Modeling, Infinite, Pianoteq) play in exact equal temperament, identical on every instance,
  so exposed ensembles sound too perfect. Sampled sections (LASS, Spitfire, VSL) already carry
  recorded intonation and are left alone. The idea: a new Apply kind, `intonation`, that writes
  **per-note pitch bend** for modeled solo instruments, reading the score for unisons and chords:
  - **unisons** start a few cents apart and converge over the note, without becoming identical;
  - **chords** lean toward just intonation by an adjustable amount (e.g. 30–60 %: major thirds
    up to ~14 cents low, fifths ~2 cents wide); leading tones slightly high;
  - a small, consistent **bias per player**, an **onset scoop** that settles, slow **drift**
    over a phrase.

  Needs: each VI's pitch-bend range (a `libraries.toml` field; SWAM's is settable in the
  plug-in), one instrument per MIDI channel (true for SWAM/SM solo instruments), and keeping
  any pitch bend the user already wrote. Check against Hermode Tuning (Cubase/Logic) and
  whether the VIs support MTS-ESP microtuning before building. Measure with `vi-render`
  (SWAM, Pianoteq). A real-time version (a VST plug-in for Cubase/Logic) would be built in
  the plug-ins workspace later, if wanted.

---

## 9. Readiness gates and suggested order

| Gate | Needed for | State (2026-10-30) |
|---|---|---|
| Project S decisions (§2.9) | everything | All answered (2026-10-29); uv installed |
| Engine session started (brief §2.12) | S0 onwards | Started 2026-10-29 |
| S2 codec bindings + S3 helpers | every later phase | Done 2026-10-29 (Windows wheel pending) |
| S5 edit layer (byte-identical untouched data) | cleaner, A5 apply-style, B4 harpgliss, dorigit merge | Not started (dorico-hp plumbing is the seed) |
| S4 read model incl. options, library, slurs, glissandi | A6 lint, B4 | Read model done and used by all three tools (2026-10-29); prototype retired (2026-10-30); options and library not in it yet |
| finale-read `style` facts | A1 | Not started |
| Reference-round method (user saves Dorico files) | A3, B2 | Proven in finale2dorico Rounds 1–9 |
| Remote Control PDF export (`automation`) | A6, B5 | API names found; parameters not discovered |
| Target Dorico version | all | **Dorico 5** (decided); Project B moves to **Dorico 6.2.30+** for sawtooth/wavy (B is on hold until the user has Dorico 6) gliss line styles (user, 2026-11-01) |
| `vi-render` audio input for effects | E2 (VSS2 capture) | Requested in `engine/REQUESTS.md` 2026-11-01; vi-render itself built 2026-11-01 (Project C) |
| Project E inventory (E1) | everything in E | **Done 2026-11-01** (`stagecraft inventory`; instrument names per channel wait on engine routing, requested) |

**Suggested order**

1. ~~**Start the engine session** with §2.12, and do **S0–S3**~~ Done 2026-10-29, with S4.
2. In parallel, read-only evidence work that needs no shared modules: **A1–A2**, **B1**, and the
   **A3 + B2** reference round (one round to save the user time).
3. **S4–S5** (one model, edit layer), then **A4** decisions (font specimen) and **B3** geometry.
4. **S6–S9**, then **A5** and **B4**.
5. **A6 / B5** validation; **S10–S12** as the tools settle.

---

## 10. Original requests

<details><summary>VI playback profiles / expression maps (2026-11-01, verbatim)</summary>

> Your correct in that there is no keyswitch/expression map entry for staccato; while I'd like to
> "fine tune" our expression maps for optimal playback (and, potentially, with specific
> adjustments based on "style" etc.) so they are "work best" with both Dorico and our various
> VIs, that requires more "rigourous" investigation into how each VI works. I would like to
> explore this further--both here (for SWAM Flutes) and elswhere (could be a "good idea" to begin
> a separate session for each "VI" set used i.e. SWAM Woodwinds, SWAM Brass, Infinite Series
> Brass, Infinite Series Woodwinds, LASS 3, Spitfire Harp Redux, et al--including some VIs not
> yet "configured" with expression maps for Dorico). For SWAM Flutes--documentation is here:
> https://support.audiomodeling.com/guides/winds/SWAM%20Woodwinds%20v2.8%20-%20User%20Manual.pdf

</details>

<details><summary>Score configuration manager / templates (2026-11-01, verbatim)</summary>

> it might be woth adding to our PLANNED_WORK a way to "manage" scores and their configurations
> outside of Dorico; this could ideally allow for the easy application of desired expression
> maps/percussion maps/custom playback techniques/custom lines/et al, and also allow for "easy"
> creation and management of "project templates" (when this is explored, we should also look at
> what Dorico saves in it's "own" settings/configuration/preferences

</details>

<details><summary>Stage placement / audio-chain profiles (2026-11-01, verbatim)</summary>

> I tend to use a "mix" of sample libraries and virtual instruments that all "lean dry" but still
> contain "various levels of dryness" as well as "different (recording) perspectives"--for
> instance, LASS (while not "recoded in situ") is dry but not "bone dry", and when sections are
> panned center, they have a "natural layout" while also being able to be easily
> repositioned/panned; Infinite Series Brass/Woodwinds are also not "bone dry" as they feature an
> "in engine" "on stage" positioner to "place" each instrument on stage/in position (such that the
> correct early reflections etc are automatically applied); Sample Modeling brass and saxophones
> are quite "bone dry" with little/no "air" (early reflections)--excellent for "exposed" parts
> (i.e. close miced solo, etc.) but can be difficult to "mix" and "position" properly within a
> full orchestral multi-library setup. While reverb provides a good "glue" (I tend to prefer
> Altiverb but have gotten good results from many products) for this, I have found many
> factors--from early reflections to EQ to delay--to affect specifically how an instrument is
> "placed" in an "orchestral space/mix", and it is difficult to "get this right" as well as
> "match up" the various VIs. To help with this, I have in the past utilised Virtual Sound Stage
> 2 (no longer developed/sold; provided as a free download now from
> https://www.musehub.com/plugin/virtual-sound-stage) to help with this, as it allows for both
> "spacial positioning" but also provides various "microphone profiles" which I find to be one of
> the many variables that affect this sound in recordings (especially in relation to EQ and
> "spacial/microphone coloring"); I also believe that (some if not all) of this can be achieved
> with a combination of "common" plugins (potentially even "light" resouce-wise plugins) and/or
> Impulse Responses (or similar) as well as VI settings (i.e. "distance" knobs in Sample Modeling
> brass,, etc.). I'd like to consider I can work on the above--ideally, the end goal is to have a
> full set of "digital audio chain" profiles for my VI so I can improve my virtual instrument
> mixes (both for orchestral music and other styles) in terms of "realism".

On the two Altiverbs (same day): "one is 'dialed in' on each 'section' as appropriate to provide
'layers' of reverb (i.e. front is 'drier' back is 'wetter' etc)), while the final/master reverb
is used as the 'glue'/'reverb for the entire space' (and applied to the whole track/output)."

</details>

<details><summary>Shared modules (2026-10-29, verbatim)</summary>

> I'd also like to consider/think about the specific "modules" used by the various "tools"
> available in this project/repo/codebase--ideally, I'd like to "separate" and "centralize" these
> such that they can be easily "shared"/used by each of the tools (e.g. module to read/interpret
> Finale files, module to read/write/edit Dorico files, etc.) Please review the codebase with the
> above in minde, and spec out/plan the work as you did with the other tasks/prompts, adding it to
> our PLANNED_WORK.md (note that I'd consider this the "highest priority" as it potentially impacts
> all of our tools and allow each to "benefit" from any work done on any tool.)

</details>

<details><summary>House style (2026-10-28, verbatim)</summary>

> I'd like to consider/ideate on how I could potentially create a "house style" in Dorico that is
> "publish ready" but "friendly/readable to musicians". I'd ideally like this to be "based off of"
> the layous of published scores "blended" with the layout of film scores (e.g. 4 measures per
> page, centered bar numbers, etc). I have some Finale scores that are examples of both published
> scores and film scores (from my understanding, some of the "source" files potentially used for
> publishing/printing/performance). I'd love to use the existing tools within this
> folder/project (there are at least 3) to help analyize the look/feel of these various scores and
> help outline a professional house style specific to myself and for use in Dorico. Note that it
> would be nice to additionally/concurrently build a "classic" and "film" set of styles for use
> with scores that have more "strict" requirements (e.g. a "non-modern"/transcribed band/orchestra
> piece, an actual film score, etc.) We should NOT impelment this--we shoudl be highly focused on
> plans/specifications such that implementation becomes "easy" (especially once the various tools
> in this folder/project are more "fleshed out" and mature.)
> - D:\SCORES+BOOKS\Film Scores\James Horner\Avatar\Finale (.mus) Files
> - D:\SCORES+BOOKS\Film Scores\John Williams\Superman
> - D:\SCORES+BOOKS\Film Scores\John Williams\Superman\Concert Scores
> - D:\SCORES+BOOKS\Film Scores\John Williams\E.T. The Extra Terrestrial\Concert Scores
> - D:\SCORES+BOOKS\Film Scores\John Williams\Star Wars - The Empire Strikes Back\Concert Scores
> - D:\SCORES+BOOKS\Film Scores\Marco Beltrami\The Thing\Complete Score (pdfsib)\MB-TT-SIBMUS

</details>

<details><summary>Harp glissandi (2026-10-28, verbatim)</summary>

> I'd like to consider/ideate on supporting more "idiomatic" and "professional grade"/"publish
> ready" harp glissandos (specifically, "ad lib" type) in my Dorico scores. They should not only
> look excellent (e.g. "idiomatic" curves/lines etc.--in "engrave" and "print" mode(s)) but ideally
> they should also play back well/correctly (e.g. play all notes of the gliss as expected,
> following the "ad lib" shape/expression/etc.) Use the various tools in the folder/project to
> help you with this as needed--I do also have an example of a notated "ad lib" harp glissando and
> my "notational interpretation" that I will provide you separately (please request these
> specifically when ready so they get properly reviewed/ingested.)
>
> Examples of the desired notation:
> - https://musescore.org/sites/musescore.org/files/styles/width_740/public/2018-02/slur%20harp.jpg (top harp staves only)
> - https://europe1.discourse-cdn.com/steinberg/original/4X/2/6/1/261b9a984df943d804364e141d95d3ee92710f89.png
>
> More on harp glissando notation (open to "sawtooth" too, but the curved lines above are the goal):
> - https://harpnotation.com/de/notation-manual/sliding-sounds/glissando/single-glissando/

</details>

<details><summary>Answers (2026-10-29, verbatim)</summary>

> - what setting(s) are you referring to? (the full orchestral template was focused on player
>   setup and playback for writing/mockups, and not for engraving/printing)
> - concert pitch is generally preferred (this should all be "easily switchable" in Dorico)
> - i'm open to the "best" fonts, and would love to review options--you could also "pull" from
>   ~/dev/kenpierson.com as that is my recently revised site with some font info/preferences
> - let's target version 5 for now

</details>

<details><summary>Answers on shared modules and fonts (2026-10-29, verbatim)</summary>

> 1. No--I have not started on the separate engine session yet (though I'd like to start that
>    next/first; I am presently working on the finale to dorico converter)
> 2. That is fine
> 3. This is also fine; ideally, the "more Rust" and "less Python" we are able to use (with the
>    ultimate goal having this fully built/running on Rust and no Python) the better
> 4. Yes
> 5. I'm fine with it being "test only" with the ultimate plan being deprecation/removal; I just
>    want to confirm it is not the "finale to dorico converter" actively being developed.
> 6. Sure as long as it is not needed
> 7. I'm not entirely sure yet--right now I lean toward dorigit being it's own application/tool
>    (specific to version control for music/dorico files), though I am open to having other
>    presently separate tools/modules (human playback engine, finale to dorico converter, etc)
>    share a UI/UX as long as it makes semantic/functional sense (e.g. all "score management"
>    tools live together, etc.--be smart/considerate about how you approach this, such that we
>    don't end up with one "monolitic" app with too much nor do we end up with "tons of tiny apps"
>    that should really "live together".)
> 8. Ideally the highest version we can (considering any dependencies); at minimum 3.12 if not
>    3.14. (Also--ideally we use UV for version/package management; I come from the "node JS"
>    world and prefer that type of system.)
>
> Additionally--I'd like to stick with the Bravura font for now (regardless of what is used on my
> site's logo, as that is just "for design"), but I wouldn't mind exploring various SMuFL notation
> fonts (like Sebastian et al) to determine which I like best (and potentially for each "score use
> case").

</details>

### Sources consulted (web, 2026-10-28)

- [harpnotation.com: single glissando](https://harpnotation.com/de/notation-manual/sliding-sounds/glissando/single-glissando/)
- [Steinberg forum: Curved glissando lines](https://forums.steinberg.net/t/curved-glissando-lines/745517), [Harp gliss roofs](https://forums.steinberg.net/t/harp-gliss-roofs/787245), [New take on glissando](https://forums.steinberg.net/t/new-take-on-glissando/1042742)
- [notat.io: "ad lib" harp glissandi](https://www.notat.io/viewtopic.php?p=10928) (could not be fetched; search summary only)
- [Dorico help: Glissando lines in playback](https://www.steinberg.help/r/dorico-elements/6.1/en/dorico/topics/notation_reference/notation_reference_glissando_lines/notation_reference_glissando_lines_playback_r.html), [Changing the glissando playback type](https://steinberg.help/dorico_pro/v5/en/dorico/topics/notation_reference/notation_reference_glissando_lines/notation_reference_glissando_lines_playback_type_changing_t.html)
- [Scoring Notes: Dorico 6.2.30](https://www.scoringnotes.com/news/dorico-6-2-30/), [Dorico 6.2](https://www.scoringnotes.com/news/dorico-6-2/)
- [Dorico help: hiding noteheads](https://www.steinberg.help/r/dorico-elements/6.1/en/dorico/topics/notation_reference/notation_reference_notes/notation_reference_notes_noteheads_hiding_showing_t.html)
