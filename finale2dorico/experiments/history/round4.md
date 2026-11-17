# Round 4: forced ties, stricter linking

**Folder from Windows:**
`\\wsl.localhost\Ubuntu-26.04\home\ken\dev\dorico-test\finale2dorico\experiments\round4\`

Regenerate with `python3 experiments/make_round4.py`.

## Round 3 follow-ups

- 03/04: the rhythms test piece has **no ties or slurs at all**, so 03 was right; 03 and 04 look
  the same because Dorico's own notation already matches Finale's for those rhythms. The
  forced-duration feature (keeping Finale's ties where Dorico would merge notes) is still
  untested, hence the ties test below.
- 05: the three mf are in the source (bar 1 on both staves, bar 5 upper staff). Expected.
- Willow: hidden Finale dynamics (18, invisible in Finale) are now skipped. The ff on the
  bar-1 barline next to bar 2's mp is in Finale's data (Finale draws it at the end of bar 1;
  in Dorico it can only sit on bar 2 beat 1), so it stays.

## Files

| File | Check | Result |
|---|---|---|
| 01-ties-forced | Should look like **Finale wrote it**: bar 1 two tied crotchets then a minim; bar 2 crotchet, **minim on beat 2**, crotchet; bar 3 dotted crotchet tied to a quaver, minim; bar 4 semibreve tied over the barline to a crotchet. | |
| 02-ties-dorico-default | Same notes with nothing forced (Dorico's own choice), for comparison: bar 1 probably a minim, bar 2 probably crotchet~crotchet in the middle. Does 01 differ from 02 as described? | |
| 12-willow-full | **Linking** now only joins staves that play the same rhythm over the phrase (the "would condense together" test): e.g. Cl 3 + Hn 1 and Cl 2 + Hn 2 at the start, separate from the woodwinds/trumpets group. Also: dynamics/hairpins that Finale had at odd positions (beat 1 + 595/1024 etc.) are now snapped onto the note they sit next to. Better? | |

## One reference file, please (2 minutes)

**ref-ties.dorico**: File > New, a Flute, 4/4. Turn on **Force duration** (the "O" key in
note input) and enter the same as 01: bar 1 two crotchets tied (C), then a minim; bar 2
crotchet, minim on beat 2, crotchet. Save into this folder. It shows exactly how Dorico
stores forced ties, which my writer currently guesses.
