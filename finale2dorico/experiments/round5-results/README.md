# Round 5 results (2026-10-27)

User reviewed 12 and made **13-willow-full.dorico** (kept here):
manual dynamic-group adjustments, playing techniques, trills, tremolos, glissandi, extra horn
players. Mostly from the performance PDF; some "in the moment"; not complete across the score.
Use as symbolic reference, not ground truth for every bar.

User guidance:
- Dorico is player-based; Finale staff-based. Condensed Finale staves (e.g. Horn 1/2 or 1/3 in
  layers) must be exploded into the right players/instruments; ideally doublings too (Fl 1 doubling
  Picc, "Broadway" Wind 1 with several instruments).
- Wants complementary utilities (score "cleaner", score "editor").

## What 13 shows (12 vs 13)

| Item | Encoding / finding |
|---|---|
| Horns | Players Horn 3 and 4 added, ordered Hn 1, Hn 3, Hn 2, Hn 4 (pairs from each Finale staff kept together); music not yet moved (still in Horn 1/2 voice 2). Finale marks single lines "a2" / "º1" / "º2" (= 1. / 2.). |
| Trill | `TrillEventDefinition` in the voice stream, duration = trilled span; `kTrillInterval` = `list: {string: "1/12"}, {int: 1}` (semitone; fraction of an octave in 12-EDO, 1 diatonic step); absent = Dorico default. In Finale: `trill` shapes and custom lines (char 126 wavy + start text "tr" (Maestro 217) + small ♭ (105)). |
| Glissando | `GlissandoLineEventDefinition` (voice stream) with `fromNoteEventAndBlockInstanceIDs` / `toNoteEventAndBlockInstanceIDs` = (note event ID, block instance ID), may cross voices/staves; `kGlissandoLineType` `kFlatLine` (user's choice for harp). |
| Mute | `PlayingTechniqueEventDefinition` (voice stream, duration 0): `appearanceEntityID` `pta.straightMuteText`, `appearanceType` `kGlyph`, empty `data`. |
| Tremolo | Note property `kNoteSingleStemTremolo` = `string: "list: {int: 3}, {bool: false}"`. Finale: articulation glyphs Maestro 33/64/190 = 1/2/3 strokes. |
| fp | `CombinedDynamicDefinition`: `direction` kDown, `startIntensity` 1, `endIntensity` 1. Was dropped by our writer (unsupported). |
| sfz in a group | `ForceDynamicDefinition` with relative `position`. User projects: Sfz levels 1 and 2 (sffz). |
| Dynamics | 26 players changed: fp added (bar 1, low instruments); duplicate hairpins removed (from Finale duplicates: Horn 1 ×3 at 169, Violins ×2 at 179); groups merged across gaps where the instrument keeps playing (Horn 187, Bass Cl 81); a few splits/edits "in the moment" (Cl 1 at 2, Tpt 1/3 at 191); hairpin starts unified across section players (Tbn 2/3 + Vla, Vln 1/2) so they link; the barline ff removed in Bass Cl (kept in Cbsn). |
| Accidentals | Our 4 `kNoteAccidentalVisibility` were dropped by Dorico: native files write `kNoteAccidentalVisibility_v3` too. |

Fixes made (Round 6): explode shared staves (`f2d/explode.py`); trills/glissandi/tremolos/
techniques/fp/sffz; hairpin de-duplication; grouping across continuous sound; accidental _v3;
grace notes before rests kept in place; player numbers taken from the source ("Horn 3").
Not reproduced (judgment calls): hairpin-start unification across sections, individual splits.
