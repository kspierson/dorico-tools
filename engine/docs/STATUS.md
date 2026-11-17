# Engine (Project S): status and resume notes

*Last updated: 2026-10-31 (timeline session; before it session 3: one copy of every decoder, findings v2). Read this first when picking the work back up. The plan is
`../../PLANNED_WORK.md` §2 (the brief is §2.12); this file records what was actually done.*

## Where things stand

| Phase | State | Safety check result |
|---|---|---|
| **S0 Baseline** | ✅ golden set in `tests/golden/manifest.json`: dorigit + dorico-hp (56 cases), f2d (54 cases, recorded right before its switch: 8 conversions + review of each, --dtn, bootstrap reader, ir, review of 40 projects, dump) | Re-run: identical (f2d with a fixed hash seed and dates masked) |
| **S1 Skeleton** | ✅ `engine/`, **repo-root Cargo workspace** (one `Cargo.lock`, one `target/`), `dorico-format` moved here, `dorico-paths` crate + `tests/corpus.toml`, shared `scripts/dev-env.sh`, test files A–H moved to `tests/dorico-files/`, uv workspace root | `cargo test` ✅; real-file tests (64 DTN byte round trips, 32 listings = Python prototype, before it was retired) ✅; dorigit Windows app + CLI cross-build ✅; golden 56/56 ✅ |
| **S2 Codec bindings** | ✅ **dorico-hp** and ✅ **f2d** (codec + container; `f2d/dtn.py`, `research/tools/dtn.py` deleted; `finale2dorico/pyproject.toml`, workspace member; `f2d` command); 🟡 Windows wheel blocked (maturin issue, below) | Codec parity: 80 trees / 40 projects, **0 differences**; golden: all identical (f2d conversions identical as decoded trees); you opened the new zips in Dorico: OK |
| **S3 Foundation helpers** | ✅ Rust: `tree` (builders, DTN-safe edits, property tables, `event_head`), `ids` (allocator + counter check), ticks on `Ratio`. Python: `doricokit.positions`, `doricokit.ids`. dorico-hp uses `doricokit.positions` | Positions parity: 3,304 distinct strings + 4,000 tick conversions, **0 differences**; ID counters OK in all 40 projects; golden 56/56 |
| **S4 One read model** | ✅ `dorico-model` + `doricokit.model`, now used by **f2d's reviewer** (`read.py` is a thin view), **dorigit's listing** bar numbers (shared `dorico-format::bars`) and **dorico-hp's `notation.py`** (thin view). Model additions: displayed bar numbers (pick-up = 0, bar-number changes), repeats (segno/coda/jumps/endings), divisi staves, voice → stave ID, instrument ranges, "f possibile". `dorigit/prototype/` **retired** (2026-10-30; scripts moved to `dorigit/research/`, new `doricokit.listing`). Left: delete the thin views (later, see decision 8) | Parity vs the old readers (kept as oracles in `tests/oracles/`): no unexplained differences. Golden: dorico-hp Apply/render **identical**; f2d review and dorigit listing changed only as listed under "Tool output changes" |
| S5–S14 | not started (see the note below on S5/S9) | |

