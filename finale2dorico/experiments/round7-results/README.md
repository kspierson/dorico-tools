# Round 7 results (2026-10-28): reference markings

The user added the requested markings to `ref-start.dorico` (saved over it; kept here as
`ref-markings.dorico`; decoded copy in `ref/`, git-ignored). All items present.

| Item | Encoding (stream) |
|---|---|
| Chord symbol C (bar 1 beat 1), G7 (beat 3) | `ChordSymbolEventDefinition` (global): `chordSymbolData/primaryChord/definition` (`quality` kMajor, `interval` kNone / k7, `alterations` []), `root` (`noteName` C, `accidentalType` kNatural); empty `playedPrimaryPitches`, `playedSecondaryPitches`, `chordDiagramData` |
| Lyrics "la la la la" (bar 2) | `LyricEventDefinition` (voice) per note -> `LyricElementDefinition`: `text`, `syllableType` kWholeWord, `lineLocation` kBelow, `lineType` kVerse, `lineNumber` 0, `richText` (paragraph.lyrics) |
| Repeat barlines | global `BarDivisionElementDefinition/barDivisionData/barlineChangeIfAny/type`: kEndRepeat (end of bar 5), kEndAndStartRepeat (start of bar 3; user asked for a start repeat), kDouble (end of bar 8). Final barline automatic (nothing stored) |
| 1st/2nd endings (bars 4-5, 6) | `RepeatEndingLineEventDefinition` (global), position 12, duration 12; properties `kRepeatEndingLineNumSegments` int 2, `kRepeatEndingLineSegmentDuration` "8" / "4" (propertyOffset "2:0:0:0" / "2:1:0:0") |
| Segno / Coda | `RepeatMarkerEventDefinition` (global) `sectionType` kSegno (bar 9 start), kCoda (bar 15 start) |
| To Coda / D.S. al Coda | `RepeatMarkerEventDefinition` `jumpTypeAndQualification` (kToCoda + kEndOfFlow; kDalSegno + kAlCoda), stored at the bar's **last beat** (end of bar 12 -> 47; end of bar 14 -> 55) |
| Tempo range Allegro ♩ = 92–96 | `data/tempoValueRange` = 625000 (96) next to `absoluteTempo/tempoValue` 652173 (92); flags 3 |
| ♩. = 60 | `tempoValue` 1000000 with `beatUnits` {8},{1}: **tempoValue counts the stated beat unit** |
| Staff-only 12/8 (Flute bar 11) | `BarDivisionEventDefinition` in the **stave** stream at 40 (12/8) and 44 (4/4 back); Dorico added a **hidden tuplet** over the bar: `TupletEventDefinition` 12:8 quavers (`{12},{8},{7,0}`), duration 4, `kTupletTextContent` kNone, `kTupletBracketVisibility` kHidden. The bar keeps the global 4-crotchet length; its notes are tuplet-scaled. |
