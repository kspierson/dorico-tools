# finale2dorico: design

*Started 2026-10-26. Status and next steps: [STATUS.md](STATUS.md). Format evidence: [RESEARCH.md](RESEARCH.md).*

## Goal

Convert Finale scores (`.musx`, Finale 2014+, and legacy `.mus`, Finale 1.0-2012)
**directly** into Dorico projects (`.dorico`), with accurate notation and Dorico's own
default ("standard") playback. MusicXML is not in the path: it loses information and is
what produces the clean-up work this tool is meant to remove.

Non-goals (for now): carrying Finale playback (Human Playback, MIDI data, VST setups) into
Dorico; reproducing Finale's page layout pixel for pixel.

## Architecture

```
 .musx ──┐                           ┌───────────────┐
 .mus  ──┼─▶ Finale reader ─▶ Score IR (JSON) ─▶ Dorico writer ─▶ .dorico (zip)
 (.enigmaxml)                        └───────────────┘      ▲
                                                             │ factory data read at run time
                                                   user's Dorico install (instruments.xml,
                                                   instrument names, tutorial projects as seeds)
```

- **Reader** turns Finale data into the **Score IR** ([f2d/ir.py](../f2d/ir.py)): the music
  *as notated* (positions/durations in crotchets as exact fractions, concert pitch with
  spelling, ties, tuplets, voices, clefs, keys, time signatures, dynamics, slurs, hairpins).
- **Writer** ([f2d/dorico/writer.py](../f2d/dorico/writer.py)) turns the IR into Dorico's
  model and idioms: tie chains become one note with forced split durations, rests are left
  to Dorico, instruments come from the installed Dorico's factory definitions.
- The IR is the contract between the two halves. `python3 -m f2d ir X.musx` prints it,
  and `convert` accepts an IR `.json`, so either half can be tested or replaced alone.

### Two readers, one IR

