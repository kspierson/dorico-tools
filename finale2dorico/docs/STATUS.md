# finale2dorico: status and resume notes

*Last updated: 2026-10-26 (session 2). Read this first when picking the work back up.*

> **Shared engine switch (2026-10-29, Project S session).** finale2dorico now uses the shared
> engine (`engine/`, PLANNED_WORK.md §2) for the Dorico file format:
> - `f2d/dtn.py` and `research/tools/dtn.py` are gone. Use `from doricokit import format as dtn`
>   (same `Node`, `Document`, `decode`, `encode`, `to_xml`, `from_xml`; Rust inside).
> - Reading/writing `.dorico` zips: `from doricokit import container` (`container.open_score(path)`,
>   `container.read/write`, `container.Entry`). `writer.write` and `_load_score` use it.
> - The reviewer reads through the shared model: `f2d/dorico/read.py` is now a thin view over
>   `doricokit.model` (same classes; `Project.instruments` is now entity ->
>   `{name, standard_range, advanced_range}`). Review output changed only where the old reader
>   was wrong: divisi staves are separate ("Violin I (divisi staff 2)"), so linked dynamics on
>   divisi staves no longer show as duplicates/repeats; bars after a mid-bar time signature
>   are numbered right; staff order inside could-link messages follows the score.
> - Setup once: `. engine/scripts/dev-env.sh && uv sync` at the repo root. Then
>   `python3 -m f2d ...` works as before (it finds `engine/python`), or `uv run f2d ...`.
> - Safety net: `uv run python engine/tests/golden/golden.py check --only f2d/` (54 cases:
>   convert x8 + review of the output, --dtn, bootstrap reader, ir, review of 40 projects,
>   dump). Conversions were identical before/after. When f2d output changes on purpose,
>   re-record: `... golden.py record --only f2d/`.
> - Want a Dorico-format helper? Ask in `engine/REQUESTS.md` rather than adding a local copy.

> **Engine, 2026-10-31 (session 3):** `f2d review --json` now writes **findings v2**
> (`doricokit.findings`, `FINDINGS_VERSION = 2`): every v1 field unchanged, plus `tool`,
> `flow_id`, `bar`, `beat`, `staves`, `events` (Dorico event IDs) and, for cleaner changes,
> `change: {before, after}`. "not-converted" findings get `tool: "finale2dorico"`. No f2d file
> changed; golden `f2d/` re-recorded with the user's OK (review.json only). Checks that call
> `ctx.add(...)` can pass `staff=` and `events=`. Details: `engine/docs/CHANGES.md`.

## Where things stand

