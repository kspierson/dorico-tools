# Round 8: the converter batch (tempo, text, ottavas, doublings ...) on nine scores

**Folder from Windows:**
`\\wsl.localhost\Ubuntu-26.04\home\ken\dev\dorico-test\finale2dorico\experiments\round8\`

Regenerate with `python3 experiments/make_round8.py`. This supersedes Round 6 (same five scores,
newer converter) and adds four John Williams scores from G:\Scores. Each file has a review next
to it (`.review.txt`).

> **Fixed in the converter after these files were generated** (Round 7 results): metronome
> ranges are now written as ranges, and E.T.'s 12/8-against-4/4 staves now get a staff-only 12/8
> with correct quavers. Also since: breath marks/caesuras, sf, fermata styles, and **page setup**
> (these files have Dorico's default 7 mm staff, so big scores look squashed in Engrave mode;
> the converter now carries Finale's page and staff size over and shrinks the staff to fit).
> Review the files as they are; they'll be regenerated afterwards.
>
> E.T. (user's note: six flutes): the Finale file itself prints 45 staves, including exact copies
> of flute, bassoon and violin staves and new, mostly empty staves (a third flute from bar 110,
> English horn, percussion, xylophone): it is a working copy. The converter now warns about the
> identical staves.

## New since Round 6

- **Tempo marks** with text and metronome mark ("SCENE I ♩ = 92", "Slower ♩ = 84"), tempo words in
  older files ("Alla Marcia", "Meno Mosso", "Tempo Primo"), **rit. / rall. / accel.** as Dorico
  tempo changes (until the next tempo mark, at most two bars; dashed "rit." lines keep their length).
  Metronome *ranges* (92–96) are written as the first value for now (Round 7 will show Dorico's way).
- **Rehearsal marks** (also the boxed bar numbers older Finale files use; Dorico shows its own
  letters/numbers per your rehearsal mark settings).
- **Fermatas** (were dropped before!).
- **Ottavas** — and a real bug fixed: **notes under 8va/8vb lines were an octave off** before
  (Finale stores the written pitch there). Found by comparing with Finale's own MusicXML: the
  Asteroid Field now matches all 18,965 notes.
- **Cross-staff notes** (harp, piano).
- **Plain text** (staff text, with ♭ ♯ ♮), e.g. Willow's timpani tunings "Tune to D, B♭, C♯, E♭".
- **Harp pedals**: Finale's pedal diagrams and pedal-change letters -> Dorico harp pedal settings.
- **Pedal lines** (Ped. ... ✱), **arpeggios**, **ornaments** (turns, mordents), up/down bows.
- **Doublings**: Finale staves like "Piccolo (Flute 3)", "Oboe 2 (English Horn)", "Piano/Celeste"
  with "To Flute" / "Picc." instructions become **one player with two instruments**; Dorico adds
  its own change labels.
- Staves named only "1 2" / "3" get their instrument name (bracket group, else instrument type).

## Files

| File | Check | Result |
|---|---|---|
| Willow | Tempo marks (bars 1, 4, ...), rit./accel., rehearsal marks, timpani tuning text, **harp pedal diagrams/changes (are the pedal positions right?)**, the bar-17 8va passage at the right octave | |
| Trex | Pedal lines, trills, up-bows | |
| VV_Full, Venus, WW | WW: fermatas, "Sneaky ♩ = 108", dashed rit. | |
| JW Raider's March (.mus) | Cross-staff harp notes; Celeste 8va passages; doubling players (Bass Clarinet/Clarinet 3, Piano/Celeste); rehearsal marks; Alla Marcia / Meno Mosso | |
| JW Superman (.mus) | Three flutes from one staff; horns/trombones | |
| JW Asteroid Field | Piano/Celeste 8va passages | |
| JW E.T. | Piccolo/Flute 3, Oboe 2/English Horn, Piano/Celeste doublings. Known issue: some staves run in **12/8 against 4/4** in Finale; until Round 7 shows Dorico's way, their quavers come out as odd rhythms (correct timing, wrong notation). E.T. also has duplicate staves in Finale (28 onward repeat earlier ones), which come across as extra players | |

Not converted yet: chord symbols, lyrics, repeats/endings/codas (Round 7), caesuras/breath marks,
custom lines other than trills, percussion kits, page layout.
