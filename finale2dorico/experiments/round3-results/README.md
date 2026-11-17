# Round 3 results (2026-10-26)

| File | Result |
|---|---|
| 01, 05-10 | Look good (install-built library works: noteheads, no crash reported) |
| 03 | Rhythms as expected; no ties/slurs (source has none) |
| 04 | No visible difference from 03 (Dorico's default notation already matches) |
| 05 | Three mf (bar 1 both staves, bar 5 upper): matches the source |
| 12 Willow | Renders correctly; linked dynamics decent but too broad (Cl/Hn linked with trumpets/woodwinds at the start; would link only Cl/Hn). "Extra" items (bass clarinet ff linked to contrabassoon, clashing with an mp): from Finale's data; keep rather than make editing decisions |

User decisions:
- Linking should be "somewhat strict": link what would condense together (same phrase/rhythm).
  → `link_dynamics="rhythm"` (default): identical groups + same note onsets/lengths over the
  group span and at least to the end of the bar.
- Shared modules: document duplicates; aim for one real shared engine in the best language,
  respecting dorigit's Rust. → docs/SHARED_ENGINE.md (proposal, awaiting decisions).

Findings:
- Native Dorico files use `kNoteSplitDurations` only as a single value equal to the note's
  duration (4,002 instances in the user's projects): "force this note's displayed duration".
  How forced *ties* are stored is still unknown (Round 4 asks for ref-ties.dorico).
- Willow bar 1: the ff is placed exactly on the barline (eduPosition = bar length); bar 2 has mp.
- 18 hidden dynamics in Willow (Finale `<hidden/>` on measExprAssign) are now skipped.
- Measure-attached hairpins/dynamics carry raw click positions; now snapped to the nearest note
  onset (within half a crotchet) or the semiquaver grid.