| Area | State | How it was verified |
|---|---|---|
| Research: Finale side | ✅ | musxdom/denigma/finale-mus-reader sources; [RESEARCH.md](RESEARCH.md) §2 |
| Research: Dorico side | 🟡 structure known, writing untested | Decoded your projects + Steinberg tutorial files; RESEARCH.md §3 |
| **Full reader** (C++ `f2d-extract` on musxdom + finale-mus-reader, then `f2d/finale/facts.py`) | ✅ **default**; reads `.musx` and legacy `.mus` | 59/59 HPCaptures files match their MusicXML; 516 legacy `.mus` test documents (Finale 1.0-2012) read with 0 errors and match Finale 27's own conversions (4 explained differences); 5 real scores convert |
| Bootstrap reader (Python, `.musx` only) | ✅ fallback (`--reader bootstrap`) | Same oracle; agrees with the full reader on every field except where the full reader is right (RESEARCH.md §2.3) |
| Dorico writer | 🟡 Dorico opens the files; with a real library noteheads/articulations/slurs/pick-up/grouping look right (Round 2). Now builds the library from the install; dynamics grouped + linked | Rounds 1-2; Round 3 pending |
| Instrument matching | ✅ on test files | Sound-ID matches; unnamed legacy staves → Dorico generic treble/bass/grand staff by clef |
| Round 1 | ✅ done | [experiments/round1-results/README.md](../experiments/round1-results/README.md) |
| Round 2 | ✅ done | [experiments/round2-results/README.md](../experiments/round2-results/README.md) |
| Round 3 | ✅ done | [experiments/round3-results/README.md](../experiments/round3-results/README.md) |
| Round 4 | ✅ done | [experiments/round4-results/README.md](../experiments/round4-results/README.md) (forced ties confirmed) |
| Round 5 | ✅ done | [experiments/round5-results/README.md](../experiments/round5-results/README.md) (user's hand-edited Willow "13" as reference) |
| Reviewer (`f2d review`) | ✅ v1 | 10 checks; text + JSON; on all five real scores (round6/*.review.*) |
| Round 8 | ⏳ waiting on you | [experiments/round8/README.md](../experiments/round8/README.md): supersedes Round 6; nine scores incl. four John Williams; tempo/text/ottava fix/doublings/harp pedals |
| Round 7 | ⏳ waiting on you | [experiments/round7/README.md](../experiments/round7/README.md): add chord symbols, lyrics, repeats/endings, segno/coda, barlines to ref-start.dorico |
| G:\Scores survey | ✅ | 160 Finale files read, 0 errors; 4 with MusicXML checked (RESEARCH.md) |
| Round 6 | ⏳ waiting on you | [experiments/round6/README.md](../experiments/round6/README.md): all 5 real scores; shared staves -> players; trills, glissandi, tremolos, techniques, fp/sffz |

## Estimated progress (2026-10-28)

| Area | Estimate | Notes |
|---|---|---|
| Reading Finale (.musx and .mus) | ~85% | notes/rhythms/voices/layers verified (59 + 516 test files); text/tempo/repeats/lyrics/chords not extracted yet |
| Core notation in Dorico | ~75% | players, notes, ties, tuplets, voices, clefs, keys, meters, pick-ups, dynamics (grouped/linked), hairpins, slurs, articulations, trills, glissandi, tremolos, techniques: confirmed in Dorico |
| Remaining notation | mixed | done 2026-10-28: tempo marks/changes, text, rehearsal marks, fermatas, ottavas, pedals, arpeggios, ornaments, cross-staff. Still: repeats/endings/codas, chord symbols, lyrics (encodings known from Round 7; extractor work needed), percussion kits, staff-style instrument changes, multiple flows. Done since: tempo ranges, staff-only time signatures, harp pedals, doublings |
| Notation fidelity pass | ~20% | rests, beaming, stems, accidentals vs Finale; layout/page formatting not started |
| Converter overall ("fully accurate notation") | ~55-60% | a typical orchestral score converts with its notes and dynamics right; text, tempo and structure are the big gaps |
| Reviewer | ~60% | v1 with 10 checks; tuning from your feedback |
| Cleaner / editor | cleaner v1 | `f2d clean`: dedupe + link (CLEANER.md); editor proposed (UTILITIES.md) |
| Shared engine | proposal | awaiting decisions (SHARED_ENGINE.md) |
| UI (Tauri + Svelte) | 0% | |
| Windows build for others | 0% | |
| Whole project (converter + utilities + UI) | ~35% | |

## Waiting on you

1. **Round 8** (supersedes Round 6): `experiments/round8/` and the Round 7 reference file.
2. **Reviewer**: try `round6/*.review.txt` (or `python3 -m f2d review X.dorico`); which checks
   are useful / noisy? Then the cleaner ([UTILITIES.md](UTILITIES.md)).
3. **Shared engine**: decisions in [SHARED_ENGINE.md](SHARED_ENGINE.md) §4 (location, timing, ownership).
4. Some **real `.mus` files** to test with (none on C:). The 516 test documents are tiny and
   single-purpose; real scores will exercise much more.
5. Confirm the Finale "chromatic transposition = no key signature in the part" assumption
   (Willow's horns/trumpets/clarinets use chromatic transposition).

## Try it

```sh
cd ~/dev/dorico-test/finale2dorico
python3 -m f2d convert "/mnt/c/Users/kspie/Documents/HPCaptures/finale/scores/Willow.musx" -o /tmp/Willow.dorico
python3 -m f2d convert Old.mus -o Old.dorico      # legacy Finale 1.0-2012
python3 -m f2d ir Score.musx > score.json          # inspect the intermediate model (--reader bootstrap|musxdom)
python3 -m unittest discover -s tests -v           # unit tests (no C++ build needed)
H=/mnt/c/Users/kspie/Documents/HPCaptures
python3 tests/oracle.py --reader musxdom $H/finale $H/musicxml    # also musicxml2; drop --reader for bootstrap
python3 tests/compare_readers.py $H/finale $H/finale/scores        # bootstrap vs full reader
python3 tests/compare_mus.py [-v]                                  # .mus vs Finale 27 conversions
python3 tests/real_scores.py                                       # real scores vs Finale's MusicXML (G:\Scores)
python3 experiments/make_round6.py                  # regenerate the current test round (+ reviews: see its README)
```

### Building the extractor (once; ~3 minutes)

```sh
export PATH="$HOME/.local/opt/cmake-3.31.6-linux-x86_64/bin:$HOME/.local/opt/ninja-1.12.1:$HOME/.local/opt/zig-x86_64-linux-0.17.0:$HOME/.local/opt/zig-shims:$PATH"
CC=cc CXX=c++ cmake -S extract -B extract/build -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build extract/build
```

CMake fetches musxdom (4f29939, the revision finale-mus-reader pins), finale-mus-reader
(f4b1a33), pugixml 1.15 and zlib 1.3.1 into `extract/build/_deps` (git-ignored). zig is the
compiler (no system gcc in this WSL; the shims are dorigit's). Without the binary the CLI
falls back to the bootstrap reader for `.musx` and refuses `.mus`.

## Known gaps (most important first)

1. ~~Forced ties~~: confirmed (Round 4).
2. ~~Pick-up bars~~: confirmed (Round 2).
3. **Not converted yet**: text expressions and tempo marks (incl. music-font text such as
   "♩=120"), playing techniques (pizz./arco/mutes), trills, glissandi, lines/brackets, ottavas,
   tremolos (detected, reported), fp/sf/sffz/sfp, lyrics, chord symbols, repeats/endings/codas,
   rehearsal marks, barline types, cross-staff notes, harmonics (done 2026-10-31), noteheads, beaming overrides,
   percussion (Finale percussion maps → Dorico kits), page/system layout.
4. **Composite time signatures** (3/4+2/8, Finale's mixed units) are written as one plain
   meter with the right bar length (warning); Dorico additive meters to do.
5. **Measure-attached markings** are snapped to the nearest note (½ crotchet) or semiquaver grid;
   a marking exactly on a barline goes to the next bar's beat 1 (Willow bar 1/2).
6. **Rests** are left to Dorico (Finale's exact rest notation not reproduced unless `--force-durations all`).
7. **Voices**: Finale layers + voice 2 become Dorico voices in order. Not checked against Dorico's stem rules yet.
8. **Linked parts**: part-specific overrides are ignored (score data only).
9. **Legacy `.mus`**: old files have no instrument types, so matching uses staff names
   (Finale 27 does the same); staff-list expressions may land on extra staves (RESEARCH.md §2.4).
10. **Distribution**: the extractor is built for Linux/WSL only so far. Shipping to others needs
    a Windows build (zig can cross-compile; dorigit's scripts/build-windows.sh is the model).

## Next steps (suggested order)

0. (2026-10-28, done) fermatas, cross-staff notes, tempo marks (+ ranges pending), rit./rall./
   accel., rehearsal marks (incl. boxed numbers in old files), plain text, ottavas (and notes
   under them now sounding pitch), pedal lines, arpeggios, ornaments.
   Also done: harp pedal diagrams and pedal changes; doublings (text switches -> one player,
   two instruments); numeric staff names ("1 2") get their instrument name.
   Also done (Round 7 results): tempo ranges, staff-only time signatures (E.T.).
   Also done (Round 9): breath marks, caesuras, ffz/rffz, mf-mp, subito, niente hairpins.
   Also done (ref-extras2): sf/rf, staff-only breath marks/caesuras, caesura and fermata styles,
   curlew.
   Also done: page size / staff size / condensing / empty-staff hiding in layout options.
   Next: automatic PDF export from Dorico for faster reviews (dorico_remote.ps1 -Discover first).
   Still: percussion kits (structure known, round9-results),
   staff-style instrument changes in the writer, chord symbols / lyrics / repeats / endings /
   segno-coda / barline types (encodings known; need extraction from Finale), then the cleaner
   ([CLEANER.md](CLEANER.md)).

1. Round 6 results; then tempo marks/changes and text items (the biggest remaining gap), ottavas,
   harp pedalling; instrument changes / doublings (Finale staff-style instrument changes ->
   Dorico multi-instrument players; musxdom `InstrumentInfo::getChanges`).
2. Expressions: tempo marks (musxdom gives playback tempo values), technique text → Dorico
   playing techniques, plain text; map music-font characters via smufl-mapping.
   Passage words ("stacc.", "stacc., brillante", "spicc." …) → a custom *text* playing
   technique with the same words linked to the built-in playback technique (`pt.staccato` …),
   as the user does by hand (user decision 2026-10-31; encoding in RESEARCH.md, last section).
3. Remaining smart shapes: trills, glissandi, ottavas, lines; tremolos.
4. Repeats/barlines/rehearsal marks; multi-bar rests are automatic in Dorico.
5. Notation fidelity pass against Finale's rendering (rests, beams, stems, accidentals);
   reference: Dorico's own MusicXML import of the same piece.
6. Percussion; lyrics; chord symbols.
7. Packaging for others: Windows build of `f2d-extract` + the Python tool (or C++ end to end).

## Session log

- **Session 1** (2026-10-26): survey (openmusx libraries incl. new legacy `.mus` reader);
  Dorico project structure study; project skeleton; IR; Dorico writer; bootstrap reader;
  instrument matching from the user's Dorico install; MusicXML oracle (59/59); Round 1 files.
  Blocked: building musxdom (permission).
- **Session 2** (2026-10-26): user OK'd building openmusx code. Built musxdom +
  finale-mus-reader in WSL (zig); wrote `f2d-extract` (facts JSON) and `facts.py`; made it the
  default reader. `.mus` support end to end. Cross-checks: MusicXML oracle 59/59 on both
  readers; bootstrap vs full reader (found and fixed 4 bootstrap bugs: expression positions,
  display time signatures, tremolos as tuplets, grace slashes); 516 `.mus` vs Finale 27
  conversions. Legacy courtesy-accidental rule; staff-aware and snapped clefs; plain player
  names; generic staves for unnamed staves; composite meter length. Regenerated Round 1
  (06 and 12 were wrong because of the bootstrap bugs) and added round1-mus.
- **Session 2, cont.**: Round 1 results (files open; no noteheads with minimal library; wrong
  fileVersion; default playback template = user's "Silence"). Fixed fileVersion (1.1299);
  dynamic grouping from the user's saved 07; Round 2 generated.
- **Session 2, cont.**: Round 2 results (library fixes noteheads; pick-up confirmed). Install-built
  library (`library.py`, ID list from the user's new project); grouping with gaps (matches the
  user's re-saved 07); linked dynamics across staves (encoding from the user's projects);
  Round 3 generated (all files incl. `.mus`). Proposed shared modules (DESIGN.md).
- **Session 2, cont.**: Round 3 results (library works). Rhythm-strict dynamic linking (default);
  hidden expressions skipped; measure-attached markings snapped; native kNoteSplitDurations
  semantics found; SHARED_ENGINE.md (inventory + Rust-engine proposal); Round 4 generated.
- **Session 2, cont.**: Round 4 results: forced ties confirmed. Hairpin ends snap forward to the
  end of the note they're in; small overhangs trimmed when grouping. Round 5 (Willow).
- **Session 3** (2026-10-27): user's hand-edited Willow (13) analysed (round5-results). Shared
  staves exploded into players (`f2d/explode.py`, a2/1./2. aware); trills (incl. "tr♭" custom
  lines, intervals), glissandi (cross-staff, grace notes), single-stem tremolos, playing
  techniques (mute/open/pizz/arco/sord), fp-type combined dynamics, sffz; duplicate hairpins/
  trills/techniques removed; grouping across continuous sound; accidental _v3; grace notes
  before rests kept in place; player numbers from the source; legacy music-font text mapped
  back to raw bytes. UTILITIES.md proposal. Round 6 generated (all five real scores).
- **Session 3, cont.**: user answers: horn bar 7 chords must split (fixed: chords in one layer
  divide top-down); harp glissandi straight (default now); Trex wavy lines = Violin bars 22-25,
  39 (asked). Dynamics after exploding only go to players who play there. Reviewer v1
  (`f2d/dorico/read.py`, `f2d/review.py`, `convert --report`). Goal: one UI (Tauri+Svelte).
- **2026-10-28, cont.**: converter batch: fermatas (were dropped!), cross-staff notes, tempo
  marks with text/metronome/flags (writer flags were wrong), gradual tempos, rehearsal marks,
  text with ♭♯♮, ottavas, pedal lines, arpeggios, ornaments. **Bug found by the real-score oracle:
  notes under 8va/8vb were an octave off** (Finale stores written pitch under ottavas); fixed.
  Asteroid Field now matches Finale's MusicXML exactly (18,965 notes); Raider's March except
  percussion. tests/real_scores.py; tests/test_markings.py; CLEANER.md plan. Round 7 extended
  (tempo range, dotted tempo, staff-only 12/8). Then harp pedals (diagrams + letter changes),
  doublings (`f2d/doublings.py`, E.T.: Piccolo/Flute 3, Oboe 2/English Horn, Piano/Celeste),
  bracket-group names for numeric staff names, explode numbering fixes. HPCaptures
  `VV_Full BWW.mus` is not a Finale file (random bytes). Full regression: 1,363 Finale files
  converted, 1 failure (that file). Round 8 generated (9 scores).
- **2026-10-29, shared engine switch** (Project S session, while this session was paused):
  f2d moved onto `doricokit` (codec, container, read model); see the note at the top.
  69 unit tests pass; golden: conversions identical, review differences all corrections.
- **2026-10-30, Round 11**: user's chord/lyric reference decoded; chord symbols (all qualities,
  intervals, alterations, slash basses, N.C.) and lyrics (hyphenated syllables, extenders, chorus)
  now written as Dorico's own (26/27 chords identical to the user's file). Tests 70; golden 54 ok.
- **2026-10-30, visual pass (Avatar 2m2r, E.T. vs published PDFs) + kMiddle**: lyric kMiddle
  confirmed in Dorico (generated "hal-le-lu-jah", saved and exported). Fixes from the pass:
  (1) full score pitch follows Finale's "Display in Concert Pitch" (`layout.concert_pitch` from
  PartGlobals; a score with no transposing staff, like Avatar, is a score in C); E.T.'s published
  score is transposed, and so are Willow/Trex/WW in Finale (Finale's default) -> now transposing
  full scores; parts stay transposing. (2) Finale hiding only a few staves (E.T.: one divisi
  "Vc. II" staff in 1 of 28) no longer turns on hide-empty-staves for everything (fewer than a
  quarter optional -> all shown; Dorico has no per-staff exception in any file on disk).
  (3) a typed line under ^title() is the subtitle (E.T. "From the Universal Picture ...").
  (4) stacked player numbers ("1"/"2") at bar 1 beat 1 are staff labels: skipped. (5) tempo words
  count as a tempo only on the top staff Finale shows, score-wide, or on at least half the staves
  (E.T. "maestoso" on 4 brass staves is staff text; corpus check: only maestoso, "Slowly add vib.",
  "slowly bend down...", "freely" change; Asteroid Field: a stray "P" on two staves is no
  longer a tempo change). Tests 75; golden re-recorded (54 ok; differences checked: transposition
  type, condensing exclusions, E.T. subtitle/labels/maestoso, Asteroid "P").
  Re-export of E.T. after the fixes: all staves shown, transposed as published. Still open:
  Dorico's default title page has no subtitle; glockenspiel/percussion (known gap); "Ped." vs
  "ff" and "Chimes"/"let ring" text collisions.
  (6) Dorico condensed neighbouring same-instrument players we never grouped (Avatar oboes,
  violas, cellos, cymbals, synth RH/LH; "mf mp div." collided at bar 5): now excluded with
  `groupsToExcludeFromCondensing` (format found by trying it in Dorico; RESEARCH.md). Checked by
  re-exporting 2m2r: matches the published staff layout, only the paired brass condense.
  Seen, not fixed yet: viola "div." above the staff touches Violin 2's "mf" (bar 5); percussion
  (known gap); our
  layouts fit many more bars per system than Finale (page layout / house style is later).
- **2026-10-30, titles as printed**: the extractor now emits `page_texts` (pages, alignment, size,
  text, and which inserts ^title/^composer... each uses). Score Info is used only where Finale
  prints it on page 1; otherwise the text typed in that field's usual place replaces it (title =
  largest centred top text, subtitle = next, composer = top right with further lines as arranger,
  copyright = a page-1 line with "Copyright"/©; "Name ____" fill-ins ignored). Composer, lyricist
  and copyright that Finale never prints are cleared (Dorico's default templates would print
  them); title, subtitle and arranger are kept. Fixes Für Elise "Title Insert", Avatar composer
  "2m2r" (now James Horner, arranger Orch. Jon Kull), empty Raiders/Asteroid Field titles.
  Every change is in the report. Golden re-recorded (Raiders, Asteroid Field: title/composer
  only). E.T. metric modulations "(h = q)" at bars 190/196/292: Dorico encoding unknown, added
  to Round 12. Tests 73.
- **2026-10-30, box codes, trill steps, Round 12**: Finale's handwritten text fonts (Finale/
  Broadway Copyist Text, JazzText) draw a box from characters typed between the letters
  ("[B\r\i\g\ht]" = "Bright" boxed; read from the fonts' glyphs). Now stripped to the words
  (`_unbox` in facts.py; chunk marked `boxed` for a later border); 0 of 2,209 converted files keep
  such codes. "tr 1/2" / "tr WT" trill lines (Avatar, 350) now carry the half/whole step.
  Survey of live film-score lines (dead shapes on deleted notes excluded): 2,243; tab slides
  (328, Avatar) are not printed in the published PDF (2m3a bar 22 trombones: slur only), so they
  stay unconverted. Round 12 asks for harmonics, two-note tremolos, lines with text/hooks,
  technique transition lines and boxed text (none in the 400 Dorico projects on disk). Tests 72.
- **2026-10-31, Round 12 results**: user's `ref-harmonics-lines.dorico` decoded (encodings in
  `experiments/round12/README.md` and RESEARCH.md). Implemented: natural harmonics (Finale circle),
  artificial harmonics (stopped note + diamond a 4th/5th/3rd/octave above -> Dorico partial),
  lines on staves (stave stream, rhythmic-position ends; start words, centred word, end hook,
  end arrow, wavy; Dorico's factory styles copied into the library), gradual "ord." -> "sul pont."
  changes (playing-technique group), "ord."/"sul pont."/"sul tasto" as playing techniques,
  metric modulation (E.T. bar 196), boxed text (Finale enclosures + box codes; Asteroid Field's
  boxed percussion changes match the PDF). Drawn lines that belong to another mark are merged:
  dashed lines after typed "8va" (E.T. 28) stay part of the ottava, "Ped." + solid line (E.T.
  vibraphone) -> pedal line. Plain lines with no words or hooks (Finale drawings, e.g. Avatar's
  7 strokes per cue) are left out and counted. Extractor: custom-line caps/hooks/arrows, note
  `notehead` glyphs. Two-note tremolos were not in the user's file (single-note tremolos on each
  note): redo asked. To verify in Dorico: centred line text, start-only hook (`check/gen-round12.dorico`).
  Later the same day: both confirmed by the user; the redone `ref-tremolos.dorico` gave the
  two-note tremolo encoding, now written for Finale's tremolo tuplets (Trex 4, E.T. 38, Asteroid
  Field 199, generated pair identical to the user's). Tests 88; golden re-recorded, 54 ok.
- **2026-10-31, cleaner v1** ([CLEANER.md](CLEANER.md)): `f2d clean In.dorico [-o Out] [--rules]
  [--dry-run] [--json]`, rules `dedupe` and `link`. Edits the score tree in place; a run with no
  changes copies the file byte for byte; never writes over the input; IDs checked and the
  reviewer re-run after writing. Items count as identical only if the whole Dorico item matches
  apart from IDs (and default-valued / empty property lists), so hand tweaks are kept; such
  sets are listed as "left alone". The reviewer's could-link logic moved to
  `review.section_clusters` (shared; golden unchanged). Sweep over 327 projects (the user's +
  converted): no errors, no ID problems. Willow edit: 4 duplicates removed, 3 sets linked,
  nothing left. Not yet opened in Dorico (`experiments/cleaner/`). Second sweep: 337 projects,
  no errors, 29 dedupes, 5,983 links, 474 left alone. Player labels in reviewer/cleaner output
  now show ♭/♯ instead of Dorico's `{@flat@}` markup (golden review cases re-recorded, 54 ok). Tests 93.
- **2026-10-31, reviewer + cleaner moved to the shared engine** (user: tools must be modular):
  `doricokit.findings` (format + check/rule registry), `doricokit.edit` (edit layer prototype),
  `doricokit.view`/`review` (was `f2d/dorico/read.py`/`f2d/review.py`), `doricokit.clean` (was
  `f2d/clean.py`). f2d keeps wrappers and registers its own "not-converted" check. Outputs
  identical (golden 54/54; engine test-all green, 71/71; Willow clean identical). Engine notes:
  `engine/docs/CHANGES.md`, `STATUS.md`.
  Single diamond noteheads (Asteroid Field, The Thing) and other noteheads: with percussion.
  Tests 86; golden re-recorded (E.T., Asteroid Field, Willow IR), 54 ok.
- **2026-10-29, Round 7 items**: repeats (barline types, repeat barlines, endings, segno/coda/
  D.C./D.S./To Coda/Fine) fully implemented and checked in Dorico; chord symbols and lyrics read
  completely from Finale and written with the known encodings (details in RESEARCH.md). Round 11
  asks the user for chord-variant and lyric-syllable references to finish them. Tests 69.
- **2026-10-29, Round 10 + PDF export**: Dorico remote control connected (user allowed it);
  `make_round10.py` converts 14 scores and has Dorico export each full score as PDF (Dorico lays
  out pages only as viewed: page view + move to end first; save before close; stop if Dorico is
  not idle). Comparing our E.T. PDF with the published one led to: sff from glyph runs,
  metronome marks in Maestro (digits = tuplet glyphs), text 8va/loco -> ottava lines,
  condensing groups from split staves. Dorico crashed once (two opens queued at once) and hung
  once on close (playback engine); the guards now stop the batch instead.
- **2026-10-29, user decisions**: (1) Dorico remote control allowed; (2) untyped concert scores ->
  standard transposing instruments, stated keys honoured and reconciled within a family,
  deviations reported; (3) chord-written paired players are split into players. All implemented
  (FILM_SCORES.md); tests 66.
- **2026-10-28, film-score corpus**: user's D:\ film scores (Avatar, Superman, E.T., Empire,
  Raiders, The Thing): 79 Finale files, all convert ([FILM_SCORES.md](FILM_SCORES.md)). The D:\ E.T.
  `.mus` is the clean 28-staff score (G:\ "bak" is a working copy). Fixed: standard instrument
  names before fuzzy matching (Cello/Bass/Picc./Cfg./G.C. ...), "N - X" and "1)"-style staff
  names. Open questions for the user: C vs transposing instruments in untyped concert scores;
  splitting chord-written paired players.
- **2026-10-28, layout + E.T. review**: user's first E.T. look: six flutes, squashed staves in
  Engrave mode. Findings: the E.T. file prints 45 staves including exact copies (staves 28/1,
  33/6, 45/21, 46/22 now warned as "same notes") and new mostly-empty staves (third flute from
  bar 110, English horn, percussion, xylophone): it is a working copy, so the six flutes are
  Finale's. Squashing: the writer wrote no layout options. Now: extractor emits the page layout;
  writer sets page size / staff size (fit to page), empty-staff hiding, condensing
  (RESEARCH.md "Page layout"). Review speed-up: Dorico's Remote Control API has
  `File.Open`, `Window.SwitchMode?WindowMode=kPrintMode`, `Print.ExportCurrentLayoutAsPDF`,
  `Print.ExportAllLayoutsAsPDF` (names from Dorico5.exe); parameters still to read with
  research/tools/dorico_remote.ps1 -Discover (Windows side; WSL can't reach port 4560; needs the
  user to allow the connection once). Finale's sample files found (RESEARCH.md).
- **2026-10-28, ref-extras2**: second extras file (two players) decoded: sf (Sfz without z),
  staff-only pauses (stave stream), 5 caesura styles, 7 fermata lengths + curlew. All
  implemented; the old "breath marks on only some staves skipped" warning is gone (those marks
  now go on their own staves).
- **2026-10-28, Round 9 results**: user's extras file decoded (round9-results/README.md).
  Implemented ffz/rffz, mf-mp family, subito, niente hairpins, breath marks (4 styles),
  caesuras (written only where every playing staff has one: staff-only encoding unknown).
  Percussion kit structure decoded from the user's BLACK LABEL project (not implemented yet).
- **2026-10-28, Round 7 results**: user's reference markings decoded (round7-results/README.md,
  RESEARCH.md "Round 7 encodings"): chord symbols, lyrics, barline types, endings, segno/coda/
  jumps, tempo range, dotted tempo, staff-only 12/8 (stave BarDivision + hidden 12:8 tuplet).
  Implemented: tempo ranges (`tempoValueRange`), staff-only time signatures (extractor
  `time_changes` -> `Staff.time_signatures` + hidden tuplets -> stave stream; E.T. 9 staves).
  Explode now keeps ottavas, pedals and harp pedals on the split staves (were dropped).
- **2026-10-28**: decisions: bar 11 OK; no-key-sig parts OK (changeable in Dorico); shared
  engine owned by a separate session; cleaner next. Explored dorigit (codec/model/diff; no
  marking knowledge) and mined the user's 47 projects for encodings (RESEARCH.md); surveyed
  G:\Scores (160 files, 0 errors) and checked 4 John Williams scores against their MusicXML
  (oracle now resets per bar and tolerates export rounding). Round 7 reference file prepared.
- **Cleanup** (2026-10-28): old rounds 1-5 removed (generated files; checklists archived in
  `experiments/history/`, results and your files kept in `roundN-results/`), old generators and
  decoded copies removed, session scratch cleared; `experiments/README.md` indexes the rounds.
- **Session 3, cont.**: Trex's wavy lines = half-step trills (user). Added smufl-mapping to the
  extractor: markings recognised by SMuFL glyph name in any font (Trex: EngraverFontExtras
  "tr♭"); zero-length trill lines = note trills; "tr" articulations -> trills; up/down bow ->
  playing techniques. Round 6 regenerated with reviews.
