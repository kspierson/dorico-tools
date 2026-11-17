# Engine module review (2026-10-31)

*A snapshot review of what the shared engine has, how mature each piece is, what is left, and
which modules it still lacks. The plan stays in `../../PLANNED_WORK.md` §2; live state stays in
[STATUS.md](STATUS.md). Re-do this review when a phase finishes rather than editing it piecemeal.*

Test run at review time: `engine/scripts/test-all.sh` (fast set): all green (Rust, Python, parity subset, golden 71/71).

## 1. Maturity scale

| Level | Meaning |
|---|---|
| **5 Mature** | Complete for today's needs, used by every tool that needs it, parity/golden tested |
| **4 Solid** | In daily use by tools; known gaps are listed and small |
| **3 Working** | Works and is used, but narrow, one consumer, thin tests, or the API will change |
| **2 Prototype** | Exists in Python or inside one tool; shape not final; not yet in Rust |
| **1 Planned** | Only in the plan (§2.3 module map) |

## 2. What exists today

### 2.1 Rust crates

| Module | What it does | Used by | Maturity | Work left |
|---|---|---|---|---|
| `dorico-format::dtn` + `xml` | `score.dtn` ⇄ tree; lossless XML form | all three tools (directly or via `doricokit.format`) | **5** | Only real-file tests (opt-in, personal corpus); no unit tests in `dtn.rs`/`xml.rs`. Add small synthetic round-trip tests and malformed-input tests so the codec is covered without the user's files. Check `DTN_VERSION` handling once Dorico 6 files exist |
| `dorico-format::container` | the `.dorico` zip, entry order/timestamps kept, atomic write | all three | **5** | No unit tests in the file (covered by golden + real files). Windows Python wheel blocked (see bridge) |
| `dorico-format::ratio` | exact positions `"81/4"`, ticks (half-to-even) | all | **5** | — |
| `dorico-format::bars` | bar list with Dorico's displayed numbers (pick-ups, number changes, "35a") | dorico-model, dorigit listing | **4** | Open 35h/35i question: local (per-stave) time signatures ignored for bar structure. `countRepeatStructures` option not read |
| `dorico-format::dynamics` | every default Dorico dynamic named; modifiers; readable fallback for custom ones; machine levels (`level`) | dorigit listing, `dorico-model` (all tools) | **5** | Done 2026-10-31: the one dynamics decoder |
| `dorico-format::vocab` | Dorico's vocabulary: values, glyphs, technique/tuplet/key/clef/ottava/ornament/arpeggio/pause/divisi/articulation names, pitch spelling, version forms | dorico-model, listing, dorigit listing + notation | **4** | New 2026-10-31. Grow it with every new encoding (S10 can generate docs from it) |
| `dorico-format::tree` | builders, DTN-safe edits, property tables, `event_head` | dorigit research; reference for ports | **3** | Few Rust consumers yet. Python copies still live in dorico-hp `project.py` and f2d `tree.py` (decision 3: they go when those tools move to S5/S13) |
| `dorico-format::ids` | next ID, counters, collision check | Python edit + cleaner (`ids.check`) | **3** | Only allocation + check. No renumbering (needed for dorigit merge, inserts, cross-project copy) |
| `dorico-format::model` + `diff` | **dorigit's listing model** (one row per event) and its diff | dorigit (`show`, `diff`, textconv, app) | **4** for dorigit | This is a **second read model** next to `dorico-model`. Decision 4 kept it to keep dorigit's output stable. Plan: rebuild the listing on `dorico-model` and move `diff` with it (see §4, "compare") |
| `dorico-format::playback` | which plug-ins `enginedata` loads | dorigit policy | **3** | Narrow: plug-in counts only. Expression maps, endpoints, playback templates still in dorico-hp `playback.py` (S6) |
| `dorico-model` | the one read model: flows, bars, parts, staves, voices, notes, dynamics groups, marks, tempos, repeats, divisi, ranges | f2d reviewer, cleaner, dorico-hp `notation.py`, dorigit listing (bars) and MEI | **4** core / **3** coverage | See §2.4 for the list of gaps (keys, tuplets, many raw marks, film, options/library). `Mark.detail` is string-to-string: fine for reading, too loose for edit/build round trips. One unit test; the rest needs the personal corpus |
| `dorico-paths` | host + WSL ⇄ Windows paths, Dorico install/AppData/Documents, `corpus.toml` | all (tests, tools) | **4** | Install detection is also re-implemented in f2d `install.py` (`CANDIDATE_DIRS`) and dorico-hp `tools/dorico_maps.py`; switch them (S6). `corpus.toml` hard-codes Dorico 5 |
| `doricokit-py` | PyO3 bridge (`doricokit._native`) | every Python tool | **4** (temporary) | Windows wheel fails to link (`PyInit_doricokit._native`); fix only when a Python tool must run on Windows. Removed in S14 |