**2026-10-31, from the finale2dorico session (user's request: modular tools):** Python
prototypes now live in `doricokit`: `edit` (S5's operations so far: transaction, remove event,
link dynamics, content equality, safe save), `findings` (S9's schema + check/rule registry),
`view` + `review` (the reviewer, was f2d) and `clean` (the cleaner). CHANGES.md has the API.
S5 in Rust can start from `edit.py`'s operations and tests; S9/S12 from `findings.py` and
`review.py`. f2d only wraps them.

`scripts/test-all.sh` (fast) and `scripts/test-all.sh --full` (whole corpus + all golden
cases) were green at the end of the session.

**2026-10-31, session 3 (handed over from the review session, MODULE_REVIEW.md):** read-side
duplication removed and read-model gaps 1–5 + 10 closed; findings format v2. Details in
CHANGES.md ("engine session 3").
- New **`dorico-format::vocab`**: the one home of Dorico's vocabulary (values, glyph tokens,
  technique/tuplet/key/clef/ottava/ornament/arpeggio/pause/divisi/articulation names, pitch
  spelling, tempo, player names, 4.3/5.1 version forms). `dorico-format::dynamics` is the one
  dynamics decoder (readable `describe` + machine `level`).
- `dorico-model` uses only those (no private decoders) and gains keys, typed tuplets, readable
  `Mark.name`, `DynamicItem.name`, `Player.label`, `Note.muted`, typed detail for the raw kinds.
- dorigit-core's `listing.rs`/`notation.rs` and `doricokit.view` call the engine instead of
  their own copies (dorigit session agreed; it rebuilt its Windows app).
- Findings v2: additive (every v1 field unchanged), with event/stave/flow IDs, Dorico bar and
  beat, tool and `change {before, after}`.

### Listing model: plan (item 6 of the hand-over)

dorigit's listing (`dorico-format::model::build_score`) and `dorico-model` are still two
readers of the same tree, but since session 3 they share every *decoder* (vocab, dynamics,
bars, element tables): what is left twice is only the walk (streams, block placements,
bar/beat location). Plan, not started (restructures dorigit's listing; ask the user first):
1. Build the listing rows from `dorico-model` (one row per note/mark/dynamic with owner/lane),
   keeping the listing's text byte-identical (golden `dorigit/show/*` is the check).
2. Move dorigit's naming pass (`listing.rs`, now a thin layer over `vocab`) into that builder
   so `doricokit.listing` (research scripts) gets the same names.
3. Move `diff` with it (MODULE_REVIEW §4 "dorico-compare"); then delete the second walk.

## Files that moved (tell the other sessions)

| From | To |
|---|---|
| `dorigit/crates/dorico-format/` | `engine/crates/dorico-format/` (dorigit uses it through the root workspace) |
| `dorigit/Cargo.toml` (workspace) | `Cargo.toml` at the repo root (dorigit's crates and app are members) |
| `dorigit/Cargo.lock`, `dorigit/rustfmt.toml` | `Cargo.lock`, `rustfmt.toml` at the repo root |
| `dorigit/target/` (build cache, git-ignored) | `target/` at the repo root (moved, not rebuilt) |
| `dorigit/scripts/setup-wsl-toolchain.sh` | `engine/scripts/setup-wsl-toolchain.sh` |
| `dorigit/scripts/dev-env.sh` | now forwards to `engine/scripts/dev-env.sh` (which also adds cmake/ninja and uv) |
| `dorigit/prototype/experiments/dorico-tests/*.dorico` (A–H, git-ignored) | `engine/tests/dorico-files/` (git-ignored) |
| `dorico-hp/doricohp/dtn.py` | `engine/tests/oracles/dtn_py.py` (test oracle only) |
| `finale2dorico/f2d/dtn.py`, `finale2dorico/research/tools/dtn.py` | deleted (use `doricokit.format`) |
| old `finale2dorico/f2d/dorico/read.py` | `engine/tests/oracles/f2d_read_py.py` (oracle); `read.py` is now a view over the model |
| old `dorico-hp/doricohp/notation.py` | `engine/tests/oracles/hp_notation_py.py` (oracle); `notation.py` is now a view over the model |
| `dorico-model/src/bars.rs` (new this session) | `dorico-format/src/bars.rs` (shared with dorigit's listing) |
| `dorigit/prototype/experiments/merge_probe.py`, `make_test_files.py` | `dorigit/research/` (2026-10-30; on `doricokit`, byte-identical output) |
| rest of `dorigit/prototype/` | deleted (2026-10-30, your OK); backup `~/dev/dorico-test-backups/2026-10-30-dorigit-prototype.tar.gz` |

`finale2dorico/` was changed only in the agreed switch (at the user's quiet point): imports,
`writer.write`/`_load_score`/`dump` via `doricokit.container`, `read.py` as a model view,
`review.py` range check, one test expectation (pick-up = bar 0), docs, `pyproject.toml`. The f2d
extractor build still works: its zig shims live in `~/.local/opt/zig-shims`.

New files: root `Cargo.toml`, `pyproject.toml`, `.python-version` (3.15), `.gitignore`,
`uv.lock` (made by `uv sync`), `.venv/` (git-ignored); `engine/**`; `dorico-hp/pyproject.toml`.

## How the pieces fit

```text
engine/crates/dorico-format   codec, XML, zip container, ratio/ticks, tree helpers, ids, bars
                              (displayed numbers), dorigit's listing model + diff + playback reader
engine/crates/dorico-model    the one read model (new, S4)
engine/crates/paths           dorico-paths: install, AppData, WSL <-> Windows, corpus.toml
engine/crates/timeline        dorico-timeline: tempo map, performed order, seconds, timecode,
                              MIDI tempo events (TIMELINE.md)
engine/crates/doricokit-py    PyO3 module doricokit._native (temporary bridge)
engine/python/doricokit       format (= old dtn.py API), container, positions, ids, model, paths,
                              listing (dorigit's listing model, for research scripts), timeline
```

Python tools import `from doricokit import format as dtn` (same `Node`/`Document`/`decode`/
`encode`/`to_xml`/`from_xml` as the old copies). Trees are plain Python objects, because the
tools edit them in place; Rust does the parsing and writing. Details: `DEV_SETUP.md`.

## Decisions I made (please confirm or overrule)

1. **Zip folder entries.** Dorico stores folders (`META-INF/` etc.) as empty *deflated* entries.
   The Rust writer stored them uncompressed; I changed it to match Dorico. This also changes
   dorigit's restored files slightly (closer to Dorico's own). File contents are untouched.
2. **Ticks round half to even** (`Ratio::to_ticks`), like Python's `round()` that dorico-hp
   uses, so ported code gives identical numbers.
3. **S3 tree helpers in Python stay where they are** (dorico-hp `project.py`, f2d `tree.py`)
   instead of being copied into `doricokit`. The Rust versions are the reference now. The
   Python copies disappear when their tools move onto the Rust edit layer (dorico-hp, S5) and
   the build layer (f2d, S8/S13). The alternative, a Python `doricokit.tree`, would have been a
   third copy. Recommendation: keep it this way.
4. **New crate `dorico-model`** for the read model instead of growing dorigit's listing model.
   dorigit's listing is untouched (its output and the git textconv stay identical). Later
   dorigit's listing can be built on the new model, which would fix its bar-number gap.
5. **Python 3.15** pinned (`.python-version`; PyO3 0.30.1 supports 3.15 final). The extension
   is built for the stable ABI (`abi3-py312`), so one build also works with system Python 3.14.
6. **`python3 -m doricohp...` still works** without uv: `doricohp/__init__.py` finds
   `engine/python` once `uv sync` has built the extension.
7. Golden text outputs replace their input/output folders with `{in}`/`{out}` before hashing,
   because those folders move during Project S.
8. **f2d's `read.py` and dorico-hp's `notation.py` stay as thin views** over the model (same
   classes), so `review.py` and Apply needed almost no change. Deleting them means rewriting
   their callers against the model; better done when the reviewer moves to Rust (S9) and Apply
   to the edit layer (S5).
9. **Divisi staves** are labelled "Violin I (divisi staff 2)" in reviewer findings (the main
   staff counts as division 1). Each divisi staff is checked on its own, so a mute set on both
   the main and divisi staff and never released is now reported for each.
10. **dorico-hp still ignores combined dynamics (fp, ...)**, as before: the model has them, but
   passing them to the rules would change Apply output. A dorico-hp decision.
11. **dorigit listing past the end of the music** keeps counting bars (a time signature at the
   very end of "all i want 2" stays "bar 149", as before).

## Tool output changes from the S4 switches (all checked, golden re-recorded)

| Tool | What changed | Where (your files) |
|---|---|---|
| f2d review | divisi staves are separate staves ("Violin I (divisi staff 2)"): ~270 false duplicate/repeated-dynamic findings gone; mute findings now per divisi staff | Have Yourself… (4 versions) |
| f2d review | bars after a mid-bar time signature numbered right ("bar 26 beat 11" -> "bar 27 beat 1") | all i want 2 |
| f2d review, dorigit listing | bar numbers as Dorico shows them: pick-up = bar 0 | brass test |
| f2d review, dorigit listing | "f possibile" instead of the raw encoding | ET test files A-H |
| f2d review | staff order inside could-link messages follows the score | HP, Obi-Wan, Rainy Nights |
| dorico-hp | nothing in Apply/render output; `notation.py` JSON gains `bar_labels`, longer `bar_starts` where the flow has empty bars at the end | - |

## S4 parity findings (old readers vs the new model)

| Finding | Who is right |
|---|---|
| f2d `read.py` merges divisi staves (Dorico gives every divisi stave index 0) and so counts each linked dynamic twice (Have Yourself…, strings) | new model keeps the staves apart. The reviewer may currently report false duplicates |
| f2d `read.py` doesn't start a new bar at a mid-bar time signature ("all i want 2", bar 22) | new (Dorico always starts a bar at a time signature) |
| f2d `read.py` ignores block-instance positions | no effect in the corpus (all blocks at 0); new model applies them |
| dorico-hp `notation.py` ignores pick-up bars (`brass test`) | new |
| dorico-hp `notation.py` ends the flow at the last event; Dorico keeps `minimumNotatedLength` (29 flows: e.g. HP flow 3 has 137 bars, not 130) | new |
| dorico-hp `notation.py` misses rich-text Text events ("MM", "OO", "AH" in all i want 2) | new |
| `{int: 0}, {int: 1}, {bool: false}, {}` | **"f possibile"** (you saw it in test file A; it came with your ET project, not from our tools); decoded since 2026-10-29. **Corrected by you 2026-10-30: possibile is a standard Dorico modifier, allowed only on f or p** (not an error). "p possibile" = `{int: 1}, {int: 1}, …`; possibile with any other level now reads as a custom dynamic |
| 7–8 f counts (`{int: 7}`, `{int: 8}`) | decoded as fffffff / ffffffff (Horn 2 bar 89, Timpani bar 69 in test file A); Dorico's display not checked |
| Bar-number changes, repeats | from your reference file (finale2dorico/experiments/round7/ref-start.dorico, copied to `tests/dorico-files/reference/`): changes are `barNumberChangeIfAny` on hidden bar divisions **in the top stave's stream**; pick-up = bar 0 (your "bar 2"/"bar 8" fit only that) |

`tests/parity/model_vs_python.py` lists these as explained; anything else fails the check.

## Waiting on you

T. ~~**Timeline reference**~~ **Done 2026-11-01**: your exports match the timeline event for
   event (9 flows). Optional leftovers (TIMELINE.md "Still open"): a re-export of flow 4 with a
   sound loaded (pass order of "repeat 3 times", To Coda), a plain repeat's count, a 29.97 dfps copy.

0. ~~**Findings v2 golden**~~ **Done 2026-10-31** (your OK): f2d's `review.json` (40 review + 8
   convert cases) re-recorded with the additive v2 fields; text output and every v1 field
   identical (checked finding by finding). Golden 110/110.

1. ~~Open the two files in `tests/dorico-check/`~~ **Done** (2026-10-29): both open fine.
2. ~~f2d switch~~ **Done** (2026-10-29, at your quiet point).
3. ~~S4 tool switches~~ **Done** in your order: f2d, dorigit, dorico-hp.
4. ~~Subordinate bar numbers~~ **Confirmed** (2026-10-30): bars 8, 9 = "35a", "35b". One
   loose end, **open**: the coda is 2 bars (crotchets 57 and 61) and Dorico shows **35h on the
   second**; the code says 35h, 35i. So Dorico counts one bar fewer somewhere in 35c–35g
   (crotchets 37–57). All music there is in regular 4-crotchet bars. Suspect: the flute's own
   (local) time signatures, 12/8 at crotchet 41 and 4/4 at 45, in the flute's stave stream
   (with a tuplet at 41). The code ignores local time signatures for bar structure. Also
   `countRepeatStructures = false` in the options. Asked the user for the number Dorico shows
   on each bar from 35b to the end (2026-10-30).
5. **Optional:** Horn 2 bar 89 and Timpani bar 69 in test file A
   (`engine/tests/dorico-files/ET The Flying Theme mASTER A-rebuilt.dorico`) are stored as 7
   and 8 f's. Worth a glance only if they look odd in Dorico.
6. ~~Retire `dorigit/prototype/`?~~ **Done** (2026-10-30, your OK): `merge_probe.py` and
   `make_test_files.py` moved to `dorigit/research/` and ported to `doricokit` (same output as
   before on both MERGE.md cases and on test files A–D, byte for byte); the listing parity
   test was dropped (golden tests pin the listing).
7. **Windows wheel** (only when a Python tool must run on Windows): `maturin build --target
   x86_64-pc-windows-gnu --zig` fails at link time with `undefined symbol:
   PyInit_doricokit._native` (it writes the dotted module name into the export). Options: name
   the extension module `_native` at the top level, or build natively on Windows with MSVC.
8. ~~**dorigit Windows build:**~~ **Done 2026-10-30** (dorigit session rebuilt `dorigit/dist/windows`).

## Next steps (in order)

1. The 35h/35i question above (small; fix in `dorico-format::bars` once the bar numbers are known).
2. **S5 edit layer (Rust)**: `dorico-edit` crate from dorico-hp's Apply plumbing (transaction,
   events, element tables, automation lanes, tool-owned tagging), built on `tree` and `ids`.
   Apply moves onto it; Python then sends edits ("set these note properties", "add this curve")
   instead of touching trees. Check: no-op edit byte-identical; Apply golden identical.
3. S6 install/factory data/playback (`dorico-paths` already finds the install and AppData).
4. Model extras when needed: ~~key signatures~~ (done 2026-10-31), ~~film data~~ (done
   2026-10-31, timeline session), harmonics and note spelling, options and library (house styles).
4b. **Timeline** (TIMELINE.md "Next"): checked against Dorico (2026-11-01). Next: switch
   dorico-hp's own tempo maths (`model.py`, `render.py`: ignores beat units, relative tempos,
   rit./accel., fermatas, repeats; defaults to 100 bpm) onto it, with the user's OK.
4c. **Encodings catalogue** (MODULE_REVIEW §4 #1; user's next pick after the timeline): build on
   `vocab`: encoders (name -> raw, for f2d's writer and the edit layer), provenance (reference
   file + Dorico version per encoding), a corpus scan for encodings not yet catalogued.
   Include the user-made text playing technique (appearance + composite + text primitive,
   linked to a built-in `pt.*`): encoding in finale2dorico/docs/RESEARCH.md, last section
   (from `HP FLUTE print.dorico`, 2026-10-31); f2d's writer will need an encoder for it.
5. **Non-standard dynamics check** (your note 2026-10-30): a reviewer finding such as
   "unusual-dynamic: …" for a dynamic Dorico doesn't offer by default (not possibile, which is
   standard on f/p) so custom dynamics are pointed out
   but kept. Belongs to f2d's reviewer now (its agent's call) or the Rust findings layer (S9).

