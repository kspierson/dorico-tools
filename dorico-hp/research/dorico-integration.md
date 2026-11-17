# Working with Dorico's playback, not against it

How the HP rebuild fits Dorico's own playback (playback options, expression maps,
percussion maps), so that a project with properly configured maps keeps working the way
Dorico intends, and the humanisation only adds what Dorico doesn't do.

Sources: the playback options stored in a Dorico 5.1 project (`score.dtn` →
`/kScore/options/playbackOptions`, all names and defaults below come from there); the
user's expression maps (`tools/dorico_maps.py` → `dorico-user-expression-maps.md`);
Dorico 5 install files (`C:\Program Files\Steinberg\Dorico5\scorelibrary.xml`:
rhythmic feel definitions); Steinberg help (pages describe the dialogs, not the options).

## Ground rules

1. **Playback only.** Apply writes nothing that appears in Write mode or in print: only
   Play-mode data (per-note velocity, played start/end offsets, automation and the
   dynamics lane) and, if asked, project playback options. No hidden notation items
   unless a test shows there is no other way (tempo may be the exception, see below).
   One project replaces the old "score" + "playback score" pair.
2. **Read the project, don't assume.** Every `.dorico` file embeds the expression maps
   and drum maps it uses (`scorelibrary.dtn` → `expressionMapDefinitions`,
   `drumKitNoteMapDefinitions`) and its playback options. Apply reads them per
   instrument and adapts: which controller carries dynamics, which techniques have their
   own sample, which durations the map already overrides.
3. **One owner per controller.** Controllers that a map uses for dynamics
   (`volumeType`, `volumeType2`) or switches during playback (technique actions) belong
   to Dorico. Apply never writes raw automation for them. It shapes dynamics through
   Dorico's own dynamics lane (format pending test I) so the map still decides how the
   dynamic reaches the VI. Apply writes raw CC curves only for controllers that the map
   at most sets once (init actions), e.g. SWAM vibrato depth (init CC1=24/32) – and it
   should write a value at the start of each curve, because Dorico re-sends init actions
   when playback starts. **An init CC is not automatically safe**: SWAM's CC14 (init 46/12)
   is Main Volume, not vibrato rate (corrected 2026-11-01, `vi/swam.md`). Check what a CC
   means in the plug-in (its state in the project) before writing curves on it.
4. **Re-applying is safe.** Everything Apply writes is tagged (own event group ids,
   recorded in a manifest inside the output) so a second Apply removes the previous
   result first and never touches the user's own Play-mode edits.
5. **Don't double up.** Where Dorico has an equivalent option (beat stress, humanise,
   articulation lengths, swing), one of the two does the job. Apply reports the options
   it found and either sets the Dorico option to neutral or uses it instead of its own
   rule – decided per feature below, adjustable per profile.

## HP feature → who does it

