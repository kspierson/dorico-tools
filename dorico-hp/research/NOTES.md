# Human Playback for Dorico: research notes

Goal: rebuild Finale's Human Playback (HP) so it shapes playback of Dorico projects, with
settings you can tune per library (LASS, SWAM, Infinite, Pianoteq…), per instrument
and per project. Adds adjustable note-by-note vibrato for any VI that exposes vibrato
controls.

## Handoff: start here (last updated 2026-10-31)

**What this is.** A rebuild of Finale's Human Playback (HP) for Dorico, delivered as an
**Apply** step: it reads a `.dorico` project, runs performance rules, and writes
*playback-only* data (note velocity, played start/end offsets, Play-mode controller
automation; later the dynamics lane) into a **copy** of the project. Notation is never
changed. Dorico's expression maps, percussion maps and playback options stay in charge;
Apply only adds what Dorico doesn't do. Python 3.12+ (repo pins 3.15 via uv; system 3.14 also
works) plus `doricokit`, the shared engine (Rust): run `. engine/scripts/dev-env.sh && uv sync`
once at the repo root. **Since 2026-10-29 (Project S S2/S3)** the DTN codec, the .dorico zip and
`frac`/`frac_str`/ticks come from `doricokit`; `doricohp/dtn.py` is gone (kept as a test oracle
in `engine/tests/oracles/`). Golden outputs before/after were identical (zip entries;
`engine/docs/STATUS.md`). **S4 (same day):** `notation.py` is now a view over the shared read
model (`doricokit.model`); same classes and shapes, old reader kept as a test oracle. Apply
and render outputs were identical on the golden set (HP LASS3 project + test files A-H).
Changes where it matters: pick-up bars (bar 0) and `minimumNotatedLength` now shape
`bar_starts`, rich-text Text items are read, "f possibile" is named (was "?"), and
`FlowNotation.bar_labels` gives Dorico's displayed bar numbers. Combined dynamics (fp, ...)
are still not passed to the rules (as before), though the model has them.
Usage: `../README.md`. The user handles all commits/pushes; leave changes uncommitted.

**Where it is heading.** The user's top priority is "Project S" (`../../PLANNED_WORK.md` §2):
one shared Rust engine (`engine/`, Python bindings `doricokit`) for dorigit, dorico-hp and
finale2dorico. It plans to move dorico-hp's generic plumbing out (DTN codec `dtn.py`,
container/edit layer `project.py` + the Apply plumbing → `dorico-edit`, `notation.py` →
`dorico-model`, `playback.py` + `tools/dorico_maps.py` → `dorico-playback`/`dorico-install`,
`smf.py`/`render.py` → `midi`, `musx.py` → `finale-read`). The HP engine, profiles and
rules stay in dorico-hp. **Don't add new copies of shared code**; log any new duplication
in PLANNED_WORK.md §2.2. Note for S7: `doricohp/musx.py` is not dead code: `python3 -m
doricohp.musx --hp FILE.musx` (HP settings saved in a score) and the raw EnigmaXML dump are
used during research; the shared Finale reader must offer both before it is deleted.
Golden output for S0: `python3 -m doricohp.apply "<HP LASS3 project>" OUT.dorico --style
Romantic` is deterministic (no randomness); hash OUT.dorico and its `.hp-apply.json`.

### Status at a glance

