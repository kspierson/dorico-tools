# Experiments: Dorico test rounds

Each round is a set of generated `.dorico` files you open in Dorico, with a checklist. Results,
and any files you made or saved in Dorico, are kept in `roundN-results/` (the important
references); old checklists are archived in `history/`.

**Current round:** [round10/](round10/README.md) (with PDFs exported by Dorico; supersedes round 8); previously [round6/](round6/README.md) (the five real scores; regenerate with
`python3 experiments/make_round6.py`, which also writes converter reports; reviews with
`python3 -m f2d review round6/X.dorico`).

| Round | What it settled | Results / your files |
|---|---|---|
| 1 | Dorico opens generated files; wrong fileVersion; minimal library = no noteheads; default playback template = yours | [round1-results](round1-results/README.md): `07-saved-by-dorico.dorico` (your dynamic grouping) |
| 2 | The project library is what makes noteheads work; pick-up encoding; grouping rule | [round2-results](round2-results/README.md): `ref-pickup.dorico` (new-project reference), `07-hairpins-horn-grouped.dorico` |
| 3 | Install-built library works; linking too broad | [round3-results](round3-results/README.md) |
| 4 | Forced ties encoding; stricter linking | [round4-results](round4-results/README.md): `ref-ties.dorico` |
| 5 | Your hand-edited Willow: trills, glissandi, techniques, tremolos, fp, horn players, grouping | [round5-results](round5-results/README.md): `13-willow-full.dorico` (main reference) |
| 6 | All five real scores; shared staves -> players; reviewer | [round6](round6/README.md) (superseded by 8) |
| 7 | Reference file for chord symbols, lyrics, repeats, tempo range, staff-only time signature | [round7](round7/README.md); results: [round7-results](round7-results/README.md) ✅ |
| 8 | Tempo, text, ottava fix, doublings, harp pedals; nine scores incl. John Williams | [round8](round8/README.md) (superseded by 10) |
| 9 | Extras references (dynamics, sf, breath marks, caesura and fermata styles, staff-only pauses) + BLACK LABEL kit | [round9-results](round9-results/README.md): `ref-extras.dorico`, `ref-extras2.dorico` ✅ |
| 10 | Page setup, chord-written pairs split, standard instruments, clean E.T., Avatar cues; PDFs via Dorico remote control | [round10](round10/README.md) (in progress) |
| 11 | Chord symbol variants and lyric syllables (hyphens, extenders, verse/chorus) | [round11](round11/README.md) ✅ |
| 12 | Harmonics, two-note tremolos, lines with text and hooks, technique transitions, metric modulation, boxed text | [round12](round12/README.md) done 2026-10-31 |

Used by tests/tools: `round2-results/ref-pickup.dorico` (`tests/test_review.py`;
`research/tools/extract_new_project_ids.py` builds `f2d/data/new_project_library.json` from it).

`cleaner/`: first cleaner output to check in Dorico (Willow before/after + list of changes; docs/CLEANER.md).