| HP feature | Dorico mechanism (option name, default) | Plan |
|---|---|---|
| Dynamic levels → volume | Dynamics → expression map `volumeType` (vel / CC1 / CC11, `velocityRange` min,max), `dynamicCurveParams` 0.5,1,1, levels −6…+6 | **Dorico.** Map owns the controller. Apply adds level adjustments per library (the "playback score" re-voicing) via the dynamics lane. |
| Velocity as attack on CC instruments (HP: 85–121 on strings) | Map `attackType` = velocity | **Apply** writes per-note velocity where the map uses velocity only for attack (needs test J for velocity-dynamic maps). |
| Hairpin curves | Dorico interpolates the dynamic; `resetLevelForShortConsecutiveHairpinsInSameDirection` | **Apply** reshapes through the dynamics lane (HP's S-curve, library-tuned). |
| Accent / marcato | `accentDynamicDelta` 1.0, `marcatoDynamicDelta` 0.7 (dynamic steps) | **Dorico.** HP's +19 velocity was a Finale articulation, not HP. Profiles may tune the Dorico options. |
| Articulation lengths | `noteDurationPercent` 95, staccato 50, staccatissimo 25, tenuto 98, legato (slurs) 105, marcato 95; maps override per library (SWAM strings: note 80, stacc 40; IW stacc 33) and have per-technique `lengthFactor` | **Dorico** for the base length. **Apply** adds context only (tempo-aware shortening, slur-end release, phrase ends) as played-end offsets, and only after test K shows how offsets combine with the percentages. |
| Slur legato overlap | `legatoDurationPercent` 105; maps with a legato technique switch patches | **Dorico.** Apply may add library-specific overlap/latency fixes (SWAM legato needs overlap; LASS legato transitions are late). |
| Beat accents (HP rhythmicAccents) | `primaryBeatStressDelta` 0, `beatStressDelta` 0 (+ unpitched percussion versions) | **Apply** (HP's metre hierarchy 1>3>2=4, style-dependent, inverted for funk/jazz). Dorico's stress options stay at 0; Apply warns if they aren't. |
| Rhythmic feel (HP weak-beat delays) | `timingHumanisePercent` 30 (random) | **Apply** (deterministic, style-scaled). Recommend Dorico's random timing humanise → 0 when HP timing is on (profile choice). |
| Swing | `defaultRhythmicFeel` straight; rhythmic feel changes (light/medium/heavy 8ths/16ths, fixed 2:1, 3:1) | **Dorico only.** Apply never swings. Under a swing feel, Apply's weak-beat delays are off (or scaled down) so they don't fight the swing. To verify with test M (Finale + Dorico swing). |
| Trills | `trillPlaybackMode` kSampledAndGenerated, speeds 8/12/16, `startPlaybackOnUpperNote`, `playAcceleratingTrill` | **Dorico.** With a trill technique in the map Dorico plays the sample, otherwise it generates notes. Apply does not write trill notes; profiles may set the speed options. |
| Tremolos | `unmeasuredStrokesThreshold` 3, `unmeasuredNoteLengthAt120BPM` 1/5; map techniques `pt.tremolo` (LASS, LASS 3, Nashville, Joshua Bell, SWAM strings add-on CC21, timpani CC1 roll, percussion maps) | **Dorico.** Same: sample if the map has it, generated otherwise. |
| Glissandos / harp glissandos | `glissandoPlaybackOptions.delayedStart` false | **Dorico** for playback of the line; **Apply** only for HP-style timing refinements, later. Harp pedal tuning is a separate question (harp gliss examples pending). |
| Grace notes | `noteLengthAt120BPM` 1/6, short appoggiatura threshold, `playAppoggiaturas` | **Dorico.** |
| Arpeggios / strum | `arpeggioOffsetAt120BPM` 1/10, slur arpeggio 1/12, position, min/max offset | **Dorico.** |
| Pedal (and HP auto-pedal) | `pedalLinePlaybackOptions` (depression/retake/release lengths) | **Dorico** for written pedal lines. HP auto-pedalling (no written pedal) would be Apply writing CC64 automation – only for instruments without pedal lines; later. |
| Fermatas, caesuras, breath marks | `pausePlaybackOptions`: normal fermata +50 %, long +100 %, very long +200 %, caesura 50 %, breath mark shortens 50 % | **Dorico.** HP plays a minim fermata ~2× (≈ Dorico "long"); profiles can tune these options. |
| rit. / accel. | Gradual tempo changes play with their own curve (final tempo set on the item) | **Dorico.** HP's −20 %/bar is a fixed rate; nothing to add yet. |
| Rubato (Romantic, Viennese) | none | **Apply**, but needs a playback-only tempo route (test L). |
| Phrase shaping, espressivo, chord balance, soften basses, accompaniment/solo balance | Dorico has a hidden `noteExpressionOptions` block (melody detection, voice balancing for keyboard/harp/fretted; `enableNoteExpression` false) | **Apply** (dynamics lane offsets per instrument/voice). Check whether Dorico's note-expression options appear in the UI; if they do, keep them off when Apply balances. |
| Vibrato (Garritan auto-vibrato in HP) | none (maps only set vibrato once at init) | **Apply**: per-note CC curves per library profile (SWAM, Joshua Bell, others with vibrato CCs). |
| Keyswitch / patch changes | maps (`numTicksBeforeForSwitches` 10, per-map `ticksBefore`/`millisecondsBefore`) | **Dorico.** Apply never sends switches. |
| Library latency (slow attacks, legato transitions) | none | **Apply**: negative played-start offsets per library/technique profile (variable part). Constant plug-in delays (LASS 3 look-ahead): see "Delay compensation" below. |
| Percussion | percussion/drum maps; separate beat stress and humanise for unpitched percussion; rolls via map (`Percussion - Mod Wheel Rolls`) | **Dorico** for mapping and rolls; Apply only velocity and timing shaping. |

## Delay compensation (VI look-ahead and other processing delays)

Two different problems:

**A. Constant delay of a whole instrument.** LASS 3's look-ahead delays everything the
instrument plays by a fixed time (≈ 440 ms by default, ≈ 460 ms in some configurations)
so its script can see notes before they sound. The user writes with it off and turns it on
for stem export, then slides those stems earlier in the DAW. Other VIs/plug-ins with
internal look-ahead behave the same way. A constant delay should move *everything* the
instrument receives (notes, Dorico's dynamics CCs, keyswitches, Apply's own CCs) by the
same time, independent of tempo. Options, best first:

1. **Host delay compensation** (chosen by the user; the plug-in is a separate project:
   `../latency-reporter/README.md`). Dorico's audio engine compensates latency that plug-ins
   *report* (this is how NotePerformer's 1-second look-ahead stays in time). Kontakt
   doesn't report the LASS script's look-ahead, but a pass-through insert that reports a
   chosen latency (440 ms) on that instrument's channel would make Dorico send its MIDI
   that much earlier and align the audio, in playback and in audio export, with no
   change to the project's music data. Needs: a check that Dorico compensates latency
   reported by *insert* effects (test N), then a tiny VST3 "report N ms" insert (or an
   existing one, if one is found that works in Dorico). Fits naturally into the later
   real-time plug-in.
2. **Apply in "export" mode.** Shift the instrument's notes earlier with played-start/end
   offsets (ms → ticks through the tempo map, re-computed at every tempo change) and shift
   Apply's own automation with them. Problems: Dorico-generated dynamics CCs and
   keyswitches stay at the written time unless tests show they follow the played
   offsets (test N), notes in the first ~0.5 s of a flow can't move before the flow start
   (`preRollBeforeFlowSeconds`, test N), and the offsets show in Play mode.
3. **Stem offset list** (current workflow, automated): Apply writes a per-instrument
   offset table (instrument → ms) to paste/apply in the DAW. Always correct, zero risk.

Profile settings: `lookahead_ms` per library (LASS 3: 440, editable), and per run a
switch "look-ahead on/off" so the same project serves writing (off) and export (on).

**B. Variable delay per note.** Slow attacks, legato transitions (LASS without look-ahead,
SWAM bow/breath onset), soft dynamics speaking later than loud ones. Handled per note by
Apply's played-start offsets in milliseconds (converted to ticks at the local tempo), from
the library profile: by technique, dynamic level, interval, note length. When the LASS
look-ahead is on, LASS already evens out its transitions, so the profile turns these
per-note corrections off for that library.

## Tests still needed in Dorico

All of these can be files that I write and you open; for most, exporting MIDI from
Dorico (File ▸ Export ▸ MIDI) lets me measure the result without anyone listening.

- **I – dynamics lane. Answered 2026-11-01** (`Dorico Projects\HP FLUTE test I.dorico` + `.mid`:
  a swell drawn over bar 2 of Flute 1). Storage: `AutomationEventDefinition` events exactly
  like a controller lane (same `kAutomationStream`, `automationStreamTable` entry
  `kIRV:<instrumentID>:-1`, `kEventGroupId` per drawn line, last point `kConstant`) with
  `data/controllerDefinition` = **`kDynamic`** and `data/value` a decimal **Dorico dynamic
  level** (drawn: 0.69 → 2.62 → 0.48). **Absolute, not an offset**: inside the drawn span CC11
  follows the line (81 → 112 → 73) and Dorico's dynamic humanise and beat stress disappear;
  outside it Dorico's own dynamics resume. mf ≈ 0.5 (the line's end, 0.48, gave the same CC11
  as the written mf). Value → CC11 on SWAM - Flute: 0.48→73, 0.69→81, 1.34→93, 1.76→101,
  2.12→106, 2.62→112 (not linear: Dorico's dynamic curve + the map's range).
  **Test I2 (answered 2026-11-01, `HPCaptures\dorico\test-I2\`):** with humanise and beat
  stress off, written dynamics sit exactly on lane levels: pppp −4, ppp −3, pp −2, p −1,
  mp −0.5, mf +0.5, f +1, ff +2, fff +3, ffff +4 (CC11 5/12/24/41/52/76/87/104/116/123);
  accent +0.5 (f+accent = 1.5 → 96), marcato +0.8 (mf+marcato = 1.3 → 93) = the Playback
  Options deltas. Level 0 (CC11 64) is between mp and mf. Velocity follows the same curve
  scaled into the map's velocity range. Code: `doricokit.dynlevels` (shared).
  Side findings from the same export: (a) **Dorico reads open hairpins literally**: after the
  bar 8 cresc. (no end dynamic) CC11 stays ~97 instead of ~77 for bars 9–16, until the mf in
  bar 18. (b) **A custom technique linked to pt.staccato does shorten notes** (map staccato 38 %
  on unmarked notes), **but only until the first slur**: from the slurred pair in bar 2 on,
  unmarked notes play 85 % again (Dorico's technique state seems to fall back to natural after
  a slur). Apply's passage reading carries on through the passage.
- **J – velocity vs dynamics.** For a velocity-dynamics map (Default/Pianoteq) and a CC
  map (SWAM/LASS): does a stored note velocity replace Dorico's computed velocity, or
  only the attack? Does it survive a later dynamic change?
- **K – played offsets vs articulation lengths.** *Answered by the first listen (apply-v1,
  2026-10-26):* a note with played offsets loses Dorico's length percentages (staccato
  flute notes played full length). Apply therefore writes the played end explicitly using
  Dorico's own percentages for that note (`apply.played_length`). Still to confirm: whether
  a *start* offset alone already freezes the length.
  Original question: A staccato and a slurred note with
  played-end offsets: are the percentages applied first, or does the offset replace them?
- **L – tempo for rubato.** Does drawing in Play mode's tempo track create hidden tempo
  items in Write mode? Is there a playback-only tempo lane?
- **M – swing.** A short jazz line with a swing rhythmic feel in Dorico (and "Swing"
  text in Finale): what each program plays; and whether played offsets are measured
  from the swung or the straight position.
- **N – delays.** (1) Does Dorico compensate latency reported by an insert effect on one
  channel (any insert that reports latency: a look-ahead limiter or linear-phase EQ)?
  Export audio with and without it and compare alignment. (2) Do Dorico's dynamics CCs
  and keyswitches move with a note's played-start offset? (3) Can a note at the very start
  of a flow play earlier when `preRollBeforeFlowSeconds` is set?
- **Does Dorico's MIDI export include Play-mode edits?** **Yes for the dynamics lane**
  (test I export, 2026-11-01); velocities/offsets/automation very likely too (same export
  path), to confirm with the next Apply copy. So later tests can be files written here that
  the user only opens and exports.

## Passage markings: playing techniques first, text where Dorico has none

Agreed with the user (2026-10-26): use Dorico's built-in playing techniques where they
exist, plain text where they don't, and only add a custom technique for words common in
published/film scores.

- Dorico 5 ships written techniques for **spicc., legato, détaché, marcato, martelé,
  martellato, ord./naturale/modo ordinario** (`pta.*Text` in scorelibrary.xml, each linked
  to a playback technique `pt.*`). Apply reads them by the playback technique, so it doesn't
  matter which appearance is used.
- **"stacc." is not built in.** Recommended: one custom playing technique "stacc." linked to
  Dorico's existing playback technique *Staccato* (`pt.staccato`), saved to the user
  library. Expression maps that know pt.staccato (LASS 3) then switch patch natively, and
  Apply treats it like the word. **Confirmed 2026-10-31** (`HP FLUTE print.dorico`): the user
  made exactly this, a text technique "staccato" (`pta.user.staccato_text` → `pt.staccato`);
  encoding in `../../finale2dorico/docs/RESEARCH.md` (last section). Apply reads the linked
  playback technique **and** the technique's own words (`passages.technique_flags`), so a
  technique reading "stacc., brillante" gives staccato + light. Techniques linked to a
  custom *playback* technique (`pt.user.*`, e.g. "B Spiccato" in the ET score) are patch
  switches owned by the map: their words are ignored.
- **Character words** with no playback technique (brillante, leggiero, scherzando, dolce,
  espress., sempre …): **user's decision 2026-11-01**: when they belong to a playback word
  they go *into the same custom technique* ("stacc., brillante" linked to pt.staccato),
  because a text item can't be grouped with a technique for layout. On their own they can
  be text items. Apply reads the words either way (`doricohp/passages.py`).
  How Dorico stores text items is not confirmed yet (no text in the user's projects so far);
  `notation._texts_in` reads them best-effort until a real example arrives.
- A passage state lasts until a cancelling word (ord., nat., legato ↔ stacc., non stacc.),
  another word of the same kind, or a rest of 2+ bars. Under "stacc." unslurred notes
  without their own length mark play staccato (time-capped), and so does a slur's last note
  when a rest follows it (other slurred notes keep their length); "light" words shorten the
  caps (×0.45: ~40 ms) and lighten attacks; "marcato" firms attacks. Evidence:
  `score-vs-playback.md` → "HP FLUTE print vs playback copies".
