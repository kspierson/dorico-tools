# Round 9 results (2026-10-28): extras reference + percussion kit example

`ref-extras.dorico` (user's file from `experiments/round9/`; decoded copy in `ref/`, git-ignored).

| Item (in score order) | Encoding |
|---|---|
| fz, ffz | `ForceDynamicDefinition` `kForceDynamicFz`, `intensityLevel` 1 / 2 |
| rfz, rffz | `kForceDynamicRfz` 1 / 2 |
| sfz, sffz | `kForceDynamicSfz` 1 / 2 |
| mfz | `kForceDynamicMfz` 1 |
| subito mf-mp | `CombinedDynamicDefinition` `direction` kDown, `startIntensity` 0, `endIntensity` 0, `commonDef/subito` true. Intensities count letters (f = 1, p = 1, mf/mp = 0), as fp = kDown 1/1 |
| cresc. from niente + dim. to niente | Dorico joined them into one `GradualChangeDynamicDefinition` `type` kMessaDiVoce, `direction` kGradualDynamicUp, `duration` 7, `hasNiente` true |
| breath marks | global `PauseEventDefinition`, `pauseType` kBreathMark, `breathMarkAppearance` kComma / kTick / kUpBow / kSalzedo; at the **end** of the note it follows |
| caesura | `pauseType` kCaesura, `caesuraAppearance` kNormal (4 other styles exist; names not seen) |

Implemented: ffz, rffz, mf-mp family (+ inferred mfp/fmp/mpf/pmf/mp-mf), subito, niente hairpins
(Finale niente glyph at a hairpin's open end), breath marks (4 styles), caesuras.

## `ref-extras2.dorico` (two players; copy here)

| Item | Encoding |
|---|---|
| sf | `ForceDynamicDefinition` `kForceDynamicSfz` level 1 with property `kDynamicRinforzandoAndSforzandoHaveZ` = "false" (plus `kEventSecondaryPosition` "0"). rf / sff / rff are written the same way by analogy (not seen) |
| staff-only breath mark / curlew | the same `PauseEventDefinition`, in that staff's **kInstrumentStaveStream** block instead of the global stream (breath mark at 3 on each staff's stream; a curlew at 28 on the first staff only) |
| caesura styles | `caesuraAppearance` kNormal, kThick, kShort, kCurved, kSingleStroke (global) |
| fermata styles | `fermataDuration` kVeryShort, kShort, kNormal, kLong, kVeryLong, kShortHenze, kLongHenze (the fourth sign in the file is a second kShort, entered by mistake; the eighth sign is the curlew, `pauseType` kCurlew with no appearance field). Fermatas sit at the note's start |

Implemented: sf/rf/sff/rff; breath marks and caesuras on only some playing staves go into those
staves' streams (all playing staves -> global, as before); Finale's caesura glyphs map to the five
styles; Finale fermata glyphs (fermataVeryShort ... fermataLongHenze, curlew) keep their style
(the most common style at a position wins, since Dorico's fermatas are one global event).

## Percussion kit: `BLACK LABEL - short.dorico` (user's project, read-only)

- **Library**: `library/percussionKitDefinitionCollectionDefinition` (kit templates, e.g.
  `kit-definition.kit.cowbells`), `library/instruments/.../percussionKitDefinitionID`,
  `percussionInstrumentDataID`, `drumKitNoteMapDefinitions` (playback maps).
- **Player** (e.g. "Drum Set & Suspended Cymbal"): one kit instrument (`instrument.kit.drum.set`,
  5-line stave, `clef.percussion`) with `percussionKit/kitDefinition`:
  `isDrumkit`, `presentationHint` kFiveLineStave / kGrid, and one `percussionKitComponent` per
  drum: `instrumentEntityID` (e.g. `instrument.orchestral.unpitched.snare.drum`),
  `instrumentOrder`, `stavePosition` (0 = middle line; snare 1, kick -3, hi-hat 5, crash 6),
  `destinationVoiceDirection` kUp/kDown, `destinationVoiceIndex`, optional
  `ptNoteheadOverrides` (pt.natural -> noteheadset.triangleUpNoteheads).
  `kitComponentInstrumentIDs` links each component to a full instrument **in the same player**
  (single-line stave, `percussionInstrumentData/playingTechniquePresentations`: pt.natural ->
  noteheadset.Xnoteheads etc.).
- **Flow**: the kit's `flowPlayerInstrument` has `percussionKitVoiceEventStreamMap` (kUp/kDown
  x voiceIndex 0/-1 -> four voice streams, all empty) and the kit stave stream (dynamics live
  there). Each component has its own stave stream and voice stream, and **the notes are in the
  component's voice stream at pitch 71 (B4)**, with `PlayingTechniqueEventDefinition`s
  (`pta.unpitchedOpen` for open hi-hat) at the note.
- **Finale side** (musxdom): `Entry::calcPercussionNoteInfo()` per note -> `PercussionNoteInfo`
  (note type id, staff position, noteheads) -> `percussion::PercussionNoteType` (name, General
  MIDI number, default staff position). Enough to map each Finale percussion note to a Dorico
  kit component.
