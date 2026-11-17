# Round 11: chord symbol and lyric reference (Dorico encodings still unknown)

**Folder from Windows:**
`\\wsl.localhost\Ubuntu-26.04\home\ken\dev\dorico-test\finale2dorico\experiments\round11\`

Open `ref-start.dorico` (a piano with 8 bars of crotchets), add the items below, and save it as
**`ref-chords-lyrics.dorico`** in the same folder. Positions don't matter much; one item per beat
is ideal. Round 7 already gave plain chords (C, G7) and single-word lyrics; this round fills in
the rest so Finale's chord suffixes and hyphenated lyrics convert exactly.

## Chord symbols (Shift+Q): select the note on each beat, type exactly this, Enter

| Bar | Beat 1 | Beat 2 | Beat 3 | Beat 4 | What it shows |
|---|---|---|---|---|---|
| 1 | `Cm` | `Cm7` | `Cmaj7` | `C6` | minor, minor 7th, major 7th, added 6th |
| 2 | `C9` | `C11` | `C13` | `Cdim` | extended chords; diminished triad |
| 3 | `Cdim7` | `Cm7b5` | `Caug` | `Csus4` | dim 7th, half-diminished, augmented, suspension |
| 4 | `C7sus4` | `Csus2` | `Cadd9` | `C6/9` | sus with 7th, sus2, added note, 6/9 |
| 5 | `C7b9` | `C7#9` | `C7#11` | `C7b13` | altered tones |
| 6 | `C7alt` | `Cmaj7#11` | `C/E` | `Bb7` | alt, alteration on maj7, slash bass, flat root |
| 7 | `F#m7` | `N.C.` | `C7(b9,#11)` | (empty) | sharp root, no chord, two alterations |

If Dorico turns one into something slightly different, leave it as Dorico made it.

## Lyrics (Shift+L), bars 6-8 (below the staff, so they don't collide with the chords)

1. Bar 6 beat 1: `hal-` Space `le-` Space `lu-` Space `jah` (four syllables, hyphenated).
2. Bar 7 beat 1: `love`, then Space twice with nothing typed (held over three notes: extender).
3. Under bar 6, Down arrow in the popover (line 2): `sing` Space `now`.
4. Bar 8 beat 1, popover switched to Chorus: `joy`.

Save as **`ref-chords-lyrics.dorico`** in this folder. Nothing needs exporting.

## Results (2026-10-30) ✅

User's file `ref-chords-lyrics.dorico` (27 chords, 28 lyric syllables).

| Item | Dorico encoding (`chordSymbolData/primaryChord`) |
|---|---|
| quality | kMajor, kMinor, kDiminished, kAugmented; **sus chords: kNoThird** + a kSuspended alteration |
| interval | kNone, k6, k7, k9, k11, k13, kMaj7 (kMaj9/11/13 by name) |
| alteration | `alterations/alteration`: `type` (kAltered, kAdd, kSuspended; kOmit by name) + `degreeAndAdjustment/degree` + `adjustment` (kFlat, kSharp, kUnaltered) |
| examples | m7b5 = kMinor k7 + altered 5 flat; 6/9 = k6 + add 9; C7alt = k7 + altered b5, #5, b9, #9; sus4/sus2 = suspended 4/2 |
| slash bass | `alteredBass/noteName` + `accidentalType`, inside primaryChord after root |
| N.C. | `chordSymbolData` with no `primaryChord` |
| root accidental | `accidentalType` kSharp (F#m7) / kFlat |
| lyric syllables | `syllableType` kWholeWord, kStart, kMiddle, kEnd (kMiddle confirmed 2026-10-30: `check/kmiddle.dorico` opened, saved and exported by Dorico, hyphens drawn) |
| extender | the LyricEvent's **duration** (to the end of the held notes) |
| chorus | `lineType` kChorus, `lineNumber` counted separately from verses |

Converter check: a generated file with the same 27 chords matches the user's file chord for chord
(26 of 27; the 27th is a different chord in the user's file: C7(b13) where the list had Bb7).
Implemented in the writer; hyphenated lyrics and extenders now written as Dorico's own.