### 2.2 Python package `doricokit`

| Module | What it does | Maturity | Work left |
|---|---|---|---|
| `format`, `container`, `positions`, `ids`, `paths`, `model`, `listing` | thin wrappers over Rust | **5** (as wrappers) | Nothing until S14 removes them |
| `view` | the reviewer's typed view over `model` | **3** | Transitional (decision 8); goes when the reviewer moves to Rust (S12) |
| `edit` | S5 prototype: transaction, `remove_event`, `link_dynamic_group`, content equality, safe save | **2** | Two operations so far. **Duplicates dorico-hp's `project.py`** (its own transaction, `new_id`, property set/get, automation lanes, curves). Neither is the Rust `dorico-edit` yet |
| `findings` | `Finding` (**v2** since 2026-10-31: + tool, flow_id, bar, beat, staves, events, change) + check/rule registry | **3** | v2 done (additive over v1; CHANGES.md). Rust type with the S9 crate |
| `review` | 5 checks (dynamics, duplicates, range, mutes, sections) | **3** | Range check uses concert pitch only; "unusual dynamic" check requested (STATUS next step 5). Port in S12 |
| `clean` | 2 rules (`dedupe`, `link`) | **2** | More rules per `finale2dorico/docs/CLEANER.md`; needs the real edit layer |

### 2.3 Planned modules not started in the engine

