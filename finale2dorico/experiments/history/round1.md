# Round 1: does Dorico open files we generate from scratch?

These 12 projects were written by finale2dorico straight from Finale `.musx` files
(no MusicXML involved). Dorico has never seen them. Earlier dorigit tests only *edited*
Dorico-made files; these are built from nothing, so the main question is simply whether
Dorico opens them.

**Folder from Windows:**
`\\wsl.localhost\Ubuntu-26.04\home\ken\dev\dorico-test\finale2dorico\experiments\round1\`
(copy it to a Windows folder first if Dorico complains about the network path).

Regenerate with `python3 experiments/make_round1.py`.

*Regenerated 2026-10-26 with the new full reader (musxdom). Changed: **06** (the mf and sfz in
bar 9 had both landed on beat 1) and **12** (the old reader missed most of Willow's time
signature changes, shifting everything after bar 5). 07 changed only internally. If you
already opened 06 or 12, please look at them again.*

Also see `../round1-mus/` for five small files converted from old Finale `.mus` files.

## What to do

1. Open **01-flute-minimal** first. If Dorico refuses it or crashes, try **02-flute-seeded**,
   note what happened, and stop there; that alone tells me what to change.
2. If 01 opens, open the rest. For each, note **opens? / looks right? / anything odd**.
3. In 01, check playback: does Dorico assign sounds by itself (your default playback
   template), or is it silent? Play > Playback Template shows which template is applied.
4. Please **don't save over** these files. If you want to keep one, use Save As.

Fill in the right-hand column (or just tell me in chat):

| File | From (HPCaptures\finale) | What to look for | Result |
|---|---|---|---|
| 01-flute-minimal | 01-baseline-flute | Opens? Notes, barlines, part layout. Playback template? | |
| 02-flute-seeded | 01-baseline-flute | Same music; library/options copied from a Dorico tutorial file. Any difference from 01? | |
| 03-rhythms-violin | 09-rhythms-violin | Dotted rhythms, triplets (bar 3+), ties. Same notation as in Finale? | |
| 04-rhythms-violin-forced | 09-rhythms-violin | Same, but every note has Finale's notated length forced. Better or worse than 03? | |
| 05-piano-textures | 12-piano-textures | Grand staff with brace, both hands, chords, 2 voices | |
| 06-dynamics-violin | 05-dynamics-violin | ppp..fff dynamics in the right places | |
| 07-hairpins-horn | 06-hairpins-horn-f | Hairpins; Horn in F transposed correctly in the part / transposed score | |
| 08-articulations-violin | 03-articulations-violin | Staccato, accent, tenuto, marcato, staccatissimo | |
| 09-slurs-cello | 04-slurs-cello | Slurs; clef changes | |
| 10-pickup-amazing-grace | 11-amazing-grace-flute, first 2 beats trimmed | **Pick-up bar**, written with a guessed encoding. Is bar 1 a 1-beat pick-up (C), with full 3/4 bars after it? | |
| 11-waltz-piano | 10-waltz-piano | 3/4 piano | |
| 12-willow-full | scores\Willow | Real orchestral score: instruments right (names, transpositions, Horn/Trumpet without key signature)? Notes in the right bars? | |

## Two small reference files I'd love you to make (2 minutes)

These give me Dorico's own encoding for things I had to guess:

- **ref-pickup.dorico**: File > New, add a Flute, type time signature `3/4,1` (3/4 with a
  1-beat pick-up), enter a crotchet in the pick-up and a few notes after, save into this folder.
- **ref-import-rhythms.dorico**: File > Import > MusicXML
  `C:\Users\kspie\Documents\HPCaptures\musicxml\09-rhythms-violin.musicxml`, save into
  this folder as is. (Dorico's own import of the same piece, to compare with 03/04.)

## Known gaps (not bugs in this round)

Not converted yet: text and tempo marks, playing techniques (pizz./arco), trills,
glissandi, lines, fp/sf/sffz dynamics, lyrics, chord symbols, repeats, rehearsal marks,
percussion maps, cross-staff notes, layout/page formatting. Rests are left to Dorico.
