# Round 10: review set with PDFs (supersedes Round 8)

**Folder from Windows:**
`\\wsl.localhost\Ubuntu-26.04\home\ken\dev\dorico-test\finale2dorico\experiments\round10\`

Regenerate with `python3 experiments/make_round10.py` (Dorico must be running with remote
control allowed; it opens each project, exports the full score as `<name>.pdf`, and closes it).
**Review from the PDFs first**; open a `.dorico` only where the PDF raises a question. Each file
also has the reviewer's notes (`.review.txt`) and the converter report (`.f2d-report.json`).

## New since Round 8

- **Page setup**: Finale's page size and staff size; the staff shrinks (and the page grows to
  11x17) when a system would not fit; condensing on where shared staves became players; empty
  staves hidden where Finale hid them. (Round 8 used Dorico's default 7 mm staff: squashed.)
- **Players**: staves listing two players written as chords ("Horns 1 3", "Trumpets 1, 3") and
  two-instrument staves ("Bass Tbn. / Tuba") are split into players (top note -> first player).
- **Instruments**: untyped concert scores (Avatar) get the standard instrument (B-flat clarinet and
  trumpet, F horn) unless a key is stated ("Trumpet in C"); standard orchestral names
  (Cello, Bass, Picc., Cfg., G.C. ...) no longer mismatch.
- **Condensing groups**: players split from one Finale staff condense back together, and only
  with each other (Hn 1-2 / Hn 3-4 as in Finale, not all four horns on one staff).
- **Old Finale music-font text**: tempo marks with metronome numbers ("Con Brio q = 144"),
  sff written as "S"+"f", "8va ... loco" written as text (now ottava lines, notes at pitch).
- Breath marks / caesuras (incl. staff-only), sf/rf, fermata and caesura styles, curlew.
- **E.T.** now from the clean D:\ `.mus` (28 staves, matches the published PDF), not the G:\ working copy.

## Files and what to compare

| File | Compare with | Check |
|---|---|---|
| Willow, Trex, VV_Full, Venus, WW | Finale | Round 8 items (tempo, rehearsal marks, harp pedals, 8va, pedal lines, fermatas) |
| JW Raider's March / Superman / Asteroid Field / E.T. | the PDFs next to the `.mus` files on D:\ | players (Fl. 1-2, Picc./Fl. 3 ...), doublings, page look |
| Avatar 1m1R / 2m2r / 3m2 / 4m4-5R | `James  Horner - Avatar (Complete) [E].pdf` pages 1-12 / 100-108 / 140-173 / 243-257 ([index](../../research/avatar-pdf-index.txt)) | horn/trumpet/trombone players, instruments, notes |
| The Thing 1m02 | `Score PDFs\THG_1m02_(B)_BR.pdf` | general |

Known gaps (not converted yet): custom lines, harmonics, tab slides, measured tremolos, metric modulations
("h = q"), film timings, chord
symbols, lyrics, repeats/endings, percussion kits, Finale's page text (titles showed as "Title Insert"
or similar where Finale used placeholders).

## Results

| File | Result |
|---|---|
| | |
