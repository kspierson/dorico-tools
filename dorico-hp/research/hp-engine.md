# Finale Human Playback engine: what the decompiled code shows

Source: Ghidra 12.2 decompile of Finale 26 `Finale.exe` (image base 0x140000000).
Exports live in `~/tools/ghidra-out` (seeded by class tables) and `~/tools/ghidra-hp`
(every function in 0x1401a0000–0x140230000). Function names below are Ghidra's
`FUN_<address>`; the descriptive names are ours.

## Style settings record

A style's settings sit in one 36-byte record (the pipeline reads it at `this + 0x1a8`):
`+0` u16 flags A, `+2` u16 flags B, `+4` rhythmicFeel, `+6` rhythmicAccents, `+8` rubato,
`+10` reverb, `+12` selectedPreset, `+14` swing, `+16` mood, `+18..35` unused (zero in all presets).
Flags A bits: 2 pedalMarkings, 3 slurs, 4 hairpins, 5 gliss/bends, 6 acc./rall. text,
7 fermatas, 9 final bars, 15 ornaments. Flags B bits: 0 short syncopations, 1 automatic
pedalling, 2 automatic panning, 3 string harmonics, 4 adjust dotted 8th, 5 (adjust) longer,
6 baroque ornaments, 7 automatic espressivo, 8 detect accompaniment, 9 chord balance,
10 soften basses, 11 detect solo, 12 Viennese waltz, 13 cadences, 14 strum chords,
15 exact drum rolls.
`FUN_1403d14b0` saves it under the names in `FUN_1403cf330`, which gives this map of
reader function → setting:

| Reader | Setting | Reader | Setting |
|---|---|---|---|
| 1401a3020 | selectedPreset | 1401a4440 | adjustDottedEighth |
| 1401a4550 | pedalMarkings | 1401a4450 | adjustLonger |
| 1401a4540 | interpretSlurs | 1401a4490 | baroqueStyle |
| 1401a4520 | interpretHairpins | 1401a4470 | automaticEspressivo |
| 1401a4510 | interpretGlissandiAndBends | 1401a44a0 | detectAccompaniment |
| 1401a44d0 | interpretAccRallTexts | 1401a4430 | adjustChordBalance |
| 1401a44f0 | interpretFermatas | 1401a4560 | softenBasses |
| 1401a4500 | interpretFinalBars | 1401a4460 | autoDetectSolo |
| 1401a4530 | interpretOrnaments | 1401a45d0 | vienneseWaltzFeel |
| 1401a44b0 | emphasizeShortSyncops | 1401a44e0 | interpretCadences |
| 1401a4480 | automaticPedaling | 1401a4580 | strumChords |
| 1401a42e0 | automaticPanning | 1401a44c0 | exactDrumRolls |
| 1401a4570 | stringHarmonics | | |

Amounts (16-bit values): `1401a4370` rhythmicFeel, `1401a4360` rhythmicAccents,
`1401a4380` rubato, `1401a4350` reverb, `1401a3050` swing, `1401a42f0` mood.

Style numbers (`FUN_1401a4fd0` name table at 0x141482480): 1 None, 2 Classical, 3 Romantic,
4 Baroque, 5 Jazz, 6 Rock, 7 Blues, 8 21st Century, 9 Custom, 10 Light waltz, 11 Viennese waltz,
12 Latin, 13 Samba, 14 Funk, 15 Ballad, 16 Reggae, 17 Pop, 18 Standard, 19 Marching band.

## Built-in style presets

