# Round 4 results (2026-10-26)

- 01/02 ties test: looks good (forced ties shown as Finale wrote them).
- Willow: good overall; Oboe 1 / Trumpet 1 match the other woodwind/trumpet phrases in bar 1 but
  their crescendo "hangs over" and isn't linked (a Finale artifact worth compensating for).
- `ref-ties.dorico` (kept here): two forced tied crotchets are **one note
  of duration 2 with `kNoteSplitDurations` = `list: {string: "1"}, {string: "1"}`**, exactly the
  writer's encoding. An unforced note has no property. ✅

Fix (Round 5): hairpin ends snap forward to the end of the note they fall inside
(`FactsReader._snap_end`); grouping trims a hairpin that overhangs the next item by ≤ ½ beat
(`Options.dynamic_group_overlap`). Willow: 83 linked groups (was 55).
