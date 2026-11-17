# Round 7: one reference file (the markings your projects don't contain)

**Folder from Windows:**
`\\wsl.localhost\Ubuntu-26.04\home\ken\dev\dorico-test\finale2dorico\experiments\round7\`

Your own projects already show me how Dorico stores tempo marks, rit./rall., text, rehearsal
marks, fermatas, ottavas, pedal lines, arpeggios, harp pedals, ornaments, instrument changes,
doubling players, cross-staff notes and D.C./Fine. What's missing is below.

Open **ref-start.dorico** (Flute + Piano, 16 bars of 4/4: the flute plays a scale in crotchets,
the piano holds C chords). Add exactly these, then **Save As `ref-markings.dorico` in this folder**:

| Bar | Add | How (Write mode) |
|---|---|---|
| 1 | Chord symbol **C** on beat 1, **G7** on beat 3 (Flute) | select the note, Shift+Q, type `C` / `G7` |
| 2 | Lyrics under the Flute: **la la la la** (one syllable per note) | select first note, Shift+L, type, space to advance |
| 3 | Start repeat barline at the start of bar 3 | Shift+B, `:|:` … or the Repeat structures panel: Start repeat |
| 4-5 | **1st ending** over bars 4-5 (with end repeat at the end of bar 5) | select bars 4-5, Repeat structures panel: Repeat ending |
| 6 | **2nd ending** over bar 6 (Dorico usually adds this with the 1st; check it's there) | |
| 8 | **Double barline** at the end of bar 8 | Shift+B, `||` |
| 9 | **Segno** at the start of bar 9 | Repeat structures: Segno |
| 12 | **To Coda** at the end of bar 12 | Repeat structures: To Coda |
| 14 | **D.S. al Coda** at the end of bar 14 | Repeat structures: D.S. al Coda |
| 15 | **Coda** at the start of bar 15 | Repeat structures: Coda |
| 16 | **Final barline** at the end | Shift+B, `|]` (if not automatic) |

Two extra items (added later; skip if you've already saved):

| Bar | Add | How |
|---|---|---|
| 1 | Tempo **Allegro ♩ = 92–96** (a metronome *range*) | Shift+T, type `Allegro q=92-96` |
| 10 | Tempo **♩. = 60** (dotted crotchet beat) | Shift+T, type `q.=60` |
| 11 | A **12/8 time signature on the Flute only** (piano stays 4/4) | select the Flute's bar 11, Shift+M, type `12/8`, then **Alt+Enter** (staff-only) |

If something is awkward to add, skip it and tell me which.
