# Round 2 results (2026-10-26)

| File | Result |
|---|---|
| 01a (version fix only) | No noteheads |
| 01b (+ seed library) | Noteheads ✅ |
| 01c (+ seed options) | No noteheads |
| 01d (+ both) | Noteheads ✅ |
| 07 grouped | Grouping looks good; user agreed the end of the piece should be grouped too and re-saved it with the expected grouping: `07-hairpins-horn-grouped.dorico` |
| 08, 09, 10 | Look good (articulations, slurs, pick-up) |
| version message | Gone (not reported) |

User files kept here: `ref-pickup.dorico` (File > New, Flute, 3/4 with 1-beat pick-up; also
serves as the "new project" reference) and the re-saved 07.

Findings:
- **The project library is what makes noteheads (and double-click) work**, not options.
- **Pick-up** confirmed: `BarDivisionElementDefinition/barDivisionData/irregularBarLength` =
  pick-up length in crotchets (1 for a crotchet pick-up), on the bar-1 BarDivision event.
- **New-project library**: 2,833 entities (9 notehead sets, 31 noteheads, 819 glyphs, 1,150
  composites, 54 font styles, 29 paragraph styles, 43 playing techniques, ...). All exist in the
  install's factory XML files (`glyphs.xml`, `composites.xml`, `scorelibrary.xml`, ...); most
  are identical, the rest differ in font-metric details Dorico recomputes (e.g. Bravura stem
  offsets) and a few defaults. → `f2d/dorico/library.py` builds the same set from the install.
- **Grouping with gaps**: the user grouped mp + a cresc starting one beat later + the dynamic
  and dim at its end. Writer now allows gaps up to `Options.dynamic_group_gap` (1 crotchet).
- **Linked dynamics** (from the user's ET / Rite projects): identical dynamic groups on several
  staves share one `DynamicGroupElementDefinition` whose `referencingEventIDs` lists each
  staff's event (`735,30682,30731,30633`); each staff keeps its own event at the same position.