| Area | State |
|---|---|
| Finale HP measured | ✅ 16 styles × 59 test pieces (with dynamic values), 5 user scores HP on/off, extra pieces (Last Temptation: espressivo + harp). `hp-measurements.md`, `hp-engine.md` |
| Finale HP internals | ✅ presets extracted (`hp-presets.tsv`), pipeline mapped (`hp-engine.md`). 🟡 formulas only partly read from the decompile; measurements were enough so far |
| Dorico storage (velocity, offsets, automation, routing, maps, options, techniques) | ✅ confirmed (see "What Dorico stores" below). ❌ dynamics lane (test I), text items (no example yet) |
| User's playback habits (score vs playback copies, printed score) | ✅ `score-vs-playback.md` |
| Engine v1 (model, profiles, rules, MIDI render) | ✅ reproduces HP accents/feel/dynamics/hairpins on the test pieces (`engine-v1-measurements.md`) |
| Apply | 🟡 writes attack velocity, timing + explicit played lengths, vibrato CC1, passage words (stacc./leggiero…), time-capped short articulations, and **the Dynamics lane** (since 2026-11-01: `lane.py`, spans where shaping ≠ written, accents added back). Rubato not implemented (test L) |
| HP FLUTE print vs playback (2026-10-31) | ✅ compared (`score-vs-playback.md` → "HP FLUTE print vs playback copies"). Apply on the print copy: 221/231 Flute 1 notes within 15 % of the user's playback copy (Dorico alone: 105). Rules added: slur ends under stacc., brillante ≈ 40 ms, open hairpins = local swells, technique words + `pt.user.*` = map-only. Golden re-recorded |
| Listening | 🟡 v1 heard by the user: articulations lost (fixed), "some instruments wrongly patched" (unexplained, routing proven unchanged). v2 copies await the user. Code is now past v2 (passages + time caps) with no listening copy yet |
| latency-reporter plug-in | brief only, separate project `../../latency-reporter/` (another agent) |

### Waiting on the user (ask about these first)