| Module (plan §2.3) | Where the code lives now | Maturity | Notes |
|---|---|---|---|
| `dorico-edit` (S5) | dorico-hp `project.py`/`apply.py` (~600 lines) + `doricokit.edit` | **2** | The most-blocking gap: cleaner, house styles, harpgliss, dorigit merge (M2) and the batch editor all wait on it |
| `dorico-install` (S6) | f2d `install.py`, `library.py`, `data/`; dorico-hp `dorico_maps.py`; `dorico-paths` finds the folder | **2** | Version-aware factory data; instrument transpositions belong here too |
| `dorico-playback` (S6) | dorigit `playback.rs`; dorico-hp `playback.py` (expression maps, setup); `doricokit.dynlevels` (Dorico's playback dynamic levels + curve, measured 2026-11-01) | **2** | Also the encoding of automation lanes incl. the Dynamics lane `kDynamic` (now in dorico-hp `project.py`) |
| `midi` (S9) | dorico-hp `smf.py` (read), `render.py` (write), `tools/compare_midi.py` | **2** | Two VLQ implementations |
| `findings` in Rust (S9) | `doricokit.findings` | **2** | v2 schema done (2026-10-31); port with S9 |
| `automation` (S9) | f2d `research/tools/dorico_remote.ps1`, `pdf_pages.ps1`, `pdf_index.py` | **2** (research) | dorigit V1 (comparison PDF) and "Open in Dorico at bar N" need it |
| `score-ir` (S8/S13) | f2d `ir.py` | **2** | No `ir_version` or schema yet; dorico-hp reads its JSON |
| `score-transforms` (S8/S13) | f2d `explode.py`, `doublings.py` | **2** | The cleaner wants explode/implode for MusicXML imports |
| `dorico-build` (S8/S13) | f2d `writer.py` (~1,540), `layout.py`, `library.py`, `tree.py` | **3** inside f2d | Works daily for the converter; not shared yet |
| `finale-read` (S7/S13) | f2d `extract/` (C++), `facts.py` (~1,780), `enigma.py`, `musx.py`; dorico-hp `musx.py` | **3** inside f2d | `enigma.py` to be demoted to an oracle |

### 2.4 Read-model gaps (from REQUESTS.md and this review)

*Update 2026-10-31 (engine session 3): items 1–5 and 10 done (CHANGES.md "engine session 3");
the names live in the new `dorico-format::vocab`.*

Ordered by how many tools are waiting:

1. ~~**Key signatures**~~ **Done**: `Flow.keys` (fifths, mode, tonic, name) + stave marks of kind `key` (local keys).
2. ~~**Tuplets**~~ **Done**: `Mark.tuplet` (num, den, note value, dots, unit, name).
3. ~~**Shared dynamics decoder**~~ **Done**: `dynamics::level` (machine) + `DynamicItem.name` (`describe`).
4. ~~**Technique names**~~ **Done**: `vocab::technique_appearances` (public, `name` first); dorigit uses it.
5. ~~**Raw mark kinds**~~ **Done**: glissando line names + `from_event`/`to_event`, `line`, `stave count change`, `bar rest`, `ornament`, `pause`, arpeggio names. Not decoded: trill interval (layout-scoped property), local time signatures on staves (`BarDivision` stave marks).
6. **Note spelling and harmonics**: `kNoteSpelling` and `kNoteHarmonic*` stay raw in `props`; ties not modelled as such.
7. **Film data**: video per flow, markers (dorigit's listing already reads them).
8. **Options, layouts, library** (styles, fonts, paragraph styles, page templates): only dorigit's listing flattens them as path → value. Project A depends on a real model of these.
9. Not read at all yet: lyrics, chord symbols, figured bass, cues, condensing, frames/pages.
10. ~~**Dorico version differences**~~ **Done**: `Note.muted` (`true`/`kAlways`), glissando `playback` (absent = `kChromatic`), `Player.label` (♭). The 4.3 literal "(B Flat)" vs 5.1 "(B{@flat@})" names still differ as text (Dorico renamed them).

### 2.5 Cross-cutting findings

- **Duplication still present** (log in PLANNED_WORK §2.2):
  two Rust read models (`dorico-format::model` and `dorico-model`; they now share every decoder,
  see STATUS.md "Listing model: plan");
  ~~two dynamics decoders~~ (done 2026-10-31: one, `dorico-format::dynamics`);
  two Python edit layers (`doricokit.edit`, dorico-hp `project.py`);
  Dorico install detection three times (`dorico-paths`, f2d `install.py`, dorico-hp `dorico_maps.py`);
  ~~`technique_appearances` copied into dorigit-core~~ (done);
  ~~readable names for marks split between `dorico-model`, dorigit-core `listing.rs` and `notation.rs`~~
  (done: `dorico-format::vocab`; also tuplet ×2, key, glyph ×3, pitch spelling ×2, tempo, player
  name, element tables).
- **Tests depend on personal files.** Most coverage comes from the user's corpus (opt-in) and the
  golden set. Small committed fixtures (built by the engine itself, no Steinberg library data)
  would let `cargo test` mean something on any machine.
- **Format knowledge is scattered** across three `RESEARCH.md` files and constants in code (S10 not started).
- **Open requests**: 5 rows in `REQUESTS.md`, all for `dorico-model`.

## 3. Capability coverage ("completeness")

What a complete engine for these tools has to do, and where it stands:

| Capability | Today | Gap |
|---|---|---|
| Read a project losslessly | ✅ codec + container | — |
| Understand the music | 🟡 `dorico-model` | §2.4 |
| Understand settings and styles | 🔴 flattened in listing only | options/library model |
| Edit an existing project | 🔴 Python prototypes ×2 | `dorico-edit` (S5) |
| Build a project from scratch | 🟡 inside f2d (Python) | `dorico-build` (S8/S13) |
| Import from other formats | 🟡 Finale only, inside f2d | `finale-read` (MusicXML: Dorico's own import/export is enough for now, user 2026-10-31) |
| Compare two versions | 🟡 dorigit listing diff | model-based diff, position mapping (§4) |
| Check and report | 🟡 Python reviewer + findings v1 | findings v2, Rust registry |
| Validate before saving | 🔴 ID counters only | integrity checker (§4) |
| Preview notation | 🟡 MEI inside dorigit-core | move to engine (§4) |
| Time (bars ⇄ seconds ⇄ timecode) | 🔴 scattered (`render.py`, dorigit `timecode`) | timeline (§4) |
| Playback data | 🟡 split between dorigit and dorico-hp | `dorico-playback` (S6) |
| Install / factory data | 🟡 inside f2d | `dorico-install` (S6) |
| MIDI | 🟡 inside dorico-hp | `midi` (S9) |
| Drive Dorico (open, PDF, go to bar) | 🔴 PowerShell research scripts | `automation` (S9) |

## 4. Suggested new modules (not in the plan's module map)

Ranked by value to the current and planned tools.

| # | Module | What it would do | Who gains | Effort | Notes |
|---|---|---|---|---|---|
| 1 | **`dorico-vocab`** (encodings catalogue) | One table of known Dorico encodings: property names, enum values (glissando types, tuplet note values, arpeggios, ornaments, harmonics), readable names, the Dorico version each form appears in, and the reference file that proved it. Normalises 4.3/5.1/6 forms on read | model, listing, MEI, reviewer, writer, edit; S10 docs can be generated from it | S–M | Fixes the "names in three places" problem and gives the Round method a home. Could live inside `dorico-format` |
| 2 | **`dorico-validate`** (integrity checker) | Beyond `ids::check`: every referenced element/stream/block exists, tables consistent, DTN rules (no empty elements), no orphaned items. Run by `dorico-edit` before every save and by f2d after building | edit, f2d, dorigit merge (M1 needs it), cleaner | M | The cheapest insurance against "Dorico won't open it" |
| 3 | **`timeline`** (time map) | Bars ⇄ positions ⇄ seconds (tempo map incl. gradual tempos) ⇄ timecode ⇄ video offset ⇄ MIDI ticks; position mapping between two versions (inserted/deleted bars) | dorico-hp render, dorigit film (conform, inserts) and merge M4, midi, findings ("at 01:02:03:04") | M | Pulls together `render.py`'s tick maths, dorigit's `timecode`, `bars`, and MERGE.md §7 |
| 4 | **`pitch`** (spelling and transposition) | Decode `kNoteSpelling`; written ⇄ concert pitch from instrument transposition; key signatures as fifths; accidental state in a bar; harp pedal ⇄ pitch-class checks | MEI, reviewer range check, batch editor (respell/transpose), harpgliss (pedal-aware playback), f2d writer | M | `notation.rs` and `pitch_name` each hold part of this today |
| 5 | **`dorico-style`** (options + library model) | Typed engraving/notation/layout options, paragraph and character styles, fonts, page templates: read, diff, copy between projects | house styles (Project A depends on it), dorigit settings lanes, editor "apply house style" | M–L | The plan lists this as "model extras"; it is big enough to be its own module |
| 6 | **`dorico-compare`** (model-based diff) | Diff two `dorico-model` scores by event identity + content (`edit.canon` rules), grouped into lanes and regions; replaces the listing diff | dorigit (diff, merge M1–M3), f2d round testing, dorico-hp `compare_versions.py`, "what did this tool change" reports | M | Also ends the second read model once dorigit moves |
| 7 | **`dorico-notation`** (MEI preview) | Move dorigit-core `notation.rs` into the engine; add articulations, slurs, techniques, text | dorigit, Workbench findings viewer, harpgliss and house-style previews | S (move) | Already offered by dorigit (REQUESTS.md) |
| 8 | ~~`musicxml`~~ **deferred** | MusicXML ⇄ Score IR | — | L | **User 2026-10-31: not needed at this stage**, Dorico's own MusicXML import/export covers it. Maybe later as a standalone converter; f2d's MusicXML oracle (59/59) would be the test |
| 9 | **`testkit`** | Corpus access, golden runner, parity harness, synthetic fixtures built by the engine | every crate and tool | S–M | Moves `golden.py` toward Rust (end goal) and makes tests run without personal files |
| 10 | **`cli-common`** | The §2.6 CLI conventions in code: `-o`, `--json`, `--dry-run`, exit codes, progress events for UI sidecars | every CLI, the apps (S11) | S | Small, prevents drift as tools multiply |

Related, but better as a feature than a module: **snapshot on save**. `dorico-edit`'s save can
call `dorigit-core` to snapshot before and after (PLANNED_WORK §2.11), so every tool change is
undoable.

## 5. Suggested order

1. Read-model gaps 1–4 (§2.4): small, several tools waiting.
2. Findings v2 schema (before more checks and rules are written against v1).
3. `dorico-vocab` + `dorico-validate`: both make S5 safer.
4. **S5 `dorico-edit`** in Rust, folding in `doricokit.edit` and dorico-hp `project.py`.
5. `pitch` and `timeline` (needed by harpgliss, merge M4, film).
6. S6 (install, playback), `dorico-style` (unblocks Project A).
7. `dorico-compare` + `dorico-notation` (dorigit merge), then the rest of the plan (S7–S14). MusicXML deferred (above).

**Next (user, 2026-10-31):** the encodings catalogue (#1) and `timeline` (#3). **Timeline started 2026-10-31**: crate `dorico-timeline` built (tempo map, performed order, timecode at every frame rate, film data in the model); waiting on the user's Dorico reference export for gradual curves, fermatas and play counts ([TIMELINE.md](TIMELINE.md)). Catalogue next. Read-model gaps and findings v2 were handed to session dorico-test-0c, which has started `dorico-format::vocab`, the base the catalogue builds on.
