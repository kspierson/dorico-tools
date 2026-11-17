# SWAM (Audio Modeling): how it responds, and what that means for Dorico maps and Apply

Started 2026-11-01 (dorico-hp session) with SWAM Flute; the start of the per-VI work planned in
`../../../PLANNED_WORK.md` §5 (Project C). Sources:

- **Manual**: *SWAM Woodwinds v2.8 User Manual, rev. 1* (25 pages), also installed at
  `C:\Program Files\Audio Modeling\SWAM\SWAM Woodwinds v2.8 - User Manual.pdf`
  ([online](https://support.audiomodeling.com/guides/winds/SWAM%20Woodwinds%20v2.8%20-%20User%20Manual.pdf)).
- **Factory presets**: `C:\Program Files\Audio Modeling\SWAM\<family>\<instrument>\Presets\*.swam`
  (plain XML; MIDI-mapping values decode as CC = value × 128 + 1).
- **The user's plug-in states**: Dorico stores each plug-in's state in the project, in
  `supplementary_data/vstaudioengine/enginedata` (a "MixerData" header, then XML). SWAM states
  are readable `<swam type="…">` blocks: woodwinds 2.8 = `<param name=… value=…>`; SWAM
  Strings 3 (Violin 3 …) = `<PARAM id=…>` + `<MIDIRemappingEntry parameterId=… msb=CC>`.
  Read with a throwaway script (session scratchpad `swamstate.py`); worth a proper reader
  (Project C / engine S6).

## SWAM Woodwinds 2.8 (Flute, Piccolo, Alto/Bass Flute, Oboe, Clarinets, Bassoons, Saxes)

### Controls (manual p. 9–18; the user's instances use the factory "Keyb. Cntrl" mapping)

| Control | CC | Notes |
|---|---|---|
| Expression = dynamics pp–ff | **11** | required; manual stresses keeping most playing in mp–mf |
| Vibrato depth | **1** | |
| Vibrato rate | **19** | |
| Main Volume | **14** | ← the user's maps send CC14 at start (Flute 12, Brass 50): a volume setting |
| Pan | 10 | |
| Reverb mix | **91** | maps send CC91=0 = built-in reverb off |
| Transition (legato/portamento) time | **5** | used when Transit.Time source is CC; maps send CC5=127 |
| Growl / Flutter tongue / Breath noise / Key noise | 21 / **23** / 25 / 9 | flutter → Dorico's flutter-tongue technique could drive CC23 |
| Harmonic structure / Formant / Sub-harmonics | 24 / 26 / 20 (27 on flutes) | |
| Overblow (on ≥ 64) | 64 (sustain pedal) | also keyswitch D1 (momentary), D♯1 (latch) |
| Flutes: alternate fingering / PipeSplit | 28 / 27 | also keyswitch E1 (momentary), F1 (latch) |
| Keyswitches | C1 fall, C♯1 legato mode (Expr ↔ Gliss), D1/D♯1 overblow, E1/F1 alt. fingering | "KS Oct. Transp." moves them an octave down or switches them off |

### How notes are played (manual p. 9, 11, 14–15)

- **Velocity = attack** of detached notes (and the legato transition time when Transit.Time
  = velocity). Dynamics come only from Expression. *Attack Sens.* chooses linear velocity,
  soft velocity or Expression as the attack source; *Attack-Exprs Bias* makes attack
  steepness depend on Expression; *Attack Start* trims the attack (0 = full attack).
- **Staccato / semi-legato / legato are chosen by SWAM itself** from velocity, the interval,
  and the time between note-off and the next note-on. No articulation keyswitches; the
  thresholds aren't documented. So in Dorico, "staccato" for SWAM = a short note + a firmer
  attack, which is what Apply's capped lengths and attack velocities do. Legato needs
  overlapping (or touching) notes; Apply keeps ≥ 25 ms between unslurred notes for this reason
  (found by ear, 2026-10-26).
- **Release** (note-off release time) adds a tail to every note: part of why 36 ms notes
  still sound like notes. It's a plug-in setting (`relTime` 0.5 in the user's instances).
- *Rand.Dyn* (random dynamics/pitch; user's flutes 0.18, clarinets 0.27) and *Vibrato Rand*
  are SWAM's own humanising; they stack with Dorico's humanise and Apply's timing.
- Expression = 0 at note-on: not covered by the manual (to test).

### The user's SWAM - Flute expression map (`xmap.swam.flute`)

Natural only: dynamics CC11 + velocity (1–127 / 40–127), attack = velocity; init CC14=12,
CC91=0, CC1=32, CC5=127; option overrides: notes 85 %, staccato 38 %, staccatissimo 19 %.
So Dorico has no staccato/flutter/overblow entries: written techniques reach SWAM only as
note lengths and velocities.

### HP WW.dorico: the user's woodwind section (inventory, 2026-11-01)

`C:\Users\kspie\Documents\Dorico Projects\HP WW.dorico` = the woodwinds of the HP cues,
**playback copy** (user: the balance was adjusted for playback, e.g. Quidditch m95: flutes ff in
the score → ffffff here; oboes/clarinets f → ff; the sf/sff on the low woodwinds aren't in the
score). Three flows: Rainy Nights (40 bars, ♩=80), The Rescue of Sirus (38, ♩=90), Quidditch
2004 (137, ♩=66 → 148). 17 SWAM slots, one per instrument (doubling players get one slot per
instrument). **No Play-mode edits** (no automation, no played offsets): every playback change
is notation.

**Plug-in states vs the factory "Keyb. Cntrl" presets** (read from `enginedata`, decoded with
`vi-render info/sweep`, which asks the plug-in for each parameter's display text; same edits on
every instrument, so the user set up one instrument and copied the settings):

| Parameter | User | Factory | Meaning |
|---|---|---|---|
| Main Volume CC (`mainVolumeCC`) | CC14 | CC7 (clarinets: none) | Main Volume moved to CC14 |
| Main Volume | = map's CC14 init / 127: fl 12 = **−20.5 dB**, picc 16 = −18.0, ob/EH 12 = −20.5, cl 8 = −24.0, b.cl 12 = −20.5, bn 12 = −20.5, cbn 10 = −22.1 | −3.0 dB | dB = 20·log10(CC/127). **Section balance lives in the maps' CC14 init** |
| Reverb Mix | 0 | 18 | built-in reverb off (maps also send CC91=0) |
| Attack Sens. (`attackType`) | 0.82 = **Vel Soft** | Soft (cl: Hard) | 0–0.35 Hard, 0.35–0.7 Expression, ≥0.7 Soft |
| Transit.Time (`portamentoCtrl`) | 0.82 = **CC inv** | Velocity | 0–0.34 Vel, 0.34–0.68 CC, ≥0.68 CC inverted: CC5 small = long. Maps send CC5=127 → **shortest legato transition always** |
| `rampTime` | 1.2 | 0.6 | display 0.4–1.2; meaning not in the manual (Attack to Sust Time?) |
| Expression Curve (`expressionPedal`) | **Ln 0.0** (linear) | Lg 0.5 | how CC11 maps to dynamics |
| Legato Mode | Expr | Expr (cl: Gliss) | straight legato, no portamento |
| `overblowThresh` (flutes) | 0.0 | 0.5 | unknown (Squeak→Overblow?) |
| `HarmTrans` (fl, picc) | 0.68 | 0.74 | Harm.Struct (display 0.50–1.00) |
| IR selected (fl 1–3) | "0 Flute A_1" | "1 Warm" | Instr. timbre |
| Pitch-bend range | 2.2 | 1.1 | |
| Unchanged | Rand.Dyn 7.0, vibrato rate 5.0 + rand 6.0, Release 0.10, Compressor 4.0, Attack Start 2.0, breath/key noise 64/50, Style | | |

### Measuring outside Dorico: `vi-render` (2026-11-01)

Built a headless VST2 host (`engine/crates/vi-render`, Windows exe from WSL) and
`doricokit.virender` (reads every slot's plug-in state from a project's `enginedata`, finds the
DLL, renders timed MIDI to WAV, lists parameters with display text, sweeps a parameter). Test
batteries for SWAM: `dorico-hp/tools/swam_measure.py` (A loudness vs CC11 per register, B short
notes, C velocity → attack, D gap → legato), using the project's state + the map's init CCs.

Status: the host renders Pianoteq and **SWAM Trumpet (v3)** correctly. The installed **SWAM
Woodwinds 2.8.1** renders silence in it (a non-registered build: the user owns SWAM Woodwinds
but can only install v3 here, and keeps v2 to match scores set up with v2 on the Mac; personal
use). Not worked around. **Woodwinds are rendered in Cubase instead (user, 2026-11-01).**

**Cubase kit** (`swam_measure.py kit`): `C:\Users\kspie\Documents\HPCaptures\swam\` holds
one MIDI file per woodwind (`midi\NN-<name>.mid`, tempo 120, ~9.7 min, init CCs of that
instrument's map at tick 0), the user's SWAM settings as presets (`presets\<name>.swam`, the
`<swam>` XML from HP WW) and README.txt (Cubase steps: fixed tempo 120, load preset, drop MIDI
at bar 1, channel batch export 48 kHz float to `renders\`). Plans (note times + purpose) in
`swam-measurements/<name>.plan.json`; `swam_measure.py analyse <wav> --name flute` measures a
render and checks alignment (onsets in the first vs last battery; silence before the first
note). Batteries: E range probe (every semitone ±3: sounding pitch by autocorrelation, catches
the contrabassoon's −12 transpose and key-switch collisions), A, B, C, D as above. Pipeline
checked end to end on a SWAM Trumpet render of the flute plan (alignment 10 ms both ends,
pitches exact, PCM 24-bit reader exact).

Dorico's rack numbering: `pluginRackContents` slotID = enginedata slot − 1
(`PluginState.dorico_slot`).

**Dorico side**: map `SWAM - Flute` = natural only, CC11 1–127 + velocity 40–127 (attack),
notes 85 %, staccato 38 %, staccatissimo 19 %. Project playback options: `dynamicCurveParams`
**0.5, 2.5, 2.5** (not Dorico's default), accent +0.5 and marcato +0.8 dynamic steps, beat
stress 0.3/0.2, humanise dynamics 50 % / timing 30 %. The dynamic → CC11 values that this
curve gives are not known yet (needs a MIDI export or a measurement).
*Answered 2026-11-01 (dorico-hp session, test I2 MIDI export):* pppp 5, ppp 12, pp 24, p 41,
mp 52, mf 76, f 87, ff 104, fff 116, ffff 123 (velocity on the 40–127 range: 43 … 124);
`doricokit.dynlevels` (levels −4…+4, mp −0.5, mf +0.5; accent +0.5, marcato +0.8).

**What the playback copy says about balance** (dynamics used, Quidditch): every part reaches
ffff, flutes/oboes/clarinets ffffff, bassoons sfz ×12 and fff/ffff spikes (e.g. bar 94 beat
3¾: bn 1 ffff, bn 2 fff into the ff tutti at 96). At m95 the flutes play a staccato 16th run
F5–G6 (written ff, played ffffff) against slurred 16ths in ob/cl (f → ff). Hypotheses to test:
(1) short notes never reach the CC11 level (attack ramp), so staccato needs a higher level
than legato to sound equal; (2) the dynamics curve + CC14 balance leave too little top for
tutti; (3) high flute and low reeds need register-dependent balance.

## SWAM Strings 3 (Violin, Viola, Cello, Double Bass; user's instances in the HP project)

Mapping read from the plug-in state: expression 11, vibrato depth 1, **Main Volume 14**,
pan 10, reverb mix 90, vibrato rate 19 **and bow force 19** (both on one CC), bow position 17,
play mode 20, tremolo 21, polyphony 22, alt. fingering 23, double-stop string selection 24,
harmonics 91, sustain 64. The map's init CC14=46 is therefore a volume level too.

### Measured (vi-render, HP project states + the map's start + natural actions, 2026-11-01)

`swam_measure.py render --name violin,viola,cello,double_bass`; results in
`swam-measurements/<name>.json`. **The test must send the natural technique's switch-on actions
too**: the saved Double Bass state has Play Mode = Pizzicato and only the map's natural CC20=0
makes it bowed (first run measured pizzicato).

| | Violin | Viola | Cello | Double bass |
|---|---|---|---|---|
| Sounds (MIDI as Dorico sends) | 55–101, no transposition | 48–90 | 36–78 | 26–69 |
| CC11 16→127 | 23–26 dB | 22–25 dB | 21–25 dB | 21–23 dB |
| CC11 88→127 (the top) | **only 3–4 dB** | 3–4 dB | 3–4 dB | 3 dB |
| Level at CC11 127 | −32…−39 dBFS | −34…−36 | −31…−35 | −31…−34 |
| Short notes vs 1 s note (CC11 110): 30 / 50 / 80 / 120 ms | −9…−14 / −4…−5 / −2…−3 / −2 dB | −12…−13 / −5 / −2…−3 / −1…−2 | −12…−15 / −6…−10 / −2…−5 / −1…−3 | −15…−18 / −7…−8 / −4 / −1…−2 |
| Onset / rise to −6 dB (median) | 25 / 55 ms | 25 / 65 ms | 35 / 80 ms | 50 / 80 ms |
| Velocity | no effect on onset or level (attack comes from Expression) | same | same | same |
| Gap at which the 2nd note starts from silence | ≥ 60 ms | ≥ 120 ms | > 120 ms | ≈ 120 ms |

What it means (proposals, to confirm by ear):
1. **The top of CC11 is nearly flat**: ff → ffff adds ~3 dB at most. That matches the extreme
   markings in the playback copies. The dynamics need to land in CC11 ≈ 16–100, where most of the
   change happens (map range / Dorico's dynamic curve), with balance on CC14 rather than the top
   of CC11.
2. **Short notes need time to speak**: below ~80 ms (violin/viola) or ~120 ms (cello/bass) the
   note loses level. Apply's time caps (staccato ≥ 30 ms, light passages ×0.45) are flute values;
   SWAM strings need a per-library minimum played length (≈ 80 / 120 ms).
3. **Attack latency 25–50 ms** (+ rise 55–80 ms): candidate for Apply's per-library start offset
   (or the latency-reporter look-ahead).
4. Notes with gaps under ~60–120 ms don't restart from silence (the bow keeps moving; dips of
   −5…−20 dB). Whether that reads as detaché or legato needs listening; Apply's 25 ms gap rule
   (from SWAM woodwinds) doesn't separate SWAM string notes.

## Bug found and fixed (2026-11-01)

dorico-hp's library profiles named CC14 as SWAM vibrato rate. For SWAM strings Apply wrote
rate curves on CC14 = **Main Volume** (1,456 points in the HP project), i.e. volume moving with
every espressivo note. Affects the earlier listening copies apply-v1/apply-v2 (all, and
"vibrato only"). Fixed: no rate curves for SWAM until confirmed (`data/libraries.toml`).

## Open questions / experiments (for the SWAM session)

1. ~~Which instruments' plug-in states differ from the factory mapping~~ HP WW done (table above); other projects not yet.
2. SWAM's staccato/legato thresholds: render note pairs with gaps 0–60 ms and velocities
   40–127 (MIDI into SWAM outside Dorico, or Dorico test files) and listen/measure.
3. Should the maps get technique entries: flutter-tongue → CC23 ramp, overblow/"sfz" →
   CC64 or KS D1, staccato → velocity factor + length, alt. fingering for harmonics?
4. Vibrato rate on CC19 for strings collides with bow force: change the plug-in mapping, or
   leave rate alone?
5. Main Volume via CC14 at init: keep (balance per instrument) or set in the plug-in and drop
   from the map? Balance is also planned in Apply's dynamics lane.
6. Style variants (classical vs jazz: the flutes' *Style* slider, vibrato, attack bias) as
   alternative maps or plug-in presets.