0. **SWAM Woodwinds tuning (Project C, 2026-11-01)**: `HP WW.dorico` (woodwinds, playback copy)
   inventoried, plug-in settings decoded (`vi/swam.md`). The installed SWAM Woodwinds 2.8.1
   doesn't play in vi-render, so the user renders in **Cubase** from the kit in
   `HPCaptures\swam\` (README.txt there). When WAVs appear in `HPCaptures\swam\renders\`:
   `uv run --with numpy python dorico-hp/tools/swam_measure.py analyse <wav> --name flute`
   (then the other woodwinds), and write the findings + map/profile proposal into `vi/swam.md`.
   Also useful: Dorico File > Export > MIDI of HP WW (CC11/velocity per dynamic with the
   project's curve 0.5, 2.5, 2.5). Score copy of HP WW is a handwritten PDF only.
   **Other VIs** (user wants as few Cubase exports as possible): SWAM Strings 3 measured
   automatically with vi-render (`swam_measure.py render --name violin,...`). Kontakt libraries
   (IW/IB in the template's Kontakt 7, LASS 3/SM brass/Spitfire in HP) go through Cubase:
   **kit ready 2026-11-01 in `HPCaptures\kontakt\`** (README there): two generated track archives
   (`hp-kontakt.xml` 15 tracks, `tpl-kontakt.xml` 21 tracks; every Kontakt slot players use, exact
   Dorico states, HP's Kontakt 6 states converted to Kontakt 7) = 1 import each + 1 Channel Batch
   Export. When WAVs appear in `HPCaptures\kontakt\renders\`:
   `uv run --with numpy python dorico-hp/tools/vi_measure.py analyse <renders>` (plans/results in
   `vi/measurements/`). CinePerc doesn't load in Kontakt 7 (old library): last, loaded by hand.
   Template slot 6: Bassoon 2 and 3 play on the "IW - Saxophones" map (saxophone patches on those
   channels?): asked the user.
   **Round 1 rendered 2026-11-02** (`D:\renders`, analysed → `vi/kontakt.md`): template IW/IB all
   good; template slots 11–20/22/23 are empty Kontakt instances. HP: only harps, celeste and LASS
   Violin I sounded; the rest is on other Kontakt **outputs** (user: one output per player), which
   a Cubase instrument track doesn't carry (slot 34 is empty). Round 1b asked 2026-11-16:
   `HPCaptures\kontakt\README-outputs.txt` (activate all outputs, export to
   `D:\renders\hp-outputs`); then `vi_measure.py analyse /mnt/d/renders/hp-outputs --only hp`.
   Inventory: `vi/inventory.md`.

1. **apply-v2 listen** (`C:\Users\kspie\Documents\HPCaptures\dorico\apply-v2\README.txt`):
   does the original project sound right in their current setup; which instruments sound
   wrongly patched and in which single-feature copy (velocity / timing / vibrato only).
   **Found 2026-11-01:** v1/v2 wrote "vibrato rate" curves on CC14 for the SWAM solo strings,
   and CC14 is their Main Volume (`vi/swam.md`); fixed. **Superseded by apply-v3** (item 2).
2. **apply-v3 listen** (`C:\Users\kspie\Documents\HPCaptures\dorico\apply-v3\README.txt`, made
   2026-11-01): HP FLUTE print after Apply (as is, and with "stacc., brillante"), main HP project
   all / dynamics lane only. First copies with the lane, without the CC14 volume bug.
   (Tests I and I2 answered 2026-11-01: `dorico-integration.md` → "I – dynamics lane".)
3. (answered 2026-11-01) MIDI export includes Play-mode edits (dynamics lane seen).
4. **HP FLUTE print copy: "stacc., brillante" as one custom technique** (user, 2026-11-01:
   a separate text item can't be grouped with the technique and needs its font/size matched
   by hand). A custom text playing technique reading "stacc., brillante", linked to Staccato
   (or the existing one's text changed). Apply reads the words (`passages.technique_flags`).
   Then re-run the comparison on the real file and make a listening copy (print + Apply) for
   the user to judge against `HP FLUTE.dorico`. Text-item storage stays unconfirmed.
5. Optional: Trex re-export from Finale after assigning playback devices (Score Manager);
   harp gliss examples; test N (Dorico compensating insert latency, also for latency-reporter).

### Next steps for the next agent (in order)

1. When the user reports on apply-v2: if a single-feature copy is at fault, fix it (likely
   suspects: LASS/Kontakt patches that use velocity for articulation or legato speed → make
   velocity writing a per-library profile switch; or CC numbers that aren't vibrato for some
   instrument → correct `data/libraries.toml`). Then make **apply-v3** listening copies
   (current code: passages + time-capped staccato) the same way as v2 (commands below).
2. Dynamics lane: **written since 2026-11-01** (`lane.py`, `apply._write_lane`; scale in the shared
   `doricokit.dynlevels`). Tune after the apply-v3 listen: span threshold (0.1 steps), whether
   to add Dorico's beat stress inside spans (currently dropped there, as Apply's own attack
   accents cover it), Dorico's open-hairpin rise (~+1 level) vs the engine's +2 steps, force
   and combined dynamics (not in `dynlevels` yet: sfz/fp levels need a test).
3. Printed flute copy: done 2026-10-31; waiting for the "stacc., brillante" technique (waiting
   item 4), then
   `tools/compare_played.py "PRINT + Apply" "HP FLUTE.dorico" --part "Flute 1" --notes`.
   Accent depth / dynamic spikes (the remaining difference) wait for test I.
4. If MIDI export includes Play-mode data: write the remaining Dorico tests yourself (J
   velocity vs dynamics, K start-offset-only, L tempo, M swing, see `dorico-integration.md`)
   and ask the user only to open + export.
5. Velocity for velocity-dynamics instruments (Pianoteq, harp, percussion): blocked on J.
   Rubato: blocked on L (needs a playback-only tempo route).
6. Unit tests started 2026-10-31 (`tests/test_passages.py`: passage words, technique flags,
   slur ends, open hairpins). Still to add: `apply.played_length/capped_length` and the
   re-apply round trip before Project S moves code.

### How to run

```sh
cd ~/dev/dorico-test/dorico-hp
P="/mnt/c/Users/kspie/Documents/Dorico Projects"
python3 -m doricohp.apply "$P/Harry Potter Cues Plus 5 + LASS3.dorico" /tmp/out.dorico --style Romantic   # report + write
python3 -m doricohp.apply IN.dorico OUT.dorico --only velocity|timing|vibrato --dry-run
python3 -m doricohp.playback IN.dorico                  # plug-in / map / dynamics controller per instrument
python3 -m doricohp.render IN.dorico|IN.musx out.mid --style Standard
python3 tools/render_tests.py captures/engine-v1 01-standard=Standard 04-romantic=Romantic   # engine vs Finale
python3 tools/analyze_capture.py captures/engine-v1 && python3 tools/style_report.py captures/engine-v1
python3 tools/compare_versions.py SCORE PLAYBACK        # .dorico / .musx / .mus / f2d JSON
python3 tools/compare_played.py A.dorico B.dorico --part "Flute 1" [--notes]   # played ms per note (offsets or Dorico's rule)
python3 -m unittest discover -s tests                   # unit tests
python3 tools/compare_midi.py A.mid B.mid; python3 tools/swell_context.py SCORE PLAYBACK --list
python3 tools/dorico_maps.py "/mnt/c/Users/kspie/AppData/Roaming/Steinberg/Dorico 5/EndpointConfigs"
python3 -m doricohp.musx --hp FILE.musx                 # HP settings saved in a Finale score
```
- Listening copies are made by running Apply on the user's original project (path above) and
  copying the result to `HPCaptures\dorico\apply-vN\` with a README.txt of what changed.
- Finale input (`.musx`/`.mus`) goes through finale2dorico: `model.from_f2d` runs
  `python3 -m f2d ir` from `../finale2dorico` (needs its C++ extractor built for `.mus`;
  see `../finale2dorico/docs/STATUS.md`). Read-only use; keep its IR JSON compatible.
- Large Dorico files: avoid `difflib` on decoded XML (minutes); compare subtrees instead.
- Ghidra: `~/tools/ghidra_12.2_PUBLIC` + `~/tools/jdk-25.0.5+8`, project
  `~/tools/ghidra-projects/Finale`, decompiled HP region in `~/tools/ghidra-hp/functions`
  (1,415 functions) and `~/tools/ghidra-out` (call graph), scripts in `tools/ghidra/`,
  runners `~/tools/run-ghidra*.sh` (detached, survive session end).

### Where things are

| What | Where |
|---|---|
| Code | `doricohp/` (see README layout), data `doricohp/data/{defaults.toml,libraries.toml,hp-presets.tsv}` |
| Research | this folder; index below; per-VI notes in `vi/` (`swam.md` first) |
| Finale HP captures (MIDI) | `captures/finale-hp/<NN-style>/` (+ `analysis/`), user scores in `scores-none`, `scores-own-style`; old run without dynamic values `captures/finale-hp-v1-no-dynamic-values/`; engine renders `captures/engine-v1/` |
| Test pieces | `test-pieces/*.musicxml` + `.expected.json` (generator `tools/make_test_pieces.py`) |
| Windows capture area | `C:\Users\kspie\Documents\HPCaptures\` = `/mnt/c/Users/kspie/Documents/HPCaptures/`: `musicxml*`, `finale\` (test .musx, `scores\`, `vv\`, `rod\`, `ww\`, `willow\`, `fanfare\`, `more\`, `last\`, `midi\`), `midi\<style>\` (Finale exports), `dorico\apply-v1\`, `apply-v2\`, `images\hp-flute\`, README.txt (capture procedure parts A–D) |
| FinaleScripts | `tools/finalescript/*.xml`, installed in `C:\Users\kspie\AppData\Roaming\MakeMusic\Finale 26\FinaleScript\HP Capture\`. Before a batch: export one MIDI manually as **Format 1** (Finale resets to "Tempo map" = no notes after a restart) |
| User's Dorico projects used | `C:\Users\kspie\Documents\Dorico Projects\Harry Potter Cues Plus 5 + LASS3.dorico` (main test; SWAM/LASS3/Pianoteq), `...\HP - birds.dorico` (≈ score version), `C:\Users\kspie\OneDrive\Desktop\BLACK LABEL\BLACK LABEL - short.dorico`, `G:\Scores\TREX-new-pb.dorico`. Never write to these; copy first |
| User's Finale sources | `G:\Scores\VV\*.mus` (score/BR/STR playback copies), HPCaptures `finale\*` |
| Dorico test files A–H | `../../engine/tests/dorico-files/` (moved there from `dorigit/prototype/experiments/dorico-tests/` by Project S S1, 2026-10-29) |
| User's expression maps | `C:\Users\kspie\AppData\Roaming\Steinberg\Dorico 5\EndpointConfigs\` (78 configs); summary `dorico-user-expression-maps.md` |
| Scratch | the session scratchpad under `/tmp/claude-1000/...` is **not** persistent; everything needed is regenerable from the paths above |

### Research index

| File | Contents |
|---|---|
| `hp-engine.md` | HP style record layout, presets, pipeline, and every finding from the captures (dynamics are piece-relative; espressivo swell rule; harp roll/gliss; swing; Funk/autoDetectSolo…) |
| `hp-measurements.md` | Generated cross-style tables (Finale); `engine-v1-measurements.md` same for the engine |
| `dorico-integration.md` | What Apply may touch vs what Dorico owns; Dorico playback options; delay compensation; passage markings policy; open Dorico tests I–N |
| `score-vs-playback.md` (+ `score-vs-playback/`) | What the user changed for playback (balance, range, swells, accents, articulation swaps, timing), printed flute score vs Dorico versions, rules derived |
| `dorico-user-expression-maps.md` | The user's maps: dynamics controller, sampled techniques, overrides |
| `hp-presets.tsv`, `finale-extracted/` | Raw extracted Finale data |

### Hard-won facts (don't rediscover these)

- **Dynamics lane** = `AutomationEventDefinition` with `controllerDefinition` `kDynamic`, absolute
  Dorico dynamic level, overrides Dorico's dynamics + humanise + beat stress + accent boosts
  inside the drawn span (test I). Levels (test I2): pppp −4 … p −1, mp −0.5, mf +0.5, f +1 …
  ffff +4; accent/marcato add the Playback Options deltas; CC and velocity follow one curve
  scaled into the map's ranges: `doricokit.dynlevels`. Dorico reads open hairpins literally (+level, stays). A pt.staccato playing
  technique shortens unmarked notes only until the first slur.
- **SWAM CC14 = Main Volume** (woodwinds 2.8 and Strings 3); vibrato rate = CC19 (on the user's
  violins also bow force). Plug-in states (with MIDI mappings) are readable XML inside the
  project: `supplementary_data/vstaudioengine/enginedata`. Details: `vi/swam.md`.

- **Played offsets freeze the length**: once a note has `kEventPlayStart/EndOffset`, Dorico
  no longer applies its length percentages (staccato etc.). Apply therefore always writes
  an explicit end = Dorico's own length for that note (`apply.played_length`, honouring
  map overrides) + a ≥ 25 ms gap before the next unslurred note (else SWAM/LASS slur).
- **Routing**: `/kScore/playModeData/pluginRackContents` lists plug-in slots and the map per
  channel; `instrumentPlaybackData` lists each instrument's endpoints; **endpoint id =
  slot << 10 | port << 4 | channel**. Expression maps are embedded in
  `/kScore/library/expressionMapDefinitions` (fallback `scorelibrary.dtn`); playback options
  in `/kScore/scoreOptions/playbackOptions`; playing-technique appearances (text + `pt.*`
  playback id) in `/kScore/library/playingTechniqueAppearanceCollectionDefinition`.
- **Players can share a name** (LASS "Viola" section + SWAM "Viola" solo): key everything by
  Dorico instrument id, never by name.
- **Dynamics**: `DynamicGroupEventDefinition` on stave streams → flow `elementTables`
  (`DynamicGroupElementDefinition`); intensity `{int: 0=forte|1=piano}, {}, {bool: mezzo},
  {int: count}`; hairpins are `GradualChangeDynamicDefinition` sub-elements.
- **HP's dynamic levels are piece-relative** (mf ≈ 90 CC11 alone, 65 in a ppp–fff piece);
  the engine uses absolute levels on purpose (Dorico's maps own the range).
- Dorico ships no "stacc." or "leggiero" playing technique; see the passage policy in
  `dorico-integration.md`.
- Finale MIDI export needs Format 1; HP dynamics need playback values on expressions
  (`<sound dynamics>` in MusicXML imports).
- `.mus` (Finale ≤2012) is a different binary format: read via finale2dorico's extractor,
  or convert in Finale with `tools/finalescript/convert-*-to-musx.xml`.

## Measured behaviour

All 16 styles × 59 test pieces captured with dynamic values (2026-10-26), plus the
user's 5 scores with HP off and on: `captures/finale-hp/`. Tables:
`hp-measurements.md`; interpretation: `hp-engine.md` → "Findings from the captures".

## What HP is made of (Finale 26, `C:\Program Files\MakeMusic\Finale\26`)

| Part | Where | Status |
|---|---|---|
| Engine (score reading, interpretation, rules) | Compiled C++ in `Finale.exe`, namespace `humanplayback` | Decompiled with Ghidra (`~/tools/ghidra-hp`); pipeline mapped in `hp-engine.md`, formulas not yet read |
| Style presets (Standard, Baroque, Romantic, Jazz…) | Tables inside `Finale.exe` | Extracted: `hp-presets.tsv` (all 17 styles) |
| Preferences + technique table (179 techniques) | XML inside `FinRes.dll` | Extracted: `finale-extracted/hp-default-preferences.xml` |
| Text-expression dictionary (rit., calando, pizz., con sord…) | XML inside `FinRes.dll` | Extracted: `finale-extracted/hp-strings-and-expression-dictionary.xml` |
| "Apply Human Playback" | Built into Finale.exe (`ApplyHPDlg`), not a separate plug-in file | Can be batched via FinaleScript |

HP was written by Robert Piéchaud (per the Finale manual).

### Engine structure (from C++ class names in Finale.exe)

`HumanPlaybackWrapper` / `HumanPlaybackInterface` → `DataFetcher` (+ `_Artic`, `_Shape`,
`_Fonts`) reads the score into `ScoreCanvas`, `MeasureSlotStructure`, `InfoNote`,
`InfoDynamic`, `InfoExpression`, `InfoMIDIData`. `TechniqueDefinition` / `TechniqueContext`
apply the technique table. Progress messages give the pipeline order:

1. clean MIDI → 2. get notes → 3. get expressions → 4. get smart shapes → 5. get items
6. **interpret score** → 7. ornaments → 8. techniques → 9. hairpins → 10. glissandi/bends
11. save note performance data (velocity, start/stop) → 12. save continuous data (CCs)

### Style = values for these parameters

Interpret switches: `interpretSlurs`, `interpretHairpins`, `interpretGlissandiAndBends`,
`interpretAccRallTexts`, `interpretFermatas`, `interpretFinalBars`, `interpretOrnaments`,
`pedalMarkings`

Advanced switches: `emphasizeShortSyncops`, `automaticPedaling`, `automaticPanning`,
`stringHarmonics`, `adjustDottedEighth` (`adjustLonger`), `baroqueStyle`,
`automaticEspressivo`, `detectAccompaniment`, `adjustChordBalance`, `softenBasses`,
`autoDetectSolo`, `vienneseWaltzFeel`, `interpretCadences`, `strumChords`, `exactDrumRolls`

Amounts: `rhythmicFeel` %, `rhythmicAccents` %, `rubato` %, `swing`, `mood` % (randomness),
`reverb`

Global preferences: dynamics approach (`velocityAlone`, `expressionWithVelocity`,
`volumeWithVelocity`, `modulationAlone`, `expressionAlone`, `continuousDynamicOnly`),
hairpin curve (`linear`/`quadratic`/`cubic`), `hairpinPairEmphasis` (50),
`autoExpressionEmphasis` (40), `volumeBaseValue` (75), `midiAnticipation` (15),
`trillCentiSpeed` (1300), `tremoloCentiSpeed` (1200), `fermataMinCentiDura` (160),
`ritardandoBeforeFermata`, `humanizeRollsAndTrills`, `garritanSoloStringsAutoVibrato`.

Manual descriptions of each option:
[Custom Style](https://web.pdx.edu/~jnewton/assignments/043ft_finale_tutorials/finale_tutorials/Finale/Human_Playback_Custom_Style.htm),
[Garritan Specials](https://usermanuals.finalemusic.com/Finale2012Mac/Content/Finale/Human_Playback_Preferences_-_Garritan_Specials.htm),
[Human Playback overview](https://usermanuals.finalemusic.com/Finale2010Win/Content/Finale/Human_Playback.htm).

## What Dorico stores (Dorico 5.1, confirmed with test files)

- Dorico opens files we write (tests A–D, 2026-10-25), including musical edits.
- **Per-note velocity**: property `kNoteVelocity` = `int: 127` on the NoteEventDefinition
  (test E: a Play-mode velocity edit on Horn 1's first note; nothing else changed).
- **Per-note played timing** (Play mode, "Played durations" edits): `kEventPlayStartOffset` /
  `kEventPlayEndOffset` (test G: about half a 1/16 grid step gave `int: -64` / `int: 72`, so
  confirmed by test H: **480 ticks per crotchet**; Dorico clamps notes at the flow start). The `kEventRecordedPlay*`
  variants hold MIDI-recorded timing; Dorico ignored them when we wrote them (test F).
- Editing in "Notated durations" view changes the written note itself (position/duration).
- **Controller curves**: `AutomationEventDefinition` events (`data/controllerDefinition` =
  `kMIDICC:<n>`, `data/value` float 0–127, `data/type` `kLinear` or `kConstant`) in a
  `kAutomationStream`, one per instrument, registered in the flow's `automationStreamTable`
  as `kIRV:<instrumentID>:-1`. A drawn line's points share a `kEventGroupId` and the
  last point is usually `kConstant`.
- Each stream has one blockInstance → one block (blockID == streamID in practice).
- **New IDs** come from `/kScore/idGenerators/{event,eventStream,block,blockInstance,eventGroup}`,
  which hold the next free value.
- Global: `timingHumanisePercent`, `dynamicHumanisePercent`, beat stresses,
  staccato length %, dynamic curve.
- Test F (`F-playback-write.dorico`) writes velocities, a new automation lane, a curve on an
  existing lane and play offsets, using `doricohp/project.py`.

## Plan (original) and what was decided

1. Capture Finale HP with one-feature test pieces → done.
2. Ghidra on Finale.exe → presets and pipeline done; formulas only as needed.
3. Rules engine from 1+2, plus expressive-performance rules (KTH-style) and the user's own
   habits (`score-vs-playback.md`) → v1 done (`doricohp/engine.py`).
4. Layered profiles defaults → style → library → instrument → project → done
   (`doricohp/profiles.py`, `data/*.toml`, `<project>.hp.toml`).
5. Delivery: **Apply** into a copy of the project (decided); a real-time plug-in later
   (Project S lists it as the last phase). Constant VI look-ahead (LASS 3 ≈ 440 ms) is
   handled by host delay compensation via `../../latency-reporter` (decided).

## Design constraints (from the user)

How each HP feature divides between Dorico and Apply: `dorico-integration.md`.
The user's expression maps: `dorico-user-expression-maps.md` (`tools/dorico_maps.py`).
What the user changed in playback copies of scores: `score-vs-playback.md`.

- **Delivery is an "Apply" step** that writes into a copy of the .dorico file (velocities,
  played offsets, dynamics-lane / CC automation). A real-time plug-in comes later.
- **Don't fight Dorico's own playback.** Expression maps, percussion maps and playback
  options (including Dorico's own jazz/swing playback settings) stay in charge. In
  particular, never add swing timing when Dorico's swing playback is on: test what both
  Finale and Dorico do with a swing marking before deciding (Finale HP plays straight
  quavers straight in every style, even Jazz).
- **Trills, tremolos, rolls: sample or written out, per VI.** Finale HP writes them out
  as notes only because no sample/technique was mapped. The profile for each library/
  instrument decides: "sample" (leave it to Dorico's expression map, which triggers the
  trill/tremolo patch) or "written out" (generate the notes, with HP-like timing).
- **Score vs playback versions.** The user's habit was a balanced "score" version (GPO /
  General MIDI) plus separate "playback" copies with dynamics and accents re-voiced for
  each library (e.g. VV_Full BR = SWAM brass, VV_Full STR = LASS 2.5 strings). The
  difference between the two is training data for the library profiles: what a library
  needs that the notation alone doesn't say.
  Sources: `G:\Scores\VV\*.mus` (Finale 2012 binary format; converted to .musx via
  `tools/finalescript/convert-vv-to-musx.xml` into `HPCaptures\finale\vv`).
