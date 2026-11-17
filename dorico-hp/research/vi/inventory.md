# VI inventory (Project C, step 1)

Read 2026-11-01 from the projects' `enginedata` with `doricokit.virender.plugin_states` and the
maps with `doricohp.playback` (slot numbers below are Dorico's `pluginRackContents` slotIDs =
enginedata slot − 1).

## Across all 340 projects in Dorico Projects (instrument plug-ins)

Kontakt (VST2, `Native Instruments\VSTPlugins 64 bit\Kontakt.dll`) 3,261 instances in 238 projects;
SWAM Woodwinds 2.8 (VST2) in ~180; Pianoteq 6 STAGE (VST2) 193; Kontakt 7 (**VST3** only) 243 in 22
(the newer template); SWAM Strings 3 (VST2) 30–36; SWAM Alto/Bass Flute 25; SWAM Soprano Sax 12;
SWAM Euphonium 6; DX7 V, Dexed, Padshop, Retrologue (synths).

## Two reference setups

**Full Orchestra Template NEW FULL v5** (Kontakt 7 VST3, multi-timbral, one map per channel):

| Slot | Patches | Maps |
|---|---|---|
| 1 | AV Infinite Woodwinds Flute, Piccolo | IW - Flute ×3, IW - Piccolo |
| 2 | IW Oboe, English Horn | IW - Oboe ×3, IW - English Horn |
| 3 | AV Infinite Brass Euphonium | IB - Tuba ×2 |
| 4 | IW Clarinet, Eb Clarinet | IW - Clarinet ×4 |
| 5 | IW Bass Clarinet, Contrabass Clarinet | IW - Bass Clarinet ×2 |
| 6 | IW Bassoon, Contrabassoon (+ saxes on 2–3) | IW - Bassoon, IW - Saxophones ×2, IW - Contrabassoon |
| 7 | IB French Horn | IB - Horns ×6 |
| 8 | IB Trumpet | IB - Trumpets ×4 |
| 9 | IB Trombone, Bass Trombone | IB - Trombones ×4 |
| 10 | IB Tuba | IB - Tuba |
| 21 | IW Soprano/Alto/Tenor/Bari Sax | IW - Saxophones ×8 |
| 24 | IW Alto Flute, Bass Flute | IW - Flute ×2 |
| 11–14, 16–20, 22–23 | not named in the state (16 channels, "Default" maps: percussion/strings?) | Default |
| 15 | Pianoteq 6 STAGE | Default |

**Harry Potter Cues Plus 5 + LASS3** (SWAM VST2 + Kontakt VST2): SWAM Woodwinds 2.8 (all 8 +
alto/bass flute), SWAM Strings 3 (violin ×2, viola, cello, bass), Pianoteq ×4, and in Kontakt:
LA Scoring Strings 3 (slot 9, 6 channels), Sample Modeling brass on the SWAM brass maps (SM
Horns ×6 slot 13, SM Trumpets ×4 slot 26, SM Trombones ×4 slot 27, SM Tuba slot 28), Spitfire Harp
(slots 8, 30), Spitfire Tubular Bells (44), CinePerc / Cinesamples timpani (19, 33, 43), Joshua
Bell violin (34), and several "Default"-map instances not named in the state (5–7, 16, 20, 29, 42).
HP WW.dorico = the woodwinds of this project.

## Rendering

| Plug-in | vi-render (automatic, exact Dorico state) | Cubase |
|---|---|---|
| SWAM Strings 3, SWAM v3 brass, Pianoteq | ✅ works | – |
| SWAM Woodwinds 2.8.1 | silent (see swam.md) | kit in HPCaptures\swam |
| Kontakt (VST2) | stalls ("cannot resolve resource: resources_ENG") | needed |
| Kontakt 7 (VST3) | no VST3 hosting | needed |

Every enginedata state record is a complete `.vstpreset` (header `VST3`, class id, chunk list
`Comp`/`Cont`), also for VST2 plug-ins (Dorico's VST3 wrapper, `VstW` + fxb inside):
`PluginState.vstpreset` can be written out and loaded on the same plug-in in Cubase.

**Versions (checked 2026-11-01).** The HP project's Kontakt (VST2) states were saved by
Kontakt **6.4.0.81** (UTF-16 string near the start of the `Ni$D` chunk); this PC has Kontakt
**6.2.1** (`VSTPlugins 64 bit\Kontakt.dll`, 2019), which rejects them ("created with a newer
version"), in Cubase and presumably in Dorico too. Kontakt 7 states: saved by 7.8.1 = installed
7.8.1. This may also be why the Kontakt VST2 stalled in vi-render.

**Kontakt 6 → Kontakt 7.** The Kontakt 6 VST2 chunk and the Kontakt 7 VST3 component state are
the same NI container (u64 size + "hsin" …), so `PluginState.kontakt7_vstpreset()` wraps the VST2
chunk as a Kontakt 7 `.vstpreset` (class id "VSTNiK7kontakt 7", `make_vstpreset`; rebuilding the
template's own Kontakt 7 preset this way is byte-identical). Plan: render all HP Kontakt
instruments in Kontakt 7 in Cubase. Checked 2026-11-01: the converted Spitfire Harp state loads
and sounds the same as in Dorico (same mics). **Exception: CinePerc / Cinesamples** libraries
don't work in Kontakt 7 (old library version, per the user; may need a library update), so the
timpani/percussion slots need another route (Kontakt 6.4+ or an updated library).

**Cubase track archive** (File > Export > Selected Tracks, `<tracklist2>` XML): times in
480 ticks per quarter (`MMidiNote` Start/Length, `MMidiPartEvent` Start/Length); notes carry
Channel (0-based), Data1 pitch, Data2 velocity; `MMidiController` Data1 cc / Data2 value. A
dropped MIDI file (format 0 too) becomes one MIDI track per channel, each routed to the selected
instrument on its channel. The first sample held only such a MIDI track (42 KB, no plug-in).

**MIDI into Cubase.** A format-1 file splits into one track per MIDI track; write test MIDI with
`midi.write(..., single_track=True)` (format 0, channels kept) for multi-timbral instances.

**Getting a state into Cubase 13.** Dragging a `.vstpreset` from Explorer doesn't work. What
does: copy it into `OneDrive\Documents\VST3 Presets\<vendor>\<plug-in>\` (Documents is
redirected to OneDrive; e.g. `Native Instruments\Kontakt 7\`), then plug-in preset menu >
Load Preset. VST2: preset menu > Import FXB/FXP with `PluginState.fxb`.

## Kontakt measurement kit (2026-11-01)

`dorico-hp/tools/vi_measure.py kit --out HPCaptures\kontakt` → `hp-kontakt.xml` (15 tracks) and
`tpl-kontakt.xml` (21 tracks): one Kontakt 7 track per rack slot that players use, with that
slot's exact state (`PluginState.kontakt7_state()`) and one MIDI part testing each used channel in
turn (map init + natural switch actions first). Tests per channel from its map: CC dynamics →
E/A/B/C/D; velocity-only sustaining ("Default" maps on strings/voices) → E, A by velocity, A by
CC1 and CC11 (does the patch use them?), D; velocity-only struck/plucked → E/A; further players of
the same map on the same slot → E/A. Skipped: unpitched percussion, CinePerc slots (HP 19, 33, 43).
Longest track 32 min (template saxophones). Plans/results: `research/vi/measurements/`.

Template oddity: slot 6 (IW - Bassoons) channels 2–3 = Bassoon 2 and 3 on the **IW - Saxophones**
map, and the state has saxophone patches on those channels.