Table at VA 0x14147ec10, 36-byte records indexed by style − 1; `FUN_1401a45e0` copies the
chosen preset into the active record (Custom, 9, keeps the document's own values).
Extracted by `tools/finale_presets.py` → `research/hp-presets.tsv`. Swing "current" = −1
(use the document's swing setting); 768 is in EDUs (1024 per crotchet).

| Style (#) | Feel | Accents | Rubato | Swing | Mood | Reverb | Ped marks | Slurs | Hairpins | Gliss | Acc/Rall | Ferm | Final bars | Orn | Syncop | Auto ped | Auto pan | Harm | Dotted 8th | (longer) | Baroque orn | Espressivo | Accomp | Chord bal | Soft bass | Solo | Viennese | Cadences | Strum | Drum rolls |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Standard (18) | 25 | 25 | 5 |  | 5 | 60 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  | ✓ |  |  |  | ✓ | ✓ |  |  | ✓ | ✓ | ✓ | ✓ | ✓ |  | ✓ |  |  |
| Baroque (4) | 30 | 30 | 10 |  | 10 | 60 |  | ✓ | ✓ |  | ✓ | ✓ | ✓ | ✓ |  |  |  |  | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  |  | ✓ |  |
| Classical (2) | 45 | 25 | 10 |  | 5 | 60 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  |  |  | ✓ | ✓ |  |  | ✓ | ✓ | ✓ | ✓ | ✓ |  |  | ✓ |  |
| Romantic (3) | 49 | 35 | 40 |  | 15 | 70 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  | ✓ |  | ✓ | ✓ |  |  | ✓ | ✓ | ✓ | ✓ | ✓ |  | ✓ | ✓ |  |
| 21st Century (8) | 25 | 25 | 5 |  | 5 | 58 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  | ✓ |  | ✓ |  |  |  | ✓ | ✓ | ✓ |  | ✓ |  |  | ✓ |  |
| Marching band (19) | 10 | 80 | 3 | current | 3 | 70 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  | ✓ |  | ✓ |  |  |  |  |  | ✓ |  | ✓ |  | ✓ |  |  |  | ✓ |
| Viennese waltz (11) | 55 | 35 | 40 |  | 10 | 70 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  | ✓ |  |  | ✓ |  |  | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  |  |
| Light waltz (10) | 45 | 25 | 4 |  | 5 | 70 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  | ✓ |  |  | ✓ |  |  | ✓ | ✓ | ✓ | ✓ | ✓ |  | ✓ |  |  |
| Funk (14) | 15 | 75 | 3 |  | 5 | 29 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  | ✓ | ✓ |  |  | ✓ |  |  |  | ✓ |  | ✓ |  |  |  | ✓ |  |  |
| Jazz (5) | 25 | 70 | 5 | current | 15 | 60 |  | ✓ | ✓ | ✓ | ✓ | ✓ |  | ✓ | ✓ |  | ✓ |  |  |  |  | ✓ |  | ✓ |  | ✓ |  |  |  |  |
| Latin (12) | 7 | 85 | 0 |  | 5 | 27 |  | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  |  |  | ✓ |  |  |  | ✓ |  | ✓ |  | ✓ |  |  |  |  |
| Pop (17) | 25 | 30 | 10 |  | 15 | 60 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  | ✓ |  | ✓ |  |  |  | ✓ | ✓ | ✓ |  | ✓ |  | ✓ |  |  |
| Reggae (16) | 40 | 50 | 5 | 768 | 15 | 70 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  | ✓ |  | ✓ |  | ✓ |  |  |  | ✓ |  | ✓ |  | ✓ |  | ✓ |  |  |
| Rock (6) | 10 | 90 | 0 | current | 10 | 60 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  | ✓ |  |  |  |  |  | ✓ |  | ✓ |  | ✓ |  |  |  |  |
| Samba (13) | 50 | 50 | 5 | 768 | 8 | 60 |  | ✓ | ✓ | ✓ | ✓ | ✓ |  | ✓ |  | ✓ |  | ✓ |  |  |  | ✓ |  | ✓ |  | ✓ |  |  |  |  |
| Blues (7, →18) | 25 | 25 | 5 |  | 5 | 50 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  | ✓ |  |  |  | ✓ | ✓ |  |  | ✓ | ✓ | ✓ | ✓ | ✓ |  | ✓ | ✓ |  |
| 15 (empty) |
| None (1) | 0 | 0 | 0 |  | 0 | 0 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

Blues has no preset of its own (its record points at Standard, with reverb 50); Ballad
(15) is empty, so it isn't offered in the menu.

## Pipeline: `FUN_1401eec90`

Runs once per playback/apply, after the score has been read into the engine's own
structures. In order (a setting in brackets means the pass only runs when it's on):

1. `FUN_1401c5a90` setup; [automaticEspressivo + an instrument flag] `FUN_1401c9340`
2. `FUN_1401f91c0`; per-measure tempo setup (`FUN_1401c0d70`, default 0x78 = 120)
3. [interpretFermatas] `FUN_1401e5ac0`
4. [interpretAccRallTexts] `FUN_1401f4e90`: rit./accel. text
5. [interpretFinalBars] `FUN_1401e6340`
6. [interpretCadences] `FUN_1401e8090`
7. per-measure values collected (`FUN_1401dd110`)
8. [detectAccompaniment, when the score has accompaniment] `FUN_1401cd3c0`
9. [pedalMarkings] `FUN_1401ee450`
10. [automaticPedaling] `FUN_1401cbaa0`
11. **`FUN_1401e85b0`** (24 KB, always runs): main note interpretation
12. [interpretGlissandiAndBends] `FUN_1401e69b0`
13. `FUN_1401f3040`, `FUN_1401fd860`, `FUN_1401fc600` (always)
14. [swing ≠ 0 and a document condition] `FUN_1401cc9d0`
15. `FUN_1401f29b0`; [strumChords] `FUN_1401f33d0`; `FUN_1401fdc70`
16. [interpretHairpins] `FUN_1401e5510`; `FUN_1401c2a20`
17. [adjustDottedEighth] `FUN_1401c3bf0`
18. `FUN_1401d45b0`, `FUN_1401d48c0`, `FUN_1401c6100`: write note data and
    continuous data (CCs)

Next: read each pass, and the Garritan
solo-strings vibrato code (`garritanSoloStringsAutoVibrato`).

## Findings from the captures

- **Dynamic levels come from the expression's playback value, not its text.** Finale's
  default dynamics carry `playType amplitude` + `value` (key velocity): pppp 10, ppp 23,
  pp 36, p 49, mp 62, mf 75, f 88, ff 101, fff 114, ffff 127. MusicXML-imported dynamics
  without `<sound dynamics>` have no value, and HP then ignores the level (first capture
  run, kept in `captures/finale-hp-v1-no-dynamic-values`). sfz/fp/fz *are* recognised
  without a value, by text (the `sfz`/`fp`/`fpp` entries of the expression dictionary).
- **Articulation lengths and accents are not HP.** Staccato 40 %, staccatissimo 30 %,
  portato 75 %, accent +16 velocity, marcato +0 are identical with HP off ("none") and in
  every style: they come from Finale's articulation definitions.
- **Slurs (HP):** unslurred quavers 90 % length, notes inside a slur 109 % (overlap into
  the next note), the last note of a slur 88–92 %. Same in every style.
- **Tempo words (HP):** rit./rall. slow by about 20 % of the tempo per bar, continuing
  until "a tempo"; accel. speeds up about 13 % per bar; poco rit. about 15 % per bar.
  A fermata (minim) plays about 2× its written length, with the tempo dropping to ~42 bpm.
  A breath mark shortens the note before it to ~49 % (75 % without HP).
- **Beat accents (HP):** velocity order beat 1 > 3 > 2 = 4, scaled by rhythmicAccents
  (Rock 102/90/96/90 at mf, Standard 83/79/81/79). Funk and Jazz (short syncopations on)
  invert it: off-beats louder.
- **Rhythmic feel (HP):** later onsets on weaker beats, scaled by rhythmicFeel
  (Romantic beat 2 ≈ +35 ms, Standard ≈ +18 ms, Rock ≈ +7 ms).

### Second capture run (with dynamic values), styles 00–07

Full tables: `research/hp-measurements.md` (regenerate with `tools/style_report.py`).

- **Sustaining instruments (violin): the level goes to CC11, velocity is squeezed high.**
  CC11 per level is the same in every style: ppp 25, pp 35, p 44, mp 54, mf 65, f 77,
  ff 91, fff 105 (each bar ramps slightly towards the next level). Velocity follows a
  concave curve, Standard ppp 85 → pp 94 → p 102 → mp 109 → mf 114 → f 118 → ff 120 →
  fff 121; other styles add a small offset (Baroque/Romantic/Viennese +2, Marching +7).
  So HP treats velocity on strings as attack strength, not loudness.
- **Piano: velocity only, no CC11.** Velocity = the marking's key velocity plus a style
  offset (Standard +3, Romantic +4, Marching +10), i.e. the average beat accent.
- **Unmarked music is not "mf at 65".** 01-baseline (no dynamic) plays at CC11 ≈ 92–95
  with velocity ≈ 89–93: HP's "no marking" level is louder than its mf.
- **Accent** is +19 velocity in every style including none (Finale articulation, not HP).
- **Hairpins** now start from the level's CC11 (p ≈ 55–57) and end at the target
  (f ≈ 102–107); the curve is slow at both ends and steepest in the middle (S-shape),
  ~370–420 CC11 events per piece. Romantic/Viennese/Baroque stop a few points short.
- **Tempo words, fermata, breath, slurs:** unchanged from the first run (dynamics did
  not affect them).
- **Rubato:** only Romantic and Viennese waltz vary tempo inside a phrase (Ode 78–100
  bpm, 21 tempo events). Baroque/Classical/21st-century reach 78–80 bpm only at the
  final bar (finalBars ritardando).
- **Marching band:** strongest beat accent (beat 1 +11 over beat 2), tightest timing
  (beat 2 only +7 ms).

### Second capture run, styles 08–15 and the user's scores

- **No swing on straight quavers in any style.** Jazz/Rock/Marching (swing −1) and
  Samba/Reggae (swing 768) play the 19-jazz quavers straight (off-beats only 3–6 ms
  later). −1 probably means "use the score's swing setting"; 768 is still unexplained
  (maybe semiquaver swing, or only with a swing text/tempo marking). Needs a test piece
  with a "Swing" marking and semiquavers.
- **Weak-beat delay grows with rhythmicFeel:** quaver onsets across a 4/4 bar are delayed
  by roughly 0.8 ms × rhythmicFeel at their peak (Latin 7 → 5 ms, Funk 15 → 12 ms,
  Standard 25 → 20 ms, Samba 50 → 40 ms), largest just after the downbeat and shrinking
  towards the barline.
- **Beat accents grow with rhythmicAccents:** Rock (90) beat 1/2/3/4 = 110/98/104/98,
  Latin (85) 108/96/102/96; Funk and Jazz (short syncopations on) make beats 2 and 4
  louder than 1 and 3.
- **Funk plays strings ~12 % quieter in CC11** (fff 93, hairpin top 91 vs 102–107).
  Funk is the only style with autoDetectSolo off, so autoDetectSolo probably lifts a
  detected solo line. Pop's hairpins also top out lower (95) – unexplained yet.
- **Slurred notes are softer in syncopation styles:** slurred minus unslurred velocity is
  −9/−10 in Jazz/Funk vs −1/−2 elsewhere (the off-beat emphasis applies to tongued notes).
- **Small CC11 constant on unmarked music** (Ode 89–95) in every style: HP does not phrase
  dynamics on its own – no arching. Velocity sd stays 2–6.
- **User scores** (`captures/finale-hp/scores-none`, `scores-own-style`): VV_Full and
  Venus use Romantic, WW 21st Century, Willow Standard, Trex Custom. With HP on, VV_Full
  gains 1,523 notes and Willow 1,266 (trills, tremolos, glissandos written out), and
  thousands of CC events. **Trex exports only 2 staves** because nearly every staff has
  `playbackRouteNum -1` (no device); its two routes point to "Kontakt 5".

### HP dynamics are relative to the piece, not a fixed table

Median CC11 per marking (Standard, solo string/wind test pieces, notes outside hairpins):

| markings in the piece | CC11 |
|---|---|
| mf only (baseline, articulations, slurs, Ode…) | mf 87–95 |
| p only (Amazing Grace) | p 73 |
| p, mf, f (14-long-notes) | p 73, mf 78–80, f 94–96 |
| p, f (06-hairpins) | p 56, f 105–107 |
| ppp … fff (05-dynamics) | 27, 35, 44, 54, 65, 77, 91, 105 |

So the same marking gives very different levels: mf is 65 in a piece that spans ppp–fff
but ~90 when it is the only dynamic. HP evidently scales levels to the dynamics actually
used (and probably boosts a detected solo line, cf. autoDetectSolo/Funk). Consequence for
the rebuild: don't copy HP's numbers as an absolute table. Dorico maps each marking to a
fixed level through the expression map's range; the per-library profile and section
balance decide the rest. A piece-relative "use the whole range" option could be a profile
setting later.

### "The Last Temptation" (user score + HP MIDI): automatic espressivo, harp

`HPCaptures\finale\last\the last temptation.musx/.mid`. Custom style: rhythmicFeel 45,
rhythmicAccents 40, rubato 65, mood 76, espressivo/solo/accompaniment/chord balance/soften
basses/cadences/strum on. Solo violin + cello (Garritan in Kontakt 3, dynamics *and*
vibrato on CC1), string section, harp. Tempo 33–120 bpm across 30 tempo events (rubato).

**Automatic espressivo = a swell on every long note** (CC1 at 21 points through each note,
notes not under a written hairpin, all string tracks):

| written length | notes | swelled | mean rise when swelled | peak position |
|---|---|---|---|---|
| ≤ 1 crotchet (any ms, up to ~1.4 s) | 394 | 24 | 5–22 | — |
| 1.15 – 2 crotchets | ~150 | ~all | ≈ 22 | ~0.5 of the note |
| 3 – 8 crotchets | ~120 | ~all | 23–25 | 0.4–0.47 |

- The threshold is in **beats** (just over one crotchet), not milliseconds: 1.2 s crotchets
  stay flat, 2.1 s minims swell.
- Shape: flat start, rise to a peak a little before the middle, back down to ~2–4 below the
  starting level at the end (an arch per note).
- Depth ≈ 22–25 CC1 at mood 76; Standard (mood 5) shows no swell on Ode's minims, so depth
  scales with **mood**. Less rise when the note already starts high (start ≥ 60: mean
  rise 3) – headroom.
- Same on solo and section strings.
This is the "held-note swell" the user also added by hand in playback copies.

**Harp:**
- Chords are rolled starting *before* the beat: the lowest 2–3 notes fall up to ~0.2
  crotchet early, the rest after; spacing 20–170 ms (varies with tempo/dynamic; not
  analysed further). Dorico equivalent: `arpeggioPlaybackOptions.playbackPosition`
  (starts on / ends on the beat) – HP straddles it.
- **Glissando cells are extrapolated:** bars 40–41 notate a 7-note pedal-tuning cell in
  1/32 notes (two strands) and play 57–104 notes: the cell repeated up through the range,
  evenly spaced (bar 41) or accelerating (bar 40, 0.29 → 0.03 crotchet apart). Matches
  the user's description (cell + hidden rest/extended beam; works here without them).
  Apply can't add notes (playback-only data), so in Dorico this is a job for Dorico's own
  harp glissando playback, which follows harp pedal settings; the rebuild should at most
  check that pedals are set where a gliss is.
- A fast group in bar 10 plays ~0.47 crotchet earlier than written (leads into the next
  note) – not explained yet.

**Vibrato note (user):** Garritan solo strings tie vibrato to CC1; SWAM separates it
(own CCs) and SWAM brass "lip trill" at the top of the vibrato range → per-library
vibrato profiles need a maximum depth.
