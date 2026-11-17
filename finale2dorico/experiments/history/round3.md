# Round 3: everything with the new defaults

**Folder from Windows:**
`\\wsl.localhost\Ubuntu-26.04\home\ken\dev\dorico-test\finale2dorico\experiments\round3\`

Regenerate with `python3 experiments/make_round3.py`.

## What changed since Round 2

- **Library built from your Dorico install.** Round 2 showed the noteheads need a real project
  library (01b/01d worked, 01a/01c didn't). Instead of borrowing a tutorial project's library,
  the converter now builds exactly the library a brand-new Dorico 5 project has (the list of
  entries comes from your ref-pickup.dorico; the definitions are read from your Dorico folder),
  plus whatever the score needs (instruments, extra clefs, their techniques). No tutorial file,
  no tutorial options. If noteheads are missing anywhere here, this is the reason.
- **Dynamic grouping** now also allows a short gap (up to a crotchet) between items, which
  reproduces your re-saved 07 exactly (the mp in bar 18 + the cresc starting a beat later + the
  dynamic and dim in bar 19 are one group).
- **Linked dynamics across staves** ("horizontal" grouping): identical dynamic groups at the
  same position on different staves now share one definition, which is how your own projects
  store linked dynamics (e.g. ET has one dynamic shared by 9 staves). Willow has 89 linked groups.

Please don't double-click notes in a file that shows no noteheads.

| File | Check | Result |
|---|---|---|
| 01-flute | **Noteheads?** Double-click a note: no crash? No "older version" message? | |
| 03-rhythms-violin | Dotted rhythms, triplets (bar 3+), ties as in Finale? | |
| 04-rhythms-violin-forced | Same with every Finale note length forced. Better or worse than 03? | |
| 05-piano-textures | Grand staff, chords, two voices | |
| 06-dynamics-violin | ppp..fff in the right places (bar 9: sfz on beat 2, mf on beat 3) | |
| 07-hairpins-horn | Grouping matches what you saved? | |
| 08-articulations-violin | Articulations (as in Round 2) | |
| 09-slurs-cello | Slurs (as in Round 2) | |
| 10-pickup-amazing-grace | Pick-up (as in Round 2) | |
| 11-waltz-piano | 3/4 piano | |
| 12-willow-full | Real score: meters (20 changes), instruments, notes in the right bars. **Linked dynamics**: select a tutti dynamic; are the matching ones on other staves linked (and is that what you'd want)? | |
| m1–m5 | Legacy `.mus` conversions (see ../round1-mus/README.md for what each shows) | |

**Linking rule (please confirm):** any dynamic group that is identical (same dynamics, same
hairpins, same lengths) and at the same position on several staves is linked, whatever the
instruments. A stricter option would link only staves that also play the same rhythm there
(the "flutes and oboes in octaves" case). Which would you prefer as the default?
