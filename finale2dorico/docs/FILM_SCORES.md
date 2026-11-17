# Film-score corpus (user's D:\SCORES+BOOKS\Film Scores, 2026-10-28)

Published / recording-session Finale files, most with PDFs of the same pages. They show a film
"house style" (big time signatures, bar numbers under the system, paired players per staff, cue
notes, timings), so they are the best test set beyond plain conversion.

| Folder | Finale files | PDF |
|---|---|---|
| James Horner / Avatar / Finale (.mus) Files | 53 `.mus` (cues, revisions, inserts; plus a .rar) | `James  Horner - Avatar (Complete) [E].pdf`, 994 pages, vector; cue -> page index in [research/avatar-pdf-index.txt](../research/avatar-pdf-index.txt). **Best Finale<->PDF pair** (user) |
| John Williams / Superman | `Superman.MUS` | per-cue PDFs (sketches, film versions) |
| John Williams / Superman / Concert Scores | `John Williams - Superman.mus` | Suite, March, Flying Sequence PDFs (+ .rar) |
| John Williams / E.T. / Concert Scores | `John Williams - E.T. - Adventures On Earth.mus` (**clean: 28 staves, matches the PDF**; the G:\Scores "bak" .musx is a 45-staff working copy) | `John Williams - ET - Adventures On Earth.pdf` (62 pages) |
| John Williams / Empire Strikes Back / Concert Scores | `... The Asteroid Field.mus` | Asteroid Field PDF (Finale 2004 export) and others |
| John Williams / Raiders / Concert Scores | `John Williams - Raider's March.mus` | Raider's March PDF |
| Marco Beltrami / The Thing / ... / MB-TT-SIBMUS | 17 `.mus` + 6 Finale files with no extension (`THG_1m08_(B)_DN` ...); 17 `.sib` are Sibelius (out of scope) | `Score PDFs/` (one per cue) |

Tools: `research/tools/pdf_pages.ps1` renders PDF pages to PNG with Windows' own PDF engine (no
installs; run from WSL via powershell.exe); `research/tools/pdf_index.py` lists each page's text
(stdlib PDF parser) to find a cue's pages.

## Survey (all 79 Finale files converted, 0 failures, 340 s)

Most common things not converted yet (counts over all files):

| Count | Item | Note |
|---|---|---|
| 1,200 | smart shapes `smartLine` / `solidLine` / `dashLine` / `dashLineDown` | custom lines (div./unis. brackets, "cue" lines, ...) |
| 476 | articulation `stringsHarmonic` | natural harmonic circle |
| 327 | smart shape `tabSlide` | between two notes (Avatar). **Not printed** in the published PDF (2m3a bar 22 trombones show only a slur): left unconverted (2026-10-30) |
| 226 | measured tremolos | |
| 181 | articulation `rest..nd` | rest glyphs used as articulations (to check) |
| ~700 | "music-symbol text" in legacy fonts (**partly fixed 2026-10-29**: metronome marks with Maestro digits, sff as "S"+"f", "8va"/"loco" text ottavas; left: metric modulations "h = q" (only E.T., bars 190/196/292; Round 12), a few odd ones) (`ß`, `Ã`, `ç`, `U`, tempo marks with `{qÈ¦ª}`) | old Maestro/Engraver/tempo-font characters: needs legacy font maps (smufl-mapping has them) |
| ~600 | expressions in the dynamics category that are not dynamics | `a2`, `cresc.`, `dim.`, **timings** (`1:23.4`, film), `unis.`, `secco`, `senza sord.`, tempo words (`Maestoso`), percussion instrument changes (`Taiko`, `Piatti`, `Gran Cassa`, `Snare Drum`) |
| 136 | `brassMuteClosed` (+) | |
| 110 + 12 | parenthesised noteheads / accidentals | |
| 72 + 16 | glissando endpoints not found / ends on another instrument | |
| 41 | identical staves | Avatar: often unison doublings (e.g. both violin staves) |

Line survey 2026-10-30 (live shapes only; Finale leaves dead shapes on deleted notes, e.g. 742
of the 1,070 tab slides): 2,243. "tr 1/2" / "tr WT" trill lines 350 (converted, with the step);
plain solid/dashed lines ~900 and dashed lines with a down hook 70; "Cue" / "Cue:" / "Cue (don't
play):" dashed lines ~220; The Thing: dashed lines with centre words ("possibile", "push",
"molto", "poco") ~300 and technique changes ("ord. -- move bow towards... --> sul pont.") ~40.
All but the tab slides are attached to beat positions, not notes. Encodings: Round 12.

## Avatar findings (2m2r compared with PDF pages 100-108)

- No instrument types or transpositions anywhere (concert-pitch session score, generic staves);
  only the bass has its octave. Names come from staff + bracket group: "1", "2 - Picc.", "1)",
  "1 -", "2 - Cfg.", "Horns" + "1\n3" ...
  Fixed: "N - X" means player N on X (Picc., Cfg.); "1)" / "1 -" take the group name; a table of
  standard orchestral names/abbreviations is checked before fuzzy matching (fixes "Cello" ->
  cowbells, orchestral "Bass" -> bass guitar, "G.C.", "Cfg.", "E.H." ...).
- Fixed (user decisions 2026-10-29): untyped staves with no transposition are treated as
  concert pitch and get the **standard** instrument (B-flat clarinet/trumpet/cornet, F horn) unless
  a key is stated in the name or staff text ("in C", "C Tpt.", "E-flat Cl."); a key stated on one
  staff of a family is shared by its keyless siblings; every such choice is in the report
  (f2d/keys.py, `FactsReader._reconcile_keys`, `DoricoInstall.resolve`). Paired players written as
  chords ("Horns 1 3", "Trumpets 1, 3") and two-instrument staves ("Bass Tbn. / Tuba") are split
  into players (2m2r: Horns 1-8, Trumpets 1-4, Trombones 1-4, Bass Tbn., Tuba).
- Open: "Pno RH" / "Pno LH" are two separate staves (a synth part) rather than one grand staff.
- House style seen in the PDF: large time signatures across groups of staves, bold bar numbers
  under the system, every staff always shown, "Cue (don't play):" cue notes with a dashed line,
  "div. a3" on violas, unnamed synth grand staff.