| Reader | Status | Covers |
|---|---|---|
| **Full** (C++ `f2d-extract` on [musxdom](https://github.com/openmusx/musxdom) + [finale-mus-reader](https://github.com/openmusx/finale-mus-reader), MIT; then [f2d/finale/facts.py](../f2d/finale/facts.py)) | **Working; the default** when the extractor is built | `.musx` and legacy `.mus` (Finale 1.0-2012). Uses musxdom's interpretation: entry frames, tuplet spans, ties incl. workarounds, display vs actual time signatures, instrument grouping and names, part-aware staff clefs. |
| **Bootstrap** (Python, [f2d/finale/enigma.py](../f2d/finale/enigma.py)) | Fallback (`--reader bootstrap`) | `.musx` only; interprets EnigmaXML directly. Kept so the tool still works without a C++ build, and as a cross-check. |

Why musxdom: Finale's EnigmaXML is a raw dump of internal records. The hard parts (entry
frames, interpreted iterators that undo common Finale workarounds, beams over barlines,
pseudo-ties, part-specific data) are what that project does, and it is actively maintained.
Legacy `.mus` support exists only in finale-mus-reader, which builds musxdom documents.
Cross-checking the two readers found four bootstrap bugs musxdom already handled (see
RESEARCH.md §2.3).

**How the full reader is split.** musxdom has no EnigmaXML writer, so the C++ side doesn't
hand back a Finale file; it prints a **facts JSON** (`format: f2d-facts`): what musxdom
calculates (concert pitch per note, entry positions and actual durations, tuplet spans,
tie flags, instrument list and plain names, clef type per staff, time/key signatures,
expressions as text chunks with font kind, smart-shape endpoints) plus raw codes
(articulation and clef glyphs). Python ([facts.py](../f2d/finale/facts.py)) turns that into
the IR with the same glyph/clef tables as the bootstrap reader. Keeping interpretation in
Python keeps the C++ small (one file, [extract/src/main.cpp](../extract/src/main.cpp)) and
makes reader differences easy to diff.

```
 .mus  ───────────────────────────────▶ f2d-extract ─▶ facts JSON ─▶ facts.py ─▶ IR
 .musx ─▶ musx.py (unscramble, gunzip) ─▶ EnigmaXML ─┘
```

**Build.** [extract/CMakeLists.txt](../extract/CMakeLists.txt) fetches pinned revisions:
musxdom at the commit finale-mus-reader pins (4f29939), finale-mus-reader f4b1a33,
smufl-mapping 1b8fbe4 (legacy music-font characters -> SMuFL glyph names, so markings are
recognised by name in any font: Maestro, Engraver, Petrucci, Jazz ...), pugixml 1.15, zlib 1.3.1. In WSL there is no system compiler, so zig is the C/C++ compiler (via
dorigit's shims) with cmake + ninja from `~/.local/opt`; module scanning is switched off
because zig has no clang-scan-deps. Build tree and fetched sources: `extract/build/`
(git-ignored). The Python side finds the binary via `$F2D_EXTRACT`, then
`extract/build/f2d-extract`, then `PATH`.

### Writer strategy: generate, borrowing factory data

A Dorico project's score is one big tree (`score.xml` / `score.dtn`, see dorigit's research).
The writer **generates** it rather than editing a template, because Finale scores need
arbitrary players, flows and instruments.

- **Instruments** are copied from the installed Dorico's `instruments.xml` and
  `l10n/instrumentnames_en.xml` (never shipped with this tool). Matching Finale → Dorico:
  Finale instrument UUID → MusicXML sound ID (table extracted from musxdom/denigma, MIT,
  [f2d/data/finale_instruments.json](../f2d/data/finale_instruments.json)) → Dorico entities
  with that sound ID, ranked by transposition, stave count, name similarity, and "no key
  signature" variants. Older files use a generic "unknown instrument" UUID; then the staff
  name decides (with `^flat()` etc. decoded). No match → Dorico's generic treble/bass/grand
  staff with the Finale name kept.
- **Library** (Round 2): a project must carry a real library, or Dorico draws no noteheads
  and crashes on double-click. Default `--library factory`: the exact entity set a new
  Dorico 5 project carries (IDs in `f2d/data/new_project_library.json`, taken from a
  File > New project), with definitions read from the install's factory XML files, plus the
  instruments/names/clefs the score uses and everything they reference
  ([f2d/dorico/library.py](../f2d/dorico/library.py)). Written both inside `score.xml` and as
  `scorelibrary.dtn`, like Dorico does. `--library seed` (borrow a tutorial project's) and
  `instruments` (Round 1 behaviour) remain for comparison.
- **Options**: by default none are written, so Dorico uses its defaults (old-version files
  open in Dorico 5 with missing options filled in, which is the bet; Round 1 tests it).
  `--options-from-seed` copies engraving/notation/layout options from a seed project.
- **Seed projects**: the Steinberg tutorial projects in `<Dorico>/guidedtutorials/` are
  factory-default Dorico files present on every install, so they can be borrowed from
  without shipping anything.
- **Playback**: nothing written (no `playModeData`, no `enginedata`), so Dorico should apply
  the user's default playback template, which is the "Dorico standard playback" the brief asks for.
  To be confirmed in Round 1.

### Dynamics: grouped and linked, the Dorico way

Finale has no dynamic groups; Dorico does, and both kinds matter for clean Dorico output
(and for condensing):
- **Grouping** (along one staff): a dynamic, the hairpin starting on it (or up to a crotchet
  later), the dynamic at its end, and back-to-back hairpins form one dynamic group (rule taken
  from the user's own grouping of a test file). `Options.group_dynamics`, `dynamic_group_gap`.
- **Linking** (across staves): identical groups at the same position on several staves share
  one element, as in the user's own projects. `Options.link_dynamics`: default `"rhythm"`
  links only staves that also play the same rhythm over the phrase (the user's rule: link
  what would condense together); `"identical"` links any identical groups; `"none"`.

### Players, not staves

Finale is staff-based; Dorico player-based. `f2d/explode.py` (run by `convert`; `--no-explode`
to skip) splits single-staff wind/brass instruments whose staff carries several layers into one
player per part, using Finale's a2 / 1. / 2. markings for single-line bars; numbering follows the
staff names (Horn 1 + Horn 2 staves -> Horns 1&3, 2&4), new players sit next to their source.
`f2d/doublings.py` (also run by `convert`; `--no-doublings`) turns Finale's manual doublings
(staff "Piccolo (Flute 3)" + texts "To Flute" / "Picc.") into one player with both instruments;
each note goes to the instrument named by the latest switch instruction. Dorico places the
change labels itself (the InstrumentChange event only stores label overrides). Finale staff-style
instrument changes (musxdom `getChanges`) are extracted but none occur in the test scores yet.

### Accuracy policy: notation, not just sound

Dorico stores *sounding* durations and computes notation (rests, ties, beams) itself. To
reproduce Finale's notation:

- **Ties**: a tie chain becomes one Dorico note whose `kNoteSplitDurations` lists Finale's
  notated pieces (Dorico's "force duration"). Option `--force-durations`:
  `ties` (default) only for tie chains; `all` for every note (and explicit forced rests);
  `none` lets Dorico decide. Round 1 compares `ties` and `all`.
- **Rests**: left implicit unless hidden or `--force-durations all`. Later: compare with
  Dorico's rest grouping and force only where they differ.
- Later: beam groups, stem directions (partly done), accidental visibility (partly),
  enharmonic spelling is preserved (concert letter in `kNoteSpelling`).

## Module map

| Path | What |
|---|---|
| `f2d/__main__.py` | CLI: `convert`, `ir`, `enigma`, `dump`; `--reader auto|musxdom|bootstrap` |
| `f2d/ir.py` | Score IR dataclasses + JSON |
| `f2d/finale/musx.py` | `.musx` → EnigmaXML (vendored from dorico-hp) |
| `f2d/finale/enigma.py` | bootstrap EnigmaXML → IR reader (also holds the glyph/clef tables) |
| `f2d/finale/extract.py` | finds and runs `f2d-extract`; unpacks `.musx` for it |
| `f2d/finale/facts.py` | full reader: facts JSON → IR |
| `f2d/explode.py` | IR transform: shared staves (layers) → one player per part |
| `f2d/doublings.py` | IR transform: staves switching instrument by text ("To Flute") → one player, several instruments |
| `f2d/dorico/read.py` | reviewer's view of the shared read model (`doricokit.model`) |
| `f2d/review.py` | reviewer: report-only checks on any .dorico (`f2d review`) |
| `extract/` | the C++ extractor (`src/main.cpp`, `CMakeLists.txt`) |
| `f2d/dorico/install.py` | find Dorico install; instrument database; instrument matching |
| `f2d/dorico/library.py` | project library built from the install's factory files |
| `f2d/data/new_project_library.json` | entity IDs a new Dorico project carries (no definitions) |
| `f2d/dorico/tree.py` | helpers for building Dorico trees |
| `f2d/dorico/writer.py` | IR → `.dorico` |
| `f2d/data/finale_instruments.json` | Finale instrument UUID → name + MusicXML sound ID |
| `tests/test_core.py`, `tests/test_facts.py` | unit tests |
| `tests/oracle.py` | reader vs the MusicXML each HPCaptures file was made from (`--reader musxdom`) |
| `tests/compare_readers.py` | bootstrap vs full reader, field by field |
| `tests/compare_mus.py` | `.mus` vs Finale 27's own conversion of the same file (516 pairs) |
| `experiments/` | generators for Dorico test rounds + results |
| `research/tools/` | format study tools (explode, outline, examples, props, eventkinds) |

## Relationship to the other projects

- **Shared engine** (`engine/`, Project S): owns the Dorico format (DTN codec, container, read
  model). f2d imports it as `doricokit` (`format`, `container`, `model`); no local copies.
- **dorigit** (separate session): Its `show` command is handy to inspect our output.
- **dorico-hp**: owns `musx.py` (vendored) and the HPCaptures test pieces we use as an oracle.
  Its Human Playback output could later be applied to converted projects; this tool keeps
  Dorico's default playback.

## Shared engine across the Dorico tools

Inventory of duplicated modules and the proposal (one Rust engine, Python bindings) are in
[SHARED_ENGINE.md](SHARED_ENGINE.md). Companion tools (cleaner, editor, reviewer) are proposed
in [UTILITIES.md](UTILITIES.md). Note: dorico-hp already reads finale2dorico's IR JSON,
so `f2d/ir.py` changes must stay backward compatible.

## Licensing notes

musxdom, denigma, finale-mus-reader and smufl-mapping are MIT (Robert G. Patterson).
smufl-mapping's legacy font tables are partly MakeMusic-derived (see its NOTICE); we embed
only a few codepoints for the bootstrap reader. Nothing from Steinberg is distributed: all
Dorico data is read from the user's installation.
