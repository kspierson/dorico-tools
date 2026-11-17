# finale2dorico: format research notes

*2026-10-26. ✅ = confirmed (by Dorico or by an oracle), 🟡 = observed in Dorico-saved files
but not yet tested by writing it, ❓ = guess.*

General Dorico container/DTN facts are in dorigit's [RESEARCH.md](../../dorigit/docs/RESEARCH.md).

## 1. State of the art (Oct 2026)

- Dorico cannot open Finale files; MakeMusic and Steinberg both point to MusicXML.
- **openmusx** (Robert G. Patterson, MIT): `musxdom` (C++ object model for EnigmaXML),
  `denigma` (CLI: musx/mus → EnigmaXML, MusicXML, MNX, MuseScore, SVG), `finale-mus-reader`
  (legacy `.mus`, Finale 1.x-2012, builds musxdom documents; "ossias are the only score
  content not yet read"), `smufl-mapping` (legacy Finale music fonts → SMuFL glyphs).
  These are the best references for what Finale's data means, and the base of the full
  reader (`extract/`, built 2026-10-26; sources fetched by CMake at pinned revisions, not
  vendored).

## 2. Finale side (EnigmaXML)

`.musx` = zip; `score.dat` = EnigmaXML, gzip-compressed then XOR-scrambled (dorico-hp
cracked it). Sections: `options`, `others`, `details`, `entries`, `texts`. Records are keyed
by `cmper` (and `inci`, `cmper1/cmper2`, `entnum`); `part="N"` records are linked-part
overrides (we read score records only).

| Thing | Where | Notes |
|---|---|---|
| Time unit | | EDU, 1024 per crotchet ✅ |
| Measures | `others/measSpec cmper=N` | `beats` × `divbeat` (EDUs per beat) = actual length; `dispBeats`/`dispDivbeat` = shown time sig **only if `useDisplayTimesig` is set** (otherwise stale values Finale ignores) ✅. Dotted beat (1536) → compound ✅. Pick-up: measure 1 actual ≠ displayed ✅; old files instead use a "legacy pick-up spacer" (full bar, music starts late; musxdom `calcMinLegacyPickupSpacer`) ✅ |
| Key | `measSpec/keySig/key` | 16 bits: top bit 0 = linear; bits 8-14 mode (0 major, 1 minor, ≥2 custom); low byte signed fifths. `keyless` flag ✅ |
| Score staff order | `others/instUsed cmper=0`, by `inci` | ✅ |
| Staff | `others/staffSpec cmper=staff` | `instUuid`, `fullName` (→ textBlock), `defaultClef`, `transposition` ✅ |
| Transposition | `staffSpec/transposition` | `keysig{interval, adjust}` = diatonic steps + change in sharps (horn: 4, +1 → 7 semitones) ✅; `chromatic{diatonic, alteration}` (alteration 0 = major/perfect) ✅. Chromatic = part has no transposed key signature ❓ (mapped to Dorico `.nokeysig` instruments) |
| Grand staff | `others/multiStaffInstGroup` (staffNum1..3) ✅; name on `details/staffGroup` (`fullID`) ✅ |
| Notes per staff/measure | `details/gfhold cmper1=staff cmper2=meas` → `frame1..4` (layers) → `others/frameSpec` → `startEntry`..`endEntry` (linked list via `next`) ✅ |
| Entry | `entries/entry` | `dura` (notated EDUs incl. dots), `isNote`, `v2`, `graceNote`, `tupletStart`, `ignore` (hidden), `freezeStem`/`upStem` ✅ |
| Pitch | `entry/note` `harmLev`, `harmAlt` | concert; `harmLev` is diatonic steps from the **key's tonic in the middle-C octave**, `harmAlt` relative to the key signature ✅ (musxdom `KeySignature::calcPitch`) |
| Ties | `note/tieStart` ✅ |
| Tuplets | `details/tupletDef entnum` | `symbolicNum`×`symbolicDur` in the time of `refNum`×`refDur` ✅ |
| Clefs | `gfhold/clefID` or `clefListID` → `others/clefList` (`clefIndex`, `xEduPos`); clef table in `options/clefOptions/clefDef` (`clefChar` glyph, `adjust` = middle-C position) ✅. A mid-bar clef applies from the first entry at or after `xEduPos` (often stored slightly early) ✅. Percussion: a staff with percussion notation style always shows a percussion clef (musxdom); a percussion glyph (Maestro 139/214) on a normal staff still draws one ✅ |
| Articulations | `details/articAssign entnum` → `others/articDef` (`charMain` glyph) ✅ |
| Expressions | `others/measExprAssign cmper=meas` (`staffAssign` (−1/−2 = top/bottom staff), position in xml tag `horzEduOff`, `textExprID`) → `textExprDef` (`textIDKey` → `textBlock` → `texts/expression`), `categoryID` → `markingsCategory` (dynamics, tempoMarks, …) ✅ |
| Smart shapes | `others/smartShape` (`shapeType` slurAuto/cresc/decresc/trill/glissando/smartLine…, `startTermSeg/endPt` {inst, meas, entryNum or edu}) ✅ |
| Instrument UUIDs | musxdom `InstrumentUuids.h` (799); `a925648a…` = "Unknown" (used by older files) ✅ |

**Reader oracles:**
- All 59 HPCaptures `.musx` files match the MusicXML they were made from, note for note
  (pitch, position, sounding duration, ties), with **both** readers. `python3 tests/oracle.py [--reader musxdom] …`.
- `tests/compare_readers.py`: bootstrap vs full reader on every IR field. On the 59 test
  files and 5 real scores they now agree except where the full reader is right (below).
- `tests/compare_mus.py`: 516 legacy `.mus` test documents (finale-mus-reader's fixtures,
  Finale 1.0-2012) vs Finale 27's own conversion of each, both through the full reader:
  0 errors; 4 differ, all explained (Finale 27 infers instrument types from staff names; one
  staff-list expression, see 2.4).

### 2.3 Bugs the cross-check found in the bootstrap reader (all fixed)

1. Expression positions read from a non-existent tag (`eduPosition`; the xml tag is
   `horzEduOff`), so every dynamic sat on the barline.
2. `dispBeats`/`dispDivbeat` used without checking `useDisplayTimesig`: wrong time
   signatures and false pick-ups in 3 of the 5 real scores (VV_Full shows 6/8, not 4/4).
3. Tremolos (Finale: hidden 2-note tuplets) became nonsense tuplets ("1 in the time of 4").
   The full reader detects them (musxdom `calcIsTremolo`) and reports them; conversion to
   Dorico tremolos is still to do.
4. Grace-note slashes taken from the raw flag. Finale slashes flagged graces per document
   option and never draws a slash on beamed graces; musxdom's `calcGraceNoteSlash` models that.

### 2.4 Legacy `.mus` specifics

- Finale 1.x-2.x files record no instrument type (UUID "Unknown"); names are often empty.
  Unnamed untyped staves become "Staff N" / "Grand Staff" and Dorico generic staves (by clef).
- **Accidentals:** legacy files store "show accidental" without Finale 2014's freeze flag.
  Finale 27's upgrade freezes it only where the accidental would not be drawn anyway
  (a courtesy accidental); 25 needed accidentals and 2 cancelling naturals stayed automatic,
  2 courtesy naturals became frozen. facts.py applies the same rule (bar-by-bar accidental
  tracking per staff line).
- Staff-list expressions (F100-instlist): finale-mus-reader assigns the expression to every
  staff in the list's *parts* membership; Finale 27 keeps only the *score* membership.
  Possibly worth reporting upstream; not worked around.

## 3. Dorico side (writing)

Reference files: your projects (Dorico 3.5-5.1.60), "ET The Flying Theme" (5.1.60), and
the Steinberg tutorial projects in `<Dorico>/guidedtutorials/` (4.0.5, factory defaults).

### Project skeleton 🟡
`kScore`: `fileVersion` (**1.1299 in 5.1.60** ✅, 1.1096 in 4.0.5; we first wrote 1.982, which
Dorico reported as "created in Dorico 3"), `idGenerators` (next free id per kind;
blockInstance ids start at 1000), `info`, `scoreOptions`, `library`, `scorePlayers`,
`scorePlayerGroups`, `flows`, `textFlows`, `layouts`, `playModeData`, `printingModeData`.
The `library` in score.xml duplicates `scorelibrary.dtn` and holds only what the project
uses (instruments, names, techniques, expression maps…); the install's `scorelibrary.xml`
is the factory library.

### Players and instruments 🟡
`scorePlayer` {playerID, soloPlayer, baseName, displayName, …, instruments[]}. Each
`instrument` is the factory `InstrumentEntityDefinition` flattened: entityID, instrumentID,
numStaves, ranges, `nameData`, `formattedNameData` (paragraphs), `transposition`
(`{int: interval number}, {string: quality}` e.g. B♭ trumpet `{int: 2}, kIntervalMajorOrPerfect`),
`staveDefinition`, clefs. Numbered players use `suffix`.

### Flow 🟡
Streams: one `kGlobalTimebaseStream` (time sigs, keys, tempo), per player a `kPlayerStream`,
per stave a `kInstrumentStaveStream` (clefs, dynamics), per voice a `kVoiceStream`
(notes, tuplets, slurs). Each stream → one blockInstance at position 0 → one block.
`flowPlayers` maps players to streams (`staveStreamInfos` with `staveID`, `voiceStreamInfos`
with `defaultLogicalStaveID`, `voiceDirection`).
Events sharing a position are saved in the order tuplet, note, slur.

### Events 🟡
- Note: `NoteEventDefinition` position, duration (sounding), `pitch` (concert MIDI),
  property `kNoteSpelling` = concert letter (with a context block).
- Tied notes = one note. Forced notation: `kNoteSplitDurations` = `list: {string: "1/2"}, …`
  (all segments; a single item = force that one value).
- Grace: `GraceNoteEventDefinition` at the main note's position with negative
  `secondaryPosition`, `notatedDuration`, `slashed`.
- Rest: implicit; explicit `RestEventDefinition` with `kRestForcePositionAndDuration`.
- Tuplet: `TupletEventDefinition` (position, span) with
  `tupletDefinition = {int: n}, {int: d}, {list: {int: unit}, {int: dots}}, {bool: true}`;
  unit code 8 = crotchet, 7 = quaver, 6 = semiquaver, 9 = minim.
- Time signature: `BarDivisionEventDefinition` → `BarDivisionElementDefinition`
  (numerator, denominator, beat grouping). Pick-up encoding unknown ❓ (`irregularBarLength`
  guessed; Round 1 file 10 and the requested reference file will tell).
- Key: `TonalityDivisionEventDefinition` → element with root (note name + accidental ID),
  `kKeySigMajor/Minor`, and the explicit list of key-signature accidentals.
- Clef: `ClefEventDefinition` on the stave stream, `entityIDs/idForTransposingLayouts` = `clef.treble` etc.
- Dynamics: `DynamicGroupEventDefinition` (duration 0) on the stave stream → element with
  sub-elements: `ImmediateChangeDynamicDefinition` intensity `{int: 0=f|1=p}, {}, {bool: mezzo}, {int: count}`;
  `GradualChangeDynamicDefinition` (hairpin, its own `duration`); `ForceDynamicDefinition`
  (types: only `kForceDynamicFz/Mfz/Rfz/Sfz` exist in Dorico 5's binary);
  `CombinedDynamicDefinition` (fp-style; encoding of intensities not yet understood).
- Slur: `SlurEventDefinition` (span) → `SlurElementDefinition`.
- Articulations: properties `kArticulationDuration` (kStaccato, kStaccatissimo, kTenuto,
  kStaccatoTenuto), `kArticulationForce` (kAccent, kMarcato), `kArticulationStress`.
- Tempo: `ImmediateTempoChangeEventDefinition` with `tempoValue` = µs per beat (413793 ≈ ♩=145)
  and `beatUnits` as a duration code.

### Vocabulary source
Dorico5.exe contains all its `k…` enum/property names (5,097 strings); extracting them gave
the force-dynamic list and the articulation property names. Used for reference only.

### Encodings mined from the user's projects (2026-10-28)
47 projects (user's + Steinberg tutorials) inventoried. Stream = where the event lives.

| Event | Stream | Key fields |
|---|---|---|
| `ImmediateTempoChangeEventDefinition` | global | `data/type` kAbsolute, `presetID` (tempopreset.*), `text`, `flags`, `absoluteTempo/tempoValue` (µs per beat, e.g. 555555 = 108), `beatUnits` (duration code) |
| `GradualTempoChangeEventDefinition` | global | duration = span; `data/finalTempoPercent`, `presetID` (tempopreset.rall), `text`, `abbreviatedText` |
| `TextEventDefinition` | voice (855), stave (64), global (2) | `aboveOrBelow`, `isSystemText`, `content/paragraphs/paragraph` (`paragraphStyleID` paragraph.defaulttext, `fragments/fragment/content`) |
| `RehearsalMarkEventDefinition` | global | empty `data` (Dorico numbers them) |
| `PauseEventDefinition` (fermata) | global | `pauseData/pauseType` kFermata, `fermataDuration` kNormal |
| `RepeatMarkerEventDefinition` | global | `sectionType` kFine, or `jumpTypeAndQualification` (kDaCapo, kEndOfFlow) |
| `OttavaLineEventDefinition` | stave | duration; `entityID` line.ottava.up.8 |
| `PedalLineEventDefinition` | stave | duration; `pedalLineType` kSustainPedal |
| `HarpPedalEventDefinition` | stave | `pedalSettings/{c..b}Pedal` kTop/kMiddle/kBottom |
| `ArpeggioEventDefinition` | voice | `startVoiceID`, `endVoiceID`, `arpeggioType` kUpArpeggio |
| `OrnamentEventDefinition` | voice | `entityID` ornament.turn |
| `InstrumentChangeEventDefinition` | player | label properties (`kInstrumentChangeLabelCustomText` ...) |
| Cross-staff note | voice | `NoteEventDefinition/logicalStaveIDOverride` = target stave ID (10 cases) |
| Doubling players | `scorePlayers` | 158 players with 2-3 instruments ("Piccolo & Flute 1") |

### Page layout: page size, staff size, condensing (2026-10-28) ✅ (pending Dorico check)
Before this the writer wrote **no `layoutOptions`**, so Dorico used its defaults (Letter/A4,
7 mm staff) and big scores came out squashed in Engrave mode (user's E.T. review).
- **Dorico** (`layouts/array/layout/layoutOptions`, units = points): `defaultSpaceSize` (staff
  space; 4.96 = 1.75 mm = 7 mm staff), `pageSizeAndMarginOptions/pageWidth|pageHeight` (Letter
  612x792, A4 594x841, 11x17 792x1224, A3 841x1189), `hideEmptyStavesPolicy` (kNever,
  kAfterFirstSystem, kAllSystems), `condensingLayoutOptions/enableCondensing`. The user's
  orchestral projects: HP BRASS TEST 11x17, space 2.62 (3.7 mm staff), condensing on, kAllSystems;
  Rite of Spring 2-3.12; Full Orchestra Template A3, 2.8.
- **Finale** (musxdom): `options::PageFormatOptions::pageFormatScore/Parts` (page size in Evpu,
  288/inch = 4/pt; `calcCombinedSystemScaling`), `others::Page` (per page size/percent),
  `others::StaffSystem` (`calcEffectiveScaling`; staff space = 24 Evpu x scaling = 6 x scaling pt),
  `others::StaffUsed` per system (staves printed in that system, `distFromTop`). The extractor
  emits these as `layout` (page_format, part_page_format, pages, systems with staves) and each
  staff's `hide_mode`.
- **Converter** (f2d/dorico/layout.py): starts from the user's new-project layout options
  (f2d/data/new_project_layout_options.xml, from ref-pickup.dorico), sets page size and staff size
  from Finale; if a full-score system would not fit at that size (4-space staves + 5-space gaps),
  the staff shrinks to fit, the page grows to 11x17 first if needed (floor 2 pt = 2.8 mm staff);
  empty-staff hiding when Finale's systems leave staves out; condensing on when shared staves
  were split into players. Parts get Finale's part page size and staff size.
- E.T.: 11x17, Finale staff 4.2 mm at 45 staves per system, but its own pages overflow (one
  6-bar system is ~24 in tall at Finale's spacing); converted to 3.8 mm.

### Repeats, endings, segno/coda, chord symbols, lyrics: implemented (2026-10-29)
- **Finale (extractor)**: per measure `barline`, `left_barline`, `forward_repeat`,
  `backward_repeat`; `endings` (RepeatEndingStart: measure, length, text, passes, open);
  `text_repeats` (TextRepeatAssign + TextRepeatDef font + TextRepeatText, as glyph chunks);
  `chords` (details::ChordAssign: root/bass as scale degree of the key + alteration, suffix
  elements with number/prefix/glyph); per entry `lyrics` (LyricAssignVerse/Chorus/Section ->
  syllable text, hyphen before/after, word extension).
- **Dorico (writer)**: barline changes = BarDivision element with the current time signature
  hidden + `barlineChangeIfAny/type` (kDouble, kFinal, kStartRepeat, kEndRepeat,
  kEndAndStartRepeat, kDashed, kTick, kThick; merged into a time-signature change at the same
  barline); consecutive endings = one `RepeatEndingLineEventDefinition` with one segment each;
  `RepeatMarkerEventDefinition` sectionType kSegno/kCoda/kFine at the bar start (Fine at the
  last beat), jumps kDaCapo/kDalSegno/kToCoda + kEndOfFlow/kAlFine/kAlCoda at the bar's last
  beat. D.S./To Coda/segno/coda written as plain expressions are recognised too. Checked in
  Dorico (Mozart German Dance, Finale's "Matching repeats" worksheet).
- Chord symbols: complete since Round 11 (experiments/round11/README.md): quality, interval,
  alterations (type + degree + adjustment), slash bass (`alteredBass`), N.C.; sus = kNoThird. Dorico shows chord symbols only for instruments whose
  definition has `showChordSymbols` (piano yes, flute no): the writer sets it in the project
  library for instruments that carry chords in Finale. Checked in Dorico (Avalon lead sheet).
- Lyrics: complete since Round 11: syllableType kWholeWord/kStart/kMiddle/kEnd (kMiddle confirmed in Dorico 2026-10-30),
  extenders as the event duration, verse and chorus lines. Checked in Dorico (Silent Night, 3 verses).

### Condensing groups (user's HP BRASS TEST project) ✅
`layoutOptions/condensingLayoutOptions/userDefinedCondensableGroups` =
"38,36:40,37|39,38:41,39|23,19:25,20:26,21|35,33:36,34:37,35": groups separated by `|`, members
by `:`, each member "playerID,instrumentID". The writer puts the players split from one Finale
staff in one group (`Player.condense_group`), so Dorico condenses them back as Finale showed them.

Once condensing is on, Dorico also condenses neighbouring players of the same instrument by itself
(Avatar 2m2r: Oboe 1/2, Viola 1/2, Cello 1/2 merged although Finale had separate staves).
`groupsToExcludeFromCondensing` stops that: groups separated by `|`, members are **player IDs
only**, comma-separated ("2,3|4,5|28,29"). Checked in Dorico 2026-10-30 (the "player,instrument:"
form of the user groups is not understood there: Dorico rewrote "2,2:3,3" as "2,2,3" and ignored
it). The writer excludes every run of neighbouring same-instrument players that are not in a
user group (`_condensing_exclusions`).

### Dorico remote control: automatic PDF export (2026-10-29) ✅
`research/tools/dorico_remote.ps1` (runs on Windows; WSL can't reach 127.0.0.1:4560). Handshake as
in romanstark/dorico-maestro docs/protocol.md; the user allowed "f2d review" once (token in
%LOCALAPPDATA%\f2d\dorico-session.txt). Lessons:
- Dorico pushes `status` messages between command replies: wait for `message == "response"`.
- Never cancel a pending WebSocket receive (.NET aborts the socket); poll with `getstatus`.
- `File.Open?File=//wsl.localhost/...` (forward slashes) works for files in WSL.
- **Dorico lays out pages only as they are viewed**: right after opening, Print mode has page 1
  only and `Print.ExportCurrentLayoutAsPDF` writes one page (also for the user's own projects;
  Page range was already "All"). Fix: Write mode, page view
  (`Window.SwitchLayoutAspectType?LayoutAspectType=kPageViewAspect`), `View.MoveViewportToEnd`,
  then Print mode and export (Willow: 9 pages).
- The PDF is written next to the project as "01 - Full score - <title>.pdf", a moment after the
  command answers; experiments/make_round10.py waits for it and renames it `<name>.pdf`.
- A modal dialog (e.g. the transposition warning for concert-pitch parts) blocks everything.

### Finale's own sample files (`C:\Program Files\MakeMusic\Finale\26\Music Files`)
Exercises (955), Tutorials (24, incl. "Percussion Tutorial"), Worksheets and Repertoire (1,213;
Repertoire = 602 well laid-out pieces). Repertoire covers chord symbols (Leadsheets, Jazz), lyrics
(Vocal, "-Voice" versions), repeats/endings, figured bass (Handel), guitar TAB (Bach Prelude,
Tarrega), handbells, chant (Agnus Dei, Veni Veni, Lord's Prayer), shape notes (New Britain),
a Schenker graph (Chopin Etude in Eb min, alongside the normal version), large ensembles,
manuscript paper templates. Repertoire + Tutorials are now in the regression run.

### Round 7 encodings (user's reference file, 2026-10-28) ✅
Details in [experiments/round7-results/README.md](../experiments/round7-results/README.md).

| Item | Stream | Encoding |
|---|---|---|
| Chord symbol | global | `ChordSymbolEventDefinition/chordSymbolData/primaryChord`: `definition` (`quality` kMajor..., `interval` kNone/k7, `alterations` []), `root` (`noteName`, `accidentalType`); empty played pitches / diagram data |
| Lyric | voice | `LyricEventDefinition` per note -> `LyricElementDefinition` (`text`, `syllableType` kWholeWord, `lineLocation` kBelow, `lineType` kVerse, `lineNumber`, `richText` paragraph.lyrics) |
| Barline type / repeat barline | global | `BarDivisionElementDefinition/barDivisionData/barlineChangeIfAny/type`: kEndRepeat, kEndAndStartRepeat, kDouble (final barline automatic) |
| 1st/2nd endings | global | `RepeatEndingLineEventDefinition` (duration = all endings); `kRepeatEndingLineNumSegments` int N, `kRepeatEndingLineSegmentDuration` "8" per segment (propertyOffset "2:k:0:0") |
| Segno / Coda | global | `RepeatMarkerEventDefinition/sectionType` kSegno / kCoda at the bar start |
| To Coda, D.S. al Coda | global | `RepeatMarkerEventDefinition/jumpTypeAndQualification` (kToCoda + kEndOfFlow, kDalSegno + kAlCoda), at the bar's **last beat** |
| Tempo range | global | `data/tempoValueRange` (upper value, µs) before `absoluteTempo`; **written since 2026-10-28** |
| Dotted beat unit | global | `tempoValue` counts the stated beat unit (♩. = 60 -> 1000000); matches the writer |
| Staff-only time signature | stave | `BarDivisionEventDefinition` in the stave stream (same element as global), plus a change back; the bar keeps the score's length and Dorico adds a **hidden tuplet** per bar (12:8 quavers, `kTupletTextContent` kNone, `kTupletBracketVisibility` kHidden). **Written since 2026-10-28** (E.T.) |

### Round 9 encodings (extras file + percussion kit, 2026-10-28) ✅
See [experiments/round9-results/README.md](../experiments/round9-results/README.md): force
dynamics at level 2 (ffz, rffz), combined dynamics with m-levels (mf-mp = kDown 0/0), subito
(`commonDef/subito`), niente hairpins (`hasNiente`, messa di voce), breath marks (kComma, kTick,
kUpBow, kSalzedo) and caesuras (global PauseEvents at the end of the note), and the structure of
a Dorico percussion kit (kit instrument + component instruments in one player; notes in each
component's own voice stream at pitch 71). `ref-extras2`: sf = Sfz with
`kDynamicRinforzandoAndSforzandoHaveZ` false; a staff-only pause is the same PauseEvent in the
stave stream; caesura styles kNormal/kThick/kShort/kCurved/kSingleStroke; fermataDuration
kVeryShort/kShort/kNormal/kLong/kVeryLong/kShortHenze/kLongHenze; curlew = pauseType kCurlew.

### Ottavas: Finale stores written pitch ✅
Notes under a Finale 8va/8vb/15ma smart shape are stored at the *written* pitch; playback adds
the octave. Found with Finale's own MusicXML (every 12-semitone mismatch in the Asteroid Field
and Raider's March was under an 8va). The reader raises/lowers notes from the shape's raw start
to its end. With that, the Asteroid Field matches note for note (18,965 notes).

### Doublings
Dorico doubling player (user's Rite of Spring): one `scorePlayer` with several `instruments`;
in the flow, one `flowPlayerInstrument` per instrument, each with its own stave and voice
streams. `InstrumentChangeEventDefinition` (player stream) carries only label properties and a
layout context, no instrument: Dorico derives the changes from which instrument has notes.
Finale (E.T.): no staff styles; staff names "Piccolo\n(Flute 3)", "Oboe 2\n(English Horn)",
"Piano/Celeste" plus text "To Flute", "Picc.", "To Eng. Hn." ... Staves named only by numbers
("1 2", "3") take the name of their bracket group (Trumpets) or, failing that, the instrument
type (E.T. horns). E.T. also contains duplicate staves (28 onward repeat staves 1-7 etc.).

### Harp pedals ✅ (Finale side)
Finale harp pedal diagrams are music-font text (EngraverTextH): seven `harpPedalRaised` /
`harpPedalCentered` / `harpPedalLowered` glyphs plus a `harpPedalDivider`, in harp order
D C B | E F G A (raised = flat, centred = natural, lowered = sharp). Pedal changes are stacked
letter + accidental lines ("F♯ / C♭ / B♭"), applied to the previous setting. Written as Dorico
`HarpPedalEventDefinition` (stave stream; kTop/kMiddle/kBottom = flat/natural/sharp, inferred
from the user's projects' layout: to confirm visually in Round 8).

### Independent time signatures (E.T.)
Some E.T. staves run in 12/8 against 4/4: musxdom gives their entries' real (global) positions
and durations (quavers = triplet quavers), which is what the IR holds. Finale's MusicXML writes
those staves in longer 12/8 bars, so the oracle can't compare them. ✅ Now converted: f2d-extract
emits each staff's `time_changes` (`Measure::createDisplayTimeSignature(staff)` where it
differs from the score), facts.py turns them into `Staff.time_signatures` plus a hidden tuplet
(staff length : score length in the staff's beat unit, e.g. 12:8) in every voice with notes in
the bar, and the writer puts the signatures in the stave stream. E.T.: 9 staves, bars 118-141;
all 522 notes there have notated = 1.5 x real duration.

### G:\Scores (user's Finale archive, 2026-10-28)
160 Finale files (71 `.mus`, 89 `.musx`, ~752k notes): **all read without errors** (largest
38,775 notes / 49 staves, ≤16 s). 71 files have multi-layer staves (241 staves). Unconverted
material by frequency: custom lines 1,903, glissandi 969 (now converted), trills 495 (converted),
ottavas 75, tempo marks 273, rehearsal marks 127, "misc" expressions 17,908, technique text 2,834.
Four John Williams scores have Finale-exported MusicXML: note oracle (per-bar reset, 1/192 grid)
matches except: percussion (MusicXML unpitched; oracle limitation), harp cross-staff notes
(not converted yet), a Celeste staff with an instrument change via staff style (Raider's, from
beat 452), and some E.T. staves (24-beat shift on Oboe 2/English Horn; triplets vs quavers on
staff 12) still to investigate.

### Glyph names, not codepoints
Finale scores use many music fonts (Trex's trill symbol is EngraverFontExtras 60 =
`ornamentTrillFlatAbove`, not Maestro). f2d-extract now emits SMuFL glyph names (smufl-mapping)
for music-font text characters, articulation glyphs and custom-line glyphs; facts.py recognises
dynamics, articulations, tremolos, trills ("tr" articulations and trill lines, with
accidental), bowings by name, with the old Maestro codepoint tables as fallback. A trill custom
line with both ends at one spot (Trex: just the "tr♭" symbol) is a trill on that note.

### Round 5 findings (user's hand-edited Willow) ✅
See [experiments/round5-results/README.md](../experiments/round5-results/README.md) for the table
of encodings: trills (`TrillEventDefinition`, `kTrillInterval`), glissandi
(`GlissandoLineEventDefinition` with note event + block instance IDs, may cross staves),
playing techniques (`PlayingTechniqueEventDefinition` + `pta.*` appearance), tremolo
(`kNoteSingleStemTremolo`), fp (`CombinedDynamicDefinition`), sffz (Sfz level 2), accidental
visibility needs `_v3` too. Finale side: trill custom lines (char 126 + "tr" 217 + small
accidental 105/73/233), tremolo articulations (Maestro 33/64/190), a2/º1/º2 technique text on
shared staves, duplicate smart shapes.
- Legacy `.mus` text: finale-mus-reader converts the saving machine's encoding to Unicode; music
  fonts need the raw byte back (`_raw_music_chunks`). Text-font symbols (e.g. "Tempo (∞=120)" vs
  Finale 27's "°") still differ: matters once tempo text is converted.

### Round 4 findings ✅
- **Forced ties**: one note spanning the chain, `kNoteSplitDurations` = the tied pieces
  (`list: {string: "1"}, {string: "1"}` for two forced tied crotchets), from the user's
  ref-ties.dorico. Matches the writer. Unforced notes carry no property.
- Measure-attached hairpin ends sit inside the note they cover; snap them forward (Willow bar 1).

### Round 3 findings
- `kNoteSplitDurations` in native files: always a **single value equal to the note's duration**
  (4,002 cases in the user's projects) = "force this displayed duration". Multi-value lists
  never occur there because those projects have no forced ties; Round 4 confirmed the list form. `kNoteForcedSplitPositions` (`null:`) appears separately.
- Hidden Finale expressions (`measExprAssign/hidden`) are not notation; skipped.

### Round 2 findings ✅
See [experiments/round2-results/README.md](../experiments/round2-results/README.md).
- The **project library** (not options) is what makes noteheads render; the writer now builds
  a new project's library from the install's factory files (`f2d/dorico/library.py`, entity
  list in `f2d/data/new_project_library.json` from a File > New project) plus the score's needs.
- **Pick-up**: `barDivisionData/irregularBarLength` = pick-up length ✅ (our guess was right).
- **Linked dynamics**: one `DynamicGroupElementDefinition` shared by several staves' events
  (`referencingEventIDs` = comma-separated event IDs) ✅ (from the user's projects).

### Round 1 findings ✅
See [experiments/round1-results/README.md](../experiments/round1-results/README.md). Dorico opens
generated files. With only instrument definitions in the library, notes have no noteheads and
double-clicking one crashes; with a seed project's full library + options, noteheads are fine
(Round 2 isolates which). No playback data → Dorico applies the user's default playback template.
Dynamic groups: one `DynamicGroupEventDefinition` (duration 0) per group; sub-elements carry
positions relative to the group start (writer groups chains automatically, `Options.group_dynamics`).

## 4. Open questions (to settle with test rounds)

1. ~~Does Dorico open a generated project with no options, minimal library, no playback data?~~ Yes, but no noteheads; a full library fixes it (Round 2). Does the install-built library (Round 3) work as well as a seed's?
2. ~~Does Dorico then apply the default playback template by itself?~~ Yes ✅
3. ~~Pick-up bar encoding~~ ✅ `irregularBarLength`.
4. fp / sfp / sf / sffz encodings (Combined / Force dynamics).
5. Whether forcing every note's duration (file 04) reproduces Finale better than forcing ties only (03).
6. Does Dorico accept our IDs/ordering in large files (file 12, 31 staves)?

## Round 12 encodings (2026-10-31; user's `experiments/round12/ref-harmonics-lines.dorico`)

- Harmonics: note properties `kNoteHarmonicType` (`kNatural` / `kArtificial`) and, for
  artificial ones, `kNoteHarmonic` = partial (int: 2 octave, 3 touched 5th, 4 touched 4th,
  5 touched major 3rd). The note's pitch is the stopped note; Dorico draws the diamond.
- Lines: `HorizontalLineEventDefinition`. Not attached to notes: in the **stave** stream,
  `startAttachmentType`/`endAttachmentType` `kRhythmicPosition` (or `kBarline`), note IDs
  `{int: -1}, {int: -1}`. Attached to notes: in the voice stream, `kNote` + note event and
  block instance IDs. `lineStyleEntityID` names a factory style (`linestyle.solidLine`,
  `linestyle.dashedLineShort[InwardHook[s]]`, `...SolidArrowhead`, `linestyle.wigglyLine` ...);
  the project library must hold the style, its body and caps. Text: `kHorizontalLineText`
  (string) + `kHorizontalLineTextPlacement` `kStart` (other values not seen).
- Metric modulation: `ImmediateTempoChangeEventDefinition` data `type` `kEquation`, `flags` 1,
  `tempoEquation/left` and `right` = `{list: {int: note code}, {int: dots}}` (minim 9, crotchet 8).
- Text border: `kTextBorder` value `null: ` + `kTextBorderStyle` `kRectangle`.
- Gradual playing-technique change: first technique has a duration up to the next one; both carry
  `kEventGroupId` (int, same value); `idGenerators/eventGroup` = next free group ID.
- Two-note tremolo (`ref-tremolos.dorico`): first note `kBeamStart` "list: {int: strokes},
  {int: 0}", second `kBeamEnd` `null: `; each note keeps its real length and gets
  `kNoteSplitDurations` = that length.
- Confirmed in Dorico: line text with no `kHorizontalLineTextPlacement` is centred;
  `kHorizontalLineLineStartCapID` "lineannotation.inwardHookAxisAligned" adds a start hook.

## Custom text playing technique for passage words (2026-10-31; user's `HP FLUTE print.dorico`)

The user's way of writing a passage marking such as "stacc., brillante" in Dorico: one
**custom playing technique** shown as text and linked to Dorico's built-in *Staccato*
playback technique (`pt.staccato`), placed once at the start of the passage. Found by the
dorico-hp session (`C:\Users\kspie\Documents\Dorico Projects\HP FLUTE print.dorico`; the
user kept it generic, text "staccato", to avoid many specific custom techniques). Three
library entities plus one event:

| Where | Entity | Key fields |
|---|---|---|
| `library/playingTechniqueAppearanceCollectionDefinition/entities` | `PlayingTechniqueAppearanceDefinition` | `name` "Staccato (text)", `entityID` `pta.user.staccato_text`, `parentEntityID` empty, `inheritanceMask` 0, `playingTechniqueAppearanceCategory` kCommon, `playingTechniqueAppearanceType` **kText**, `language` kItalian, `text` "staccato", `compositeEntityID` → below, `playingTechniqueEntityID` **`pt.staccato`**, `alwaysHasDuration` false, `defaultPlacement` kAbove, `shownInCues` false, `continuationGlyph`/`continuationText` kNothing, `isBowingMark` false, `durationLineData`/`transitionLineData` (line styles `linestyle.solidLineInwardHook` / `linestyle.solidLineSolidArrowhead`, attachments kHalfXHeight) |
| library composites | `CompositeDefinition` | `name` same, `entityID` `comp.user.<32 hex>`, `category` kPlayingTechniques, one `component` (`componentId` → text primitive, `componentType` kText, offsets 0, scales 100.000000, `maxOpticalScale` 100, `colour` kDefault), empty `relativeAttachments`, `scalingRules` |
| library text primitives | `TextPrimitiveEntityDefinition` | `name` "staccato", `entityID` `text.user.<32 hex>`, `fontStyle` font.playingtechnique, `text` "staccato" |
| flow block (voice stream) | `PlayingTechniqueEventDefinition` | `position`, `duration` 0, `appearanceEntityID` `pta.user.staccato_text`, `appearanceType` **kGlyph** (even for a text appearance), empty `data` |

Playback: linking to a built-in playback technique means expression maps that know
`pt.staccato` switch patch natively; maps that don't (SWAM Flute: natural only) ignore it.
dorico-hp's Apply reads both the playback technique and the words (`passages.technique_flags`).
A custom *playback* technique (`pt.user.*`, e.g. the ET score's "B Spiccato") is only an
expression-map switch; tools should not read meaning into its words.

**User decision (2026-10-31):** when a Finale score has a passage word such as "stacc." or
"stacc., brillante" (technique text expression), the converter writes this kind of custom text
playing technique with the same words, linked to `pt.staccato` (other words to their built-in
playback technique where one exists, e.g. spicc. → `pt.spiccato`, leg. → `pt.legato`), not a
plain text item. Not implemented yet. **Confirmed 2026-11-01:** all the words stay in one
technique ("stacc., brillante"), not technique + separate text: a text item can't be grouped
with the technique for layout and would need its font/size matched by hand.
