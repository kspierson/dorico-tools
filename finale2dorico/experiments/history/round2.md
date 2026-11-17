# Round 2: noteheads, version message, dynamic groups

**Folder from Windows:**
`\\wsl.localhost\Ubuntu-26.04\home\ken\dev\dorico-test\finale2dorico\experiments\round2\`

Regenerate with `python3 experiments/make_round2.py`.

## What Round 1 showed (and what changed)

- "Created in Dorico 3": we wrote file-format version 1.982; Dorico 5.1.60 writes 1.1299
  (checked in your own projects). **Fixed in all files below.**
- No noteheads, and double-clicking a note or slur crashed Dorico, in the minimal files only;
  the seeded file 02 (library + options borrowed from a Steinberg tutorial project in your
  Dorico folder) was fine. Files 01a–01d below find out which of the two fixes it.
- Playback: Dorico applied "Silence" because that is your default playback template
  (Preferences > Play). That is the intended behaviour.
- Dynamics/hairpins are now grouped the way you grouped 07 (rule below).

## What to do

Please **don't double-click notes** in files that show no noteheads (that's the crash).

| File | What it is | Check | Result |
|---|---|---|---|
| 00-reopen-07-saved-by-dorico | Your saved copy of round-1 file 07 (Dorico wrote it, with a full library) | Noteheads now? | |
| 01a-flute-version-only | Like round-1 01, version fixed | Version message gone? Noteheads? | |
| 01b-flute-seed-library | + library from the tutorial project | Noteheads? Double-click a note OK? | |
| 01c-flute-seed-options | + options from the tutorial project (library minimal) | Noteheads? | |
| 01d-flute-seed-both | + both (like round-1 02) | Noteheads? Double-click OK? | |
| 07-hairpins-horn-grouped | Seed both; dynamics grouped automatically | Groups as you'd expect? (see below) | |
| 08-articulations-violin | Seed both | Staccato, accent, tenuto, marcato, staccatissimo visible and right? | |
| 09-slurs-cello | Seed both | Slurs real Dorico slurs (select one; Properties shows slur options)? | |
| 10-pickup-amazing-grace | Seed both | Bar 1 a 1-beat pick-up, then full 3/4 bars? | |

**Grouping rule**: dynamics and hairpins form one group when each starts exactly where the
previous one ends (dynamic → hairpin from it → dynamic at its end; or cresc → dim back to
back). This reproduces your grouping of 07 exactly, except the last bars: the cresc at
bar 18 beat 2 ends on the dynamic at bar 19, where the dim starts, and the rule puts those
three in one group; you left them separate. Was that deliberate?

Still wanted from Round 1 (2 minutes, they settle guesses):
- **ref-pickup.dorico**: File > New, a Flute, time signature `3/4,1`, a crotchet in the
  pick-up and a few notes after; save into this folder.
- **ref-new.dorico**: File > New, a Flute, a couple of notes, save. (A pristine Dorico 5
  project: shows exactly which library entries and options a new file carries.)
