# Round 12: harmonics, two-note tremolos, lines with text (Dorico encodings unknown)

**Folder from Windows:**
`\\wsl.localhost\Ubuntu-26.04\home\ken\dev\dorico-test\finale2dorico\experiments\round12\`

Open `ref-start.dorico` (a violin with 8 bars of crotchets), add the items below, and save it as
**`ref-harmonics-lines.dorico`** in the same folder. None of the 400 Dorico projects on this
machine contains these items, so the converter can't write them yet. In the film scores they are
common: string harmonics (476), measured tremolos (226), lines with text such as "Cue (don't
play):" or "ord. ---> sul pont." (about 1,000 lines). If something is awkward to make, skip it
and say which.

## Harmonics (bars 1-2): select the note, Properties panel > Notes > Harmonics

| Where | What |
|---|---|
| bar 1 beat 1 | natural harmonic (the default harmonic) |
| bar 1 beat 3 | natural harmonic, partial 3 (if Dorico offers partials) |
| bar 2 beat 1 | artificial harmonic (touched 4th) |
| bar 2 beat 3 | artificial harmonic (touched 5th, if offered) |

## Two-note tremolos (bars 3-4): select both notes, Tremolos in the Ornaments panel

| Where | What |
|---|---|
| bar 3 beats 1-2 | two-note tremolo, 3 strokes (Dorico may redraw the crotchets as minims; leave it) |
| bar 3 beats 3-4 | two-note tremolo, 2 strokes |
| bar 4 beats 1-2 | single-note tremolo, 3 strokes on beat 1 only (for comparison; already known) |

## Lines (bars 5-8): Lines panel in Write mode

| Where | What |
|---|---|
| bar 5 beat 1 to beat 4 | plain solid horizontal line, not attached to notes if Dorico allows |
| bar 6 beat 1 to bar 6 end | dashed line ending with a hook pointing down |
| bar 7 beat 1 to bar 7 end | dashed line with text "Cue:" at its start (Properties > Lines > text, or whichever way Dorico offers) |
| bar 8 beat 1 to beat 4 | playing technique change: "ord." on beat 1 changing gradually to "sul pont." on beat 4, with Dorico's transition line, and the text "move bow towards..." on the line if possible |

## Metric modulation (bar 5 beat 1)

Shift+T, type `h=q` (or use the Tempo panel's metric modulation), Enter. E.T. has "(𝅗𝅥 = ♩)" at
three meter changes (4/2 -> 3/4); no Dorico project on this machine has one.

## Bonus (optional): boxed text

Bar 2 beat 2: Shift+X text "Bright", then turn on its border (Properties > Text > Border).
Finale's jazz library draws such words in a box ("straight", "cup", "harmon w/stem").

Save as **`ref-harmonics-lines.dorico`** in this folder. Nothing needs exporting.

## Results (2026-10-31)

User's files `ref-harmonics-lines.dorico` and `ref-tremolos.dorico` (two-note tremolos, redone).
Everything came through except words on the technique-change line (Dorico can't).

| Item | Dorico encoding |
|---|---|
| natural harmonic | note property `kNoteHarmonicType` = `kNatural` |
| artificial harmonic | `kNoteHarmonicType` = `kArtificial` + `kNoteHarmonic` = partial (int). The note is the **stopped** note; Dorico draws the diamond. Partial 3 = touched 5th, 4 = touched 4th, 5 = touched major 3rd (2 = octave). Bar 1 beat 3 came out as artificial partial 3 (also `kNoteArtificialHarmonicStyle` kNormal); the user was unsure there, and it isn't needed: Finale's natural harmonics are a plain circle |
| two-note tremolo | (`ref-tremolos.dorico`) on the two notes, each at its real length: first `kBeamStart` "list: {int: strokes}, {int: 0}", second `kBeamEnd` `null: `; both `kNoteSplitDurations` = their own length ("list: {string: \"1\"}" for crotchets). The first file had single-note tremolos instead |
| single-note tremolo | `kNoteSingleStemTremolo` "list: {int: 3}, {bool: false}" (already known) |
| line, note-attached | bar 5: `HorizontalLineEventDefinition` in the **voice** stream, kNote ends + note event IDs (as in the Liszt sample) |
| line, not note-attached | bars 6-7: in the **stave** stream; `startAttachmentType`/`endAttachmentType` = `kRhythmicPosition` (bar 7) or `kBarline` (bar 6), note IDs -1. Position/duration in crotchets |
| line styles | `linestyle.dashedLineLong`, `linestyle.dashedLineShortInwardHook` (end hook, pointing towards the staff), `linestyle.solidLine`. Dorico copies each used style (and its body/cap entities) into the project library |
| text on a line | `kHorizontalLineText` string "Cue" + `kHorizontalLineTextPlacement` "kStart" (the user set Start, so the default is presumably centred) |
| metric modulation | global `ImmediateTempoChangeEventDefinition`, `type` kEquation, flags 1, `tempoEquation/left` + `right` = note value codes as for metronome marks (minim 9, crotchet 8; second int = dots) |
| boxed text | `kTextBorder` (value `null: `) + `kTextBorderStyle` "kRectangle" (the user's was set for the full score only; we write it for all layouts) |
| ord. -> sul pont. | two `PlayingTechniqueEventDefinition`s: `pta.ordinarioText` with **duration** up to the second, `pta.sulPontText` duration 0; both with `kEventGroupId` (same int); project `idGenerators/eventGroup` counts groups. "move bow towards..." could not be put on the line |

### Implemented (2026-10-31)

- Harmonics: Finale's harmonic circle -> natural; a chord of a stopped note with a diamond a
  4th/5th/3rd/octave above -> one artificial harmonic (Avatar: 24).
- Lines (Finale line shapes and custom lines, 1,823 live in the film scores): words at the start
  ("Cue (don't play):"), a word in the middle ("possibile", "push": no placement property, to
  verify), hooks, end arrows, wavy lines. "ord. ... sul pont." lines become a gradual technique
  change, their middle words a staff text. Dashed lines after a typed "8va" are part of that
  ottava (E.T.: 28); a solid line after "Ped." text becomes a pedal line (E.T. vibraphone).
  Plain lines with no words or hooks are drawings (Avatar: 7 short strokes per cue) and are
  left out, with a count in the report.
- Metric modulation (E.T. bar 196 "(h = q)"), boxed text (Finale enclosures and box-coded copyist
  text; Asteroid Field percussion changes, matching the published PDF), and "ord." / "sul pont." /
  "sul tasto" as Dorico playing techniques.

- Two-note tremolos: Finale's hidden tremolo tuplets (two short notes; their beams = strokes,
  less the notes' own beams for quaver-length tremolos) -> Dorico's pair; the generated pair is
  identical to the user's. Trex 4, E.T. 38, Asteroid Field 199; none left unconverted.

### Verified in Dorico (user, 2026-10-31): `check/gen-round12.dorico`

Generated by `make_check.py`. Confirmed: a centred line word needs no placement property
("possibile" sits centred), and `kHorizontalLineLineStartCapID` =
"lineannotation.inwardHookAxisAligned" puts a hook at the start only.
