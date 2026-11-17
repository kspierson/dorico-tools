# Round 6: players from shared staves, techniques, trills, glissandi, tremolos

**Folder from Windows:**
`\\wsl.localhost\Ubuntu-26.04\home\ken\dev\dorico-test\finale2dorico\experiments\round6\`

Regenerate with `python3 experiments/make_round6.py` (all five real scores, `f2d convert` defaults).

## What's new (from your file 13)

- **Shared staves exploded into players.** Willow's "Horn in F 1" / "Horn in F 2" staves each carry
  two players in two layers. They become **Horn 1, Horn 3, Horn 2, Horn 4** (your 13's order and
  pairing). Bar by bar: where both layers have music, layer 1 -> upper player, layer 2 -> lower;
  a single line follows the latest Finale marking: "a2" = both play it, "1." / "2." = only that
  player. The markings themselves are dropped (Dorico shows its own when condensing). Dynamics,
  hairpins, mutes go to both players.
- **Playing techniques** from Finale's technique text: Mute (brass -> straight mute, as you used;
  strings -> con sord.), Open, pizz., arco, con/senza sord.
- **Trills**, including Finale's custom "tr♭" trill lines (Willow uses 15). A trill covers its
  note and the notes tied to it. The ♭/♯/♮ shown with the "tr" sets the trill interval where it
  makes sense on that note (else Dorico's default).
- **Glissandi** (harp, hand to hand across staves; also to/from grace notes).
- **Single-stem tremolos** (Finale draws them as articulations: 1, 2 or 3 strokes).
- **fp / ffp / fpp / pf** as Dorico combined dynamics (Finale had several fp's in Willow that were
  dropped before), **sffz** as a level-2 sfz.
- **Dynamics clean-up**: duplicate/overlapping hairpins removed (24 in Willow, e.g. Horn 1's
  doubled crescendos at 169); groups now join across a longer gap (up to a bar) when the
  instrument keeps playing through it, as in your edits (Horns at 187, Bass Clarinet at 81).
- Fixes: forced accidentals now survive (Dorico wants `kNoteAccidentalVisibility_v3` too);
  grace notes before a rest are no longer moved onto the next note.

## Files

| File | Check | Result |
|---|---|---|
| Willow | Horns as four players; are the right notes in each (e.g. bar 17 "a2": both; bar 22 "2."; bar 1 split)? Trills (bars 1, 10, 17, 24 ...), harp glissandi, mutes, tremolos (timpani rolls), fp in bar 1 | |
| Trex | 30 glissandi, 98 tremolos, con sord./open/pizz./arco | |
| VV_Full | 41 trills, pizz./arco | |
| Venus, WW | General check | |

Updated after your answers (files regenerated):
- Willow bar 7: the horn chords (two notes in one layer) are now **split**, upper note -> upper
  player. Bar 11's single note follows Finale's "1." marking there (Horn 1 only).
- Harp glissandi are written as **straight** lines.
- Dynamics on a shared staff now go only to the players who play at that point.

**Reviewer** (report only): `Willow.review.txt` etc. next to each file (JSON versions for the
future UI). Run it on any project: `python3 -m f2d review X.dorico [--all] [--json out.json]`.

Trex's wavy lines (Violins, bars 22-25 and 39) are now **half-step trills**, as you said: the
symbol is a "tr♭" from the EngraverFontExtras font, which the converter now reads by glyph name
(any Finale music font, not just Maestro). Trex's 485 up-bows also come across now.
