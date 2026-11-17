# stagecraft: status and resume notes

*Last updated 2026-11-02 (session 1: E1 inventory; session 2: E2 capture pilot; session 3: E3
capture library and analysis). Plan: PLANNED_WORK.md §7 (Project E).
Read this first when picking the work back up.*

## Where things stand

| Phase | State |
|---|---|
| **E1 Inventory** | ✅ mostly done: `dorico-format::mixer` (engine) + `stagecraft inventory` / `presets`; all 39 projects and 198 VSS2 presets read. Reports in `docs/inventory/`. Left: instrument names per rack slot inside the report (see "Next") |
| **E2 Capture pilot** | ✅ `stagecraft capture` / `convolve` / `ab`. User's blind A/B (2026-11-01): "I do not hear much difference … EXTREMELY subtle" → capture, then retire |
| **E3 Capture library + analysis** | ✅ 2026-11-02: `stagecraft library` (all 904 distinct sounds: the user's settings in 39 projects + 198 presets in 3 rooms), `motion`; VSS2's seat model decoded and fitted (below) |
| **E5 Spaces + seats** | in progress (2026-11-02): stage engine + files (`src/stage.rs`), VSS2-compatible stages checked against the captures (median −28 … −33 dB in the main rooms); the user's chosen improvements built (real arrival times, physical air absorption + brightness, wide sources, free mic plans/bleed, first reflections, reflection sends); the editor (`stagecraft serve`); a film-stage starter space. Reference: [STAGES.md](STAGES.md). Next: listening and tuning |
| E4, E6–E8 | not started |

User decisions (2026-11-01) are in PLANNED_WORK.md §7.2; tool name **stagecraft** chosen the
same day.

## What the inventory found

Reports: [all-projects.md](inventory/all-projects.md) (one row per project),
per-project reports for the main projects, [vss2-presets.md](inventory/vss2-presets.md).

**The current placement system** (Harry Potter Cues Plus 4/5, Obi-Wan End Credits (VSS),
BLACK LABEL, Rainy Nights, HP FLUTE; example
[Harry Potter Cues Plus 5 + LASS3.md](inventory/Harry%20Potter%20Cues%20Plus%205%20+%20LASS3.md)):

1. **VSS2 on every solo-instrument output** (SWAM woodwinds and solo strings, the Kontakt
   brass racks with one output per player, Spitfire harps, Pianoteq, some percussion), loaded
   from the user's own **"SWAM" preset set**. Those presets started as the stock **VSL** and
   **Samplemodeling Brass** presets (Harry Potter Cues, Cues Plus 1–3, HP BRASS TEST still use
   them); the user then moved the woodwinds forward (y ≈ 6.6–8.1 m → 3.8–6.7 m), turned
   everyone toward the centre, and tuned per-section values:

   | Section | y (m back) | ER level | Air |
   |---|---|---|---|
   | Solo strings (SWAM, American seating: Vln I far left, Vc right) | −0.9 … 2.4 | −2 (Cb −3) | −10 |
   | Harps (Spitfire), keyboards (Pianoteq) | 1.7 … 4.9 | 2 (Piano 0) | 0 / 10 |
   | Flutes, piccolo | 3.8 … 4.1 | **5** | **−100** |
   | Oboes, clarinets, bassoons | 5.0 … 6.7 | 2 | 10 |
   | Horns (left), trumpets/trombones/tuba (right) | 6.9 … 9.8 | 3 (tpt, tuba 4) | 30 |
   | Percussion | ≈ 12 | 2 | −50 … 10 |

   All at height 1.5 m; solo instruments are point sources, VSS2's ensemble presets
   (LASS, Hollywood Strings, 8dio …) are 2.5 m wide. VSS2's shared room is the same in every
   project (room id 1399018305, level 1.5, dry/wet 0).
2. **Reverb in two layers, as the user described** (decoded from the Altiverb states):
   - **Fx Reverb** FX channel: Altiverb, **Todd-AO 3.5 m s-s, early reflections only**
     (direct and tail off), 45 % wet → the per-section early-reflection layer.
   - **Out**: Altiverb, **Todd-AO 10.7 m wide s-s, direct + tail** (ER off), 50 % wet → the
     glue (older projects: 11.7, 15.7 or 18.9 m wide). Compressor in slot 4; REVerence
     bypassed.
3. **Sends from VSS2 channels to the ER layer are off** (confirmed by the user), but still
   carry per-section levels (woodwinds −6 dB, bassoons/harp keyboards 0 dB, brass +6 dB). So
   today the ER layer reaches only channels **without** VSS2, whose sends are on at 0 dB
   (the user confirmed LASS 3's send is on): mainly **LASS 3** (rack 10, all five
   sections on one stereo output) and the Kontakt percussion/choir/keyboard racks.
4. **No pan anywhere**: Dorico's panners are untouched; all left/right placement comes from
   VSS2 (and LASS's own seating).
5. **Full Orchestra Template NEW FULL v5** (and FLYING SAILOR, IFMC BLANK, THE FOUNDLING,
   HP WW): no placement at all (Compressor on Out, REVerence on the FX channel).

**Libraries per rack slot** (Harry Potter Cues Plus 5 + LASS3, from dorico-hp's
`playback.py`: instrument → endpoint → slot → expression map):

| Rack | Instruments | Plug-in / map | VSS2 |
|---|---|---|---|
| 10 | Violin I/II, Viola, Cello, Bass (one output) | Kontakt, LASS 3 | no (send on) |
| 14 / 27 / 28 / 29 | Horns 1–6 / Trumpets 1–4 / Trombones 1–3 + Bass Tbn / Tuba, one output per player | Kontakt with "SWAM - Horn/Trumpet/Trombone/Tuba" maps: **Sample Modeling brass** (Kontakt versions; confirmed by the user 2026-11-01) | yes |
| 9, 31 | Harp 1, 2 | Kontakt, Spitfire Harp | yes |
| 2–5, 11–13, 15–16, 22–26, 32, 39, 42, 51, 52 | woodwinds | SWAM Woodwinds | yes (alto/bass flute: no) |
| 46–50 | solo strings | SWAM Strings 3 | yes |
| 18, 19, 33, 40 | keyboards, harpsichord | Pianoteq 6 | yes (40: no) |
| 6, 7, 20 | triangle/cymbals, mallets, clash cymbal | Kontakt | yes |
| 8, 30, 43, 44, 45, 34, 21, 17, 35 | celeste/piano, mallets, tam-tam, tubular bells (Spitfire), timpani (CineSamples), choir, synths, Joshua Bell violin | Kontakt | no |

**Oddities** (no action needed, noted for the tools): 20 VSS2 inserts in HP FLUTE /
HP FLUTE print have no saved settings (empty state records); the brass outputs carry
leftover VSS2 states in an empty slot 2; 13 older presets have a room block the decoder can't
follow (position and levels still decode); Kontakt states are compressed (no library names).

## What VSS2 does not tell us from its state

- The **library profile** and **mic position** a preset names are not stored in the state;
  VSS2 seems to apply them when the preset loads. Their effect is in the sound only.
- Units/meaning of ER level, GoLR/DoLR, RSRo. VSS2 has **no automatable parameters**, so
  nothing can be swept; only captured.
- VSS2 reports **192 samples latency** (4 ms at 48 kHz); captures remove it, and a
  replacement chain must report the same or Dorico/Cubase compensation will differ.

## E2 results (2026-11-01)

Method (`src/capture.rs`): 6 s exponential sweep (20 Hz–23 kHz, −12 dBFS) into the left
input, then the right, through `vi-render render --bank --input` with the VSS2 state;
regularised deconvolution → four 0.6 s IRs (L→L, L→R, R→L, R→R), latency removed. Checks:
repeat, −12 dB quieter sweep, null test with a stereo test signal (tone, noise bursts,
clicks) against VSS2, and VSS2 against itself (a second load).

**Pilot** (Harry Potter Cues Plus 5 + LASS3, plus two presets in that project's room):

| Pin | Source | Mono source: L−R level / right later by | Gain L→L / R→R | Cross L→R / R→L | Arrival L→L / R→R | Direct / early / late (L→L) | Length | Repeat direct / early / late | Level | Null L / R (VSS2 vs itself) |
|---|---|---|---|---|---|---|---|---|---|---|
| Fl1 | Harry Potter Cues Plus 5 + LASS3.dorico / rack 2 SWAM Flute 64bit / 1 (Flute 1) | +0.3 dB / +1.33 ms | 20.6 / 20.2 dB | -16.1 dB +0.00 ms / -15.7 dB +0.00 ms | 0.00 / 0.00 ms | 98 / 1 / 0 % | 176 ms | -78 / -5 / -4 dB | -21 dB | -10 / -5 dB (-32 / -29) |
| Cl 2 | Harry Potter Cues Plus 5 + LASS3.dorico / rack 11 SWAM Clarinet 64bit / 1 (Clarinet 2) | +0.1 dB / +0.44 ms | -2.8 / -3.0 dB | -15.1 dB +0.00 ms / -15.0 dB +0.00 ms | 0.00 / 0.00 ms | 86 / 10 / 4 % | 174 ms | -78 / -14 / -12 dB | -14 dB | -18 / -12 dB (-40 / -21) |
| Hrn 1 | Harry Potter Cues Plus 5 + LASS3.dorico / rack 14 Kontakt / Kt. st. 1 (Horn 1) | +0.2 dB / +0.90 ms | -5.3 / -5.4 dB | -15.6 dB +0.00 ms / -15.5 dB +0.00 ms | 0.00 / 0.00 ms | 75 / 17 / 7 % | 182 ms | -75 / -12 / -12 dB | -18 dB | -18 / -12 dB (-47 / -20) |
| Tpt 1 | Harry Potter Cues Plus 5 + LASS3.dorico / rack 27 Kontakt / Kt. st. 1 (Trumpet 1) | -0.2 dB / -1.15 ms | -6.2 / -5.7 dB | -14.8 dB +0.00 ms / -15.3 dB +0.00 ms | 0.00 / 0.00 ms | 80 / 11 / 8 % | 182 ms | -75 / -7 / -6 dB | -20 dB | -17 / -12 dB (-45 / -26) |
| Vln 1 | Harry Potter Cues Plus 5 + LASS3.dorico / rack 46 SWAM Violin 3 / Output (Solo Violin 1 (Seated)) | +0.9 dB / +0.96 ms | 3.4 / 2.5 dB | -15.4 dB +0.96 ms / -14.5 dB +0.00 ms | 0.00 / 0.96 ms | 96 / 3 / 1 % | 181 ms | -78 / -3 / -3 dB | -16 dB | -17 / -11 dB (-46 / -26) |
| LASS 1.Violins Ensemble | preset LA Scoring Strings/LASS 1.Violins Ensemble.vss2preset (LA Scoring Strings, Default) | -4.4 dB / -0.42 ms | -6.1 / -1.3 dB | -14.9 dB -0.02 ms / -14.4 dB -0.02 ms | 0.29 / 0.65 ms | 95 / 4 / 1 % | 183 ms | -77 / -6 / -4 dB | -18 dB | -17 / -11 dB (-41 / -24) |
| Samplemodeling Horn 1 | preset Samplemodeling/Brass/Samplemodeling Horn 1.vss2preset (Samplemodeling Brass, Default) | +0.4 dB / +0.00 ms | -8.2 / -9.0 dB | -15.6 dB +0.00 ms / -14.9 dB +0.00 ms | 0.00 / 0.00 ms | 76 / 20 / 4 % | 189 ms | -75 / -12 / -13 dB | -15 dB | -16 / -14 dB (-42 / -30) |

**What VSS2 turned out to be**

1. **Direct sound: fixed and captured exactly** (repeat −75 … −80 dB). Linear (level check
   −14 … −29 dB, limited by the moving reflections, not by distortion).
2. **Reflections move.** Early reflections and tail change continuously while VSS2 runs and
   differ between loads (click train: click-to-click −5 … −26 dB), with steady energy (±0.3 dB)
   and colour (±0.15 dB). A captured IR is a snapshot: right level, timing and colour, no motion.
   That is why the IR null (≈ −17 / −12 dB) is short of VSS2's own run-to-run match
   (≈ −40 / −22 dB on the same test signal). *(Corrected in E3: the pattern is the same every
   load; only a slow treble shimmer moves.)*
3. **Placement = time difference.** A mono source comes out with near-equal levels (< 1 dB
   apart) and the far side 0.4–1.3 ms later (spaced main microphones). Pan knobs can't do
   that; a sub-millisecond delay per side can, which makes a light replacement easy. *(E3:
   these are the outer and centre capsules of a simulated Decca tree, see E3 results.)*
4. **The room is per project.** VSS2's global room (room id, output level, main microphone
   setup "MiSe") differs between projects: Harry Potter room id …305, level +1.5, main pair
   at (−3.5, 10); Christmas 2 room id …306, level −3.0, pair at (0, 2.5); both ±45° capsules
   1.2 m apart. A few instances carry a longer room block (494 bytes). Presets carry no room,
   so `capture --preset` needs `--room-from PROJECT`.
5. **Flute/piccolo settings boost treble** (AirA −100): +9 dB at 8 kHz, +23 dB at 16 kHz vs
   the clarinet. *(User, 2026-11-01: intentional, to make them carry as live players do;
   open to a better way, PLANNED_WORK §7.11.)*
6. Bugs found on the way, both mine and fixed: test noise had a DC offset (wrecked the R null);
   preset → state needed the pin id, path and project room.

**Real audio** (Christmas 2 stems from 2021-12-13: dry and "(DECCA)" = through VSS2): the dry
alto sax through today's captured IR matches the DECCA stem's tone within ±0.5 dB from 125 Hz
to 16 kHz and its image exactly (−1.7 dB / left 1.79 ms later). Clarinet: tone within ±1 dB
(250 Hz–8 kHz). Tenor sax and trombone 1 differ: the project was saved again on 12-14, so
their settings probably changed after the export. (Renders of Sample Modeling/SWAM differ
sample by sample, so only tone and image can be compared.)

**Listening files (blind A/B)**, `stagecraft ab`: dry stems through live VSS2 vs through the
captured IRs, same gain, random order; key in `key.txt`. On the user's machine:
`\\wsl.localhost\Ubuntu-26.04\home\ken\dev\dorico-test\stagecraft\captures\listening\`
- `xmas-winds/`: 8 winds (3 saxes, clarinet, bass clarinet, 3 trombones), 160–205 s;
- `xmas-alto-sax/`: alto sax alone, 55–85 s.
A vs B differ by −24 dB on this music; levels within 0.2 dB.

## E3 results (2026-11-01/02)

`stagecraft library` over the 39 projects (+ HP FLUTE test I, new) and the 198 presets in the
rooms of Harry Potter Cues Plus 5 + LASS3, Christmas 2 and all i want 2: 1288 instances/presets
→ **904 distinct sounds** (name, colour, pin id and preset path don't change the sound, tested),
all captured, no errors (≈ 5 s each, 825 MB in `captures/library/`, local). Tables by room:
[inventory/vss2-library.md](inventory/vss2-library.md) (copy of `captures/library/library.md`).
`--reanalyse` recomputes the numbers from the saved IRs.

**VSS2's seat, decoded** (details in [FORMATS.md](FORMATS.md)):
1. **Main microphones simulated geometrically.** Each output = its own capsule + the centre
   capsule (Decca tree), each the source delayed by distance / 343 m/s, the earliest capsule
   on the 4 ms latency. Timing: median error 0.001 ms over 2344 taps, once the **room limits**
   are applied: VSS2 keeps the tree within 3.0 m of the stage and 8 m high in `ScSA` (the
   Harry Potter projects store 3.5 m / 10 m) and within 3.5 m in `ScSB` (the "7 m" projects).
2. **Levels**: ≈ 1/distance, centre capsule −9.1 dB, PiOG dB for dB, small facing term,
   cardioid capsules by pattern. On the user's settings: **median error 0.03 dB, 95 % within
   0.54 dB** (piano, one harp up to 6 dB off).
3. **Air = a fixed EQ dial** (table in FORMATS.md: −100 → +22.5 dB at 16 kHz, 10 → −5, 30 → −12,
   80 → −25), independent of distance.
4. **ER level**: ≈ +1–1.5 dB of early reflections per step; early reflections 11–16 dB below
   the direct sound in the scoring rooms, ≈ 21 dB in the studio.
5. **Library compensation decoded**: GoLR / DoLR = gain and delay between the two inputs
   (undo a stereo library's own placement); 0 in all the user's settings.
6. **Filters are symmetric around the latency point** (up to −5 dB of a flute's response
   before it): IRs are now saved whole with `ir_offset_samples`; the E2 pilot IRs and A/B
   files were trimmed (slightly less exact; checks and null tests were unaffected).
7. **Reflections: fixed pattern + slow treble shimmer** (`stagecraft motion`, alto sax and
   flute): same pattern every load (correlation 0.95 alto sax / 0.75–0.8 flute at any gap,
   1.00 below 2 kHz); a random modulation at ≈ 0.1–0.9 Hz above ≈ 4 kHz moves the 4–8 kHz
   level < 1 dB. This corrects E2's "re-randomised at every load". The user's A/B ("extremely
   subtle") fits.
8. **CPU**: VSS2 ≈ 1.9 % of a core per instance offline; ≈ one core for the main template.

**What this means for the replacement (E5/E6):** a seat = per output two delay taps (own and
centre capsule) with gains + one EQ (Air) + a send into a shared early-reflection layer, all
computed from position, room and the settings above; a light chain, no per-instrument
convolution needed. The captured IRs stay the exact reference for A/B. Motion, if wanted: a
slow modulation in the shared reflection layer (cost independent of instrument count).

## E5 so far (2026-11-02)

- **Stage files** (TOML, [STAGES.md](STAGES.md)): space (any microphone plan with mix levels,
  speed of sound, distance law, level, depth delay on/off, exact or VSS2-rounded delays), air
  EQ, players. `stage from-project` writes a VSS2-compatible one for a project; `stage render`
  writes per-player IRs and taps; `stage check` compares with the captures.
- **Exactness of the per-mic gains**: least-squares gains (300 Hz–3 kHz, `Tap.gain_db` in the
  captures) show VSS2's level law exactly: ScSB 1/distance (exponent 1.00), centre −9.0 dB,
  PiOG dB for dB, errors 0.00–0.03 dB; ScSA exponent ≈ 0.88; room base 16.5 / 19.3 / 19.0 dB +
  GOLv. Values in `stagecraft/stages/vss2-compat.toml`.
- **Air EQ** = amount(Air) × one shape (within 0.25 dB); amount 10 → 1, 30 → 2.67, 50 → 3.96,
  80 → 6.03, −100 → −3.63.
- **VSS2 rounds each mic's travel time to whole samples**, then subtracts the earliest.
- Match: median residual −28 / −33 dB (ScSA), −27 … −30 (ScSB tree 3–3.5 m), −22 (Christmas),
  −19 (studio), −13 (coincident pair); piano and some percussion don't match.

**User's choices (2026-11-02)**: real arrival times, physical air + brightness, sections as wide
sources, free mic plans + bleed, reflection layer, floor/first reflections (not chosen now:
instrument radiation patterns); tuning in a visual editor page, later inside the Playback app
(PLANNED_WORK §2.11). All built the same day:

- engine: `depth_delay`/`depth_reference_m`, `air_absorption` (ISO 9613-1, temperature,
  humidity), player `brightness_db`, `facing_deg`, `width_m` (inputs at the ends), any mics with
  `delay_ms`, `[space.room]` (first-order image sources per surface), `[space.reflections]`
  (send per player); the VSS2-compatible check is unchanged by all of it;
- `stage from-project --space FILE` (seating from VSS2, space from the file; VSS2 Air →
  brightness, same curve); `stages/film-stage-starter.toml` (starting values, not measured);
- `stagecraft serve STAGE`: the editor (drag, all settings, taps per player, save, audition of
  dry stems in the browser through the stage); checked with headless Edge screenshots.
- Found: VSS2's sections are **not** "each input at one end" (residual ≈ 0 dB, level +4–6 dB
  vs the captures): open.

## Next

1. **User tries the editor**: `stagecraft serve stagecraft/captures/stages/hp5-film.toml`
   (or `hp5.toml`, the VSS2-compatible one) with dry stems; first impressions decide what to
   tune or build next (e.g. auditioning the reflection layer in the editor, A/B against VSS2).
2. Film-stage space from the user's references (E5), then E6 host builds (taps + EQ + sends
   for Dorico/Cubase/Logic).
2. **E4 source profiles** (per VI family, with Project C), including level calibration per
   dynamic (ensemble balance, PLANNED_WORK §7.11) and, for Infinite Series, the in-player
   positioning (§7.13).
3. Open details: piano and harp level misfits; RSRo meaning; cardioid studio room has few
   samples; the reflection pattern itself (timing per seat) not yet modelled.
4. Move `src/audio.rs` (sweeps, deconvolution, measurements) into a shared engine crate when
   a second tool needs it (PLANNED_WORK §7.9; latency-reporter is the likely one).
5. **Instrument names in the inventory**: waits on engine routing (`engine/REQUESTS.md`).

## Session log

- **2026-11-01 (session 1)**: plan written (PLANNED_WORK.md §7), user's decisions recorded,
  tool named. Built `dorico-format::mixer` (engine; CHANGES.md), `stagecraft` crate (VSS2,
  Altiverb, inventory, presets). Inventory of 39 projects + 198 presets; findings above.
  User confirmed: Kontakt brass = Sample Modeling brass; LASS 3's send is on; stagecraft adds
  vi-render's input option (done, first impulse captured).
- **2026-11-01 (session 2)**: E2 capture pilot. `stagecraft capture` (sweeps → true-stereo
  IRs + checks + placement numbers), `convolve` (apply IRs; compare tone/image with a
  reference), `ab` (blind listening files); VSS2 state writer (lossless round trip on all 45
  states, tests/real_files.rs); presets captured in a project's room. Findings above;
  waiting on the user's listening.
- **2026-11-01/02 (session 3)**: user's A/B verdict (go). E3: `stagecraft library` (sound id,
  room + mic decoder, seat numbers, resume, `--reanalyse`), `motion`; IRs now kept whole
  (symmetric filters); 904 sounds captured (the first run stopped at 378 when the session
  ended overnight and was resumed). Decoded: geometric Decca tree with room limits, level
  model, Air map, ER map, GoLR/DoLR input balance, reflection shimmer, CPU. User's ideas
  recorded in PLANNED_WORK §7.11 (balance), §7.12 (mic bleed), §7.13 (Infinite Series).
- **2026-11-02 (session 3, cont.)**: E5 started: per-tap least-squares gains and third-octave
  tone in the captures; stage engine + files (`src/stage.rs`, `stages/vss2-compat.toml`,
  docs/STAGES.md), `stage from-project | render | check`; VSS2's whole-sample rounding found.
  User chose the improvements and the editor; built: engine features, `--space`, film-stage
  starter, `stagecraft serve` (`src/serve.rs`, `editor/index.html`).
