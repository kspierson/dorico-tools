# Round 1 (extra): legacy .mus files

Five tiny test documents saved by old Finale releases (1.0 through 2012), converted with the
new full reader (musxdom + finale-mus-reader). They come from finale-mus-reader's test suite
(MIT licence); each tests one thing, so they're short.

**Open these after the main Round 1 files** (`../round1/`), and only if 01 opened there:
they use the same Dorico writer, so a writer problem will show up in both.

**Folder from Windows:**
`\\wsl.localhost\Ubuntu-26.04\home\ken\dev\dorico-test\finale2dorico\experiments\round1-mus\`

Regenerate with `python3 experiments/make_round1_mus.py` (needs the extractor built).

| File | Saved by | What to look for | Result |
|---|---|---|---|
| m1-finale1-pickup | Finale 1.0 | One bar: a quaver pick-up (B) only. Uses the same guessed pick-up encoding as round1/10. | |
| m2-finale26-clefs | Finale 2.6 | Two staves of fast notes; staff 1 changes to alto clef at beat 1¼ of bar 1 and back to treble at beat 1½ of bar 2 | |
| m3-finale2000-layers | Finale 2000 | Bar 1: B/G crotchets with accents and staccatos; bar 2: the same notes in layer 2 | |
| m4-finale2008-16ths | Finale 2008 | Beamed semiquavers | |
| m5-finale2012-flags | Finale 2012 | Quavers and semiquavers with rests between | |

Not converted yet in these: the "Tempo (♩=120)" text in m2/m3 (tempo marks are on the to-do list).