## How to resume

```sh
cd ~/dev/dorico-test
. engine/scripts/dev-env.sh           # Rust, zig shims, cmake/ninja, uv
uv sync                               # builds doricokit (Rust) into .venv; ~20 s
engine/scripts/test-all.sh            # fast: Rust, Python, parity subset, golden subset (~3 min)
engine/scripts/test-all.sh --full     # whole corpus + every golden case (~12 min)
uv run python engine/tests/golden/golden.py check --only dorico-hp   # one tool's golden cases
```

## Session log

- **Timeline session, cont.** (2026-11-01): the user's MIDI exports settled the rules (rit.
  steps, stored start tempo, fermatas, caesura, relative/reset tempos, jumps at the mark,
  "repeat 3 times" = 4 passes, default 120); 9 flows match event for event.
- **Timeline session** (2026-10-31, user's pick after the module review): new `dorico-timeline`
  crate + `dorico-format::timecode` + time decoders in `vocab` + film/pauses/endings/playback
  options in the model + `doricokit.timeline`; pause-name fix; reference project for the user.
  User decisions: notated **and** performed order from the start; reference files OK; support
  every frame rate (note what Dorico offers); MusicXML module deferred. Golden unchanged.

- **Session 3** (2026-10-31, hand-over from the review session): Task A (one copy of every
  decoder: `vocab`, shared dynamics; model keys/tuplets/names/version forms; dorigit and
  `doricokit.view` switched) and Task B (findings v2). Decisions: model keeps raw player names
  (`label` added) and `level` stays the machine value (`name` added), so dorico-hp output is
  unchanged; findings v2 keeps the v1 names (`pos`, `where`, `player`) instead of renaming to the
  plan's `position`/`staff` (you chose additive); dorigit's listing not restructured (plan
  above). Golden: dorigit and dorico-hp identical; f2d `review.json` re-recorded (additive only,
  your OK). Read-model parity: 281 new differences vs f2d's old reader, all combined dynamics now
  named ("kDown2/0" -> "ff-mp"); the parity test now translates the old raw form.

- **Session 2** (2026-10-30): your answers: subordinate numbers confirmed ("35a", "35b"); "f
  possibile" is not standard (*corrected by you later that day: possibile is standard on f or p*; keep custom dynamics found in scores,
  never create them); retire the prototype. Done: prototype retired, `merge_probe.py` and
  `make_test_files.py` ported to `doricokit` in `dorigit/research/` (identical output), new
  `doricokit.listing` (PyO3 `listing_json`), prototype parity test removed. Open: whether the
  reference file's last bar shows as 35i.

- **Session 1, cont.** (2026-10-29): your answers (Dorico check OK; f2d at a quiet point; S4
  order f2d -> dorigit -> dorico-hp; f possibile; reference file). f2d golden baseline (54
  cases), f2d switched to doricokit (S2) with identical output, then its reviewer onto the
  model (S4). Bars moved to `dorico-format::bars` with Dorico's displayed numbers; dorigit's
  listing uses them. dorico-hp `notation.py` onto the model (Apply output identical). Old
  readers kept as oracles. `test-all.sh` runs f2d's unit tests too.
- **Session 1** (2026-10-29): read the brief; agreed with the user: tar backup + `git mv`
  (`~/dev/dorico-test-backups/2026-10-29-before-engine.tar.gz`, includes the git index), root
  Cargo workspace, no edits under `finale2dorico/`, scope S0–S3 + S4 engine side. Did S0, S1,
  S2 (dorico-hp), S3, S4 engine side. Found and fixed: Rust zip writer stored folders
  uncompressed. Apply got faster (10.7 s → 8.3 s on the HP LASS3 project) from the Rust codec.
