# Formats

What stagecraft reads, and how it was worked out (2026-11-01, from the user's projects and
preset files; "?" = not confirmed).

## Dorico mixer and plug-in states (`dorico-format::mixer`)

`supplementary_data/vstaudioengine/enginedata` in a `.dorico`: length-prefixed chunks
(`MixerData`, version, `MixerDocument`, mixer XML), then audio/MIDI device XML, then
`PluginStatesHeader` and one binary record per plug-in instance.

**Mixer XML** (`<mixer>`): `<instruments>` (the VST rack: `id`, `name`, `slot`, `uid`), then
channels: `output-channel` (Out), `input-channel`, `fx-return-channel` (FX channels),
`instrument-return-channel` (one per plug-in output; `instrument-id` = rack `id`). Each
channel: `pre-insert-section` / `post-insert-section` with `<insert id slot name uid
[enabled="0"]>`, `send-section` with `<send id slot [enabled="0"] gain>`.

- `gain` is linear (1.0 = 0 dB; 2.0 = +6 dB, the maximum seen). Faders: older projects store
  nothing for untouched channels; newer ones (Full Orchestra Template v5) store 0.5 (−6 dB)
  on most. The inventory treats the most common value as the project's default.
- Sends: `enabled="0"` = off (confirmed by the user in Dorico: Flute 1's send is off in Harry
  Potter Cues Plus 5 + LASS3); a send stored without `enabled` is on (LASS 3's, same project,
  confirmed). Untouched sends: older projects store them as on at 0 dB,
  the v5 template as off at 0 dB. Send `slot` n is assumed to be the n-th FX channel (only one
  FX channel seen so far).
- **No pan is stored anywhere** (no attribute in any project): Dorico's panners are untouched.
- An `<insert>` without `name`/`uid` is an empty slot; it may still own an old saved state
  (the brass Kontakt outputs have one in slot 2: VSS2 set up as the next player). The user
  confirmed Dorico shows one VSS2 per strip, so these are leftovers.

**Plug-in state record**: `u32 11 "PluginState"`, `u64 size`, `u64 owner` (= the XML `id` of the
rack instrument or insert), `u32 n`, `"VST3"`, `u32 1`, 32-char uid, `u64 len`, data.
Empty records (size 16, data all zero) mean no settings were saved (20 VSS2 inserts in
HP FLUTE). VST2 plug-ins are wrapped: data = `"VstW"`… + a standard fxBank (`CcnK`…`FBCh`,
chunk at +156) or fxProgram (`FPCh`, chunk at +56), big-endian. Kontakt chunks (`Ni$D`) are
compressed; no instrument names readable.

Note for `doricokit.virender.plugin_states` (Project C): it pairs states with rack slots by uid
order; the `owner` id gives the exact match.

## Virtual Sound Stage 2 (`stagecraft::vss2`)

Parallax-Audio, VST2 id `Para`, 64-bit DLL `C:\Program Files\Steinberg\VstPlugins\
VirtualSoundStage2_x64.dll`. **No automatable parameters** (vi-render `info`: 0 params);
everything is in the chunk. Reports **192 samples latency** (4 ms at 48 kHz).

State chunk: `"g Y8"`, u32 count, properties. Preset file (`.vss2preset`): zlib XML
`<Preset PresetData="…" Instrument="…" Library="…" Microphone-Position="…"/>`; PresetData is
JUCE base64 (`"<size>."` + 6-bit chars `.A–Za–z0–9+`, least significant bit first) of
u32 count + the same properties.

Property: 4-byte tag stored little-endian (file "oCiP" = "PiCo"), JUCE compressed int size
(1 byte n + n bytes LE), then a JUCE `var` (1 int32, 2 true, 3 false, 4 double, 5 string,
6 int64, 8 binary). Size 0 + small u32 = nested group (`RoSS`); size 0 otherwise = empty.

| Tag | Meaning | Values seen |
|---|---|---|
| PiNa, PiCo | pin name, colour (ARGB hex) | "Cl 2", "ff39b54a" |
| PiMu, PiSo, PiBy | mute, solo, bypass | |
| PiOG | pin gain (dB?) | 0; Tpt 2 −2 |
| SSSe | source: 4-byte id `96 f2 a4 1b`, flag byte, f32 x, y, height, facing dx, dy, u32 0, u32 emitter count, 7 f32 per emitter (offset across, ?, ?, ?, 1.0, ?, radius 0.1–0.25); padding | solo: 1 emitter; sections: 2 at ±1.25 m; harp ±0.63 m |
| ERLe | early-reflection level (dB?) | strings −2/−3, woodwinds 2, flutes 5, horns/trombones 3, trumpets/tuba 4 |
| DSLe | direct-sound level | 0 everywhere |
| AirA | air absorption (first f64; then 6 f32 not understood). Negative = treble boost (measured) | strings −10, flutes −100, woodwinds 10, brass 30, percussion −50…10; empty for Piano |
| PoSi | pin id | unique per instance |
| PreN | preset file it was loaded from | `C:\Users\kspie\OneDrive\Documents\parallax-audio\Presets\SWAM\Woodwinds\Flute 1.vss2preset` |
| GoLR, DoLR | **input balance** (the preset's "Library" compensation, decoded 2026-11-02): GoLR = right input gain relative to left (dB), DoLR = delay of the left input relative to the right (ms; negative delays the right). Undoes a stereo library's own baked-in placement before VSS2 places it | 0 in all the user's settings and in VSL/SWAM/Samplemodeling presets; e.g. Cinebrass Horn Solo DoLR +8.9 (left input 8.90 ms later), Spitfire 1. Solo Violin GoLR +6.4 (right input ≈ 6 dB up) |
| ReTr, IOBy, IOPr | ? (bools) | |
| RSRo | ? (2 ints + floats); differs with the library profile, probably the stereo-source mode | (2, 3) / (2, 2) |
| RoSS | room, shared by all instances: UiZo, MMPa, RoID (room id), GOLv (output level, dB), UiSz, MiSe (main microphones, below), Seat (0), DrWe (0), UiVP. UiZo/UiSz/UiVP/MMPa are UI state | RoID as 4 ASCII letters: `ScSA` (1399018305), `ScSB` (…306), `Stdi` (1400136809), presumably two scoring stages and a studio; GOLv −3 … +1.5 |

**MiSe** (main microphone setup; `vss2::Mic`), little-endian: `"rAiM"`, u32 kind, f32 array
position x, y, z, f32 direction x, y, z, u32 capsule count, then per capsule f32 position x, y,
z (relative to the array), f32 direction x, y, z, f32 pattern (0 = omni, 0.5 = cardioid), u32
output (1 left, 2 right, 3 both); then more floats not understood (they differ between
otherwise equal rooms and look like leftover memory in older projects). Seen in the user's
projects:

| Kind | Capsules | Where | Projects |
|---|---|---|---|
| 1 | **Decca tree**: omni at x = −1 and +1 (turned ±45°) and centre omni 1.2 m forward feeding both outputs | y −3.5, z 10 (later Harry Potter projects); y −3.5 / −7 / −3, z 2.5 (older ones, Obi-Wan); y 0, z 2.5 (Christmas) | most |
| 5 | cardioid pair 25 cm apart at ±45° | y 1.05, z 2.5 | all i want 2 (`Stdi`) |
| 12 | coincident cardioids at ±60° | y −7, z 2.5 | HP - birds |
| (empty) | VSS2's default | | BLACK LABEL, Obi-Wan 2 |

z is the height (sources are at 1.5 m); y < 0 = in front of the stage edge. **Each room limits
where the array can go**, whatever the project stores (measured 2026-11-02 from the arrival
times, `vss2::MIC_LIMITS`): `ScSA` at most 3.0 m in front and 8 m high (Harry Potter Cues
Plus 3–5 store 3.5 m / 10 m; the arrivals fit 3.0 m / 8 m within 0.02 ms), `ScSB` at most
3.5 m in front (the "7 m" projects behave exactly like 3.5 m). Heights mirror around the
source height, so the timing alone can't tell 0.5 m from 2.5 m. The trailing MiSe floats
don't change the sound (rooms differing only there fit one model).

Coordinates: metres; x < 0 = left as heard; y = distance back (strings ≈ −1…3.5, woodwinds
3.8–6.7, brass 6.9–9.8, percussion ≈ 12); height 1.5 everywhere. Facing: 0° = toward the
listener; every instrument turned toward the centre.

Lossless round trip (`vss2::encode_state(parse_state(x)) == x`, checked on all 45 states of
Harry Potter Cues Plus 5 + LASS3 by `tests/real_files.rs`): the parser keeps the property
count (`_count`), unknown `var` types (e.g. `MMPa` is type 7, an array) and anything it can't
follow, raw (`_tail`). The room group comes in several layouts: in some states (e.g. Fl2)
four extra words (`368, 60, 16, 16`) precede its count; older presets differ again.

**Presets vs states.** A preset holds only the source (17 properties): no pin id (`PoSi`),
no preset path (`PreN`) and no **room** (`RoSS`: room id, microphone setup `MiSe`, level). The
room is VSS2's global setting, shared by all instances in a project. Loaded without it, VSS2
does not place the source (no crossfeed, other level). `vss2::state_from_preset` adds the
pin id and path and appends the room block of a project state (`room_bytes`); the Clarinet 2
preset built this way matches the project's Clarinet 2 to −75…−80 dB.

**What sounds the same.** Changing a state's name, colour, pin id or preset path leaves its
sound unchanged (Oboe 1, 2026-11-01: direct sound −76 … −86 dB, reflections within VSS2's own
spread). `vss2::sound_key` hashes the rest (plus the room's id, level, seat, dry/wet and the
whole MiSe value) and is used to capture each sound once.

**Measured behaviour** (captures, 2026-11-01; `stagecraft capture`, `library`, `motion`):
- **The main microphones are simulated geometrically.** Each output is the sum of its own
  capsule and the shared centre capsule (Decca tree), each a delayed, scaled, filtered copy of
  the source. The delays are the distances from the source to each capsule at 343 m/s
  (measured within 0.01 ms in every capture with a decoded mic setup). The earliest capsule
  lands exactly on the 192-sample latency; the others follow (up to ≈ 4.5 ms). The centre
  capsule is mixed ≈ 7–8 dB below the outer ones. This is why a mono source comes out at
  near-equal levels with the far side 0.4–1.3 ms later "on average" (the E2 description).
- **Its filters are symmetric (linear phase) around the latency point**: up to −5 dB of a
  flute's response (treble boost) lies in the 4 ms before it; 192 samples is the filters'
  half-length. Captured IRs therefore keep the latency (`ir_offset_samples`), trimming it
  would cut every filtered pulse in half.
- **Microphone levels** (the user's 1166 taps, 2026-11-02): ≈ 1/distance (exponent 1.0–1.3,
  higher with more Air), centre capsule −9.1 dB, PiOG adds dB for dB, small facing term,
  cardioid capsules scaled by their pattern. Median error 0.03 dB, 95 % within 0.54 dB (the
  piano and one harp miss by up to 6 dB).
- **Air (AirA) is a fixed EQ dial**, the same at any distance (spread 0.5–0.8 dB): direct
  sound at 4 / 8 / 16 kHz relative to 1 kHz:

  | Air | −100 | −50 | −10 | 0 | 10 | 30 | 50 | 80 |
  |---|---|---|---|---|---|---|---|---|
  | 4 kHz | +1.4 | +0.4 | 0.0 | −0.1 | −0.4 | −1.1 | −1.5 | −2.3 |
  | 8 kHz | +5.9 | +1.6 | +0.2 | −0.3 | −1.5 | −3.9 | −5.7 | −8.4 |
  | 16 kHz | +22.5 | +5.8 | +0.9 | −1.0 | −5.1 | −12.4 | −17.3 | −24.7 |

  Level-independent (not distortion).
- **ER level**: each step adds ≈ 1–1.5 dB of early reflections; early reflections sit
  ≈ 11–16 dB below the direct sound (1 kHz octave) in the scoring rooms, ≈ 21 dB in the studio.
- **CPU**: ≈ 1.9 % of one core per instance offline (60 s of audio in 1.15 s); ≈ 45 instances
  in the main template ≈ one core.
- **Direct sound is fixed**; repeat −75 dB and better, −140 dB click to click.
- **Reflections: a fixed pattern with a slow shimmer in the treble.** The pattern is the same
  at every load and stays put (correlation 0.95 alto sax, 0.75–0.8 flute, at gaps from
  0.5 s to 16 s and between loads; 1.00 below 2 kHz). What moves: a random modulation at
  ≈ 0.1–0.9 Hz above ≈ 4 kHz (0.98 at 4 kHz, 0.95 at 8, 0.82 at 16), which moves the 4–8 kHz
  level of the whole output by < 1 dB peak to peak (alto sax) and much less on a flute. That
  is the signature of slowly modulated delay times (chorus-like). Reflection energy steady
  ±0.2–0.7 dB. (E2 called the reflections "re-randomised at every load"; that overstated it:
  its numbers, e.g. early-part repeat −14 dB for Clarinet 2, mean a correlation of ≈ 0.98.)
- **Start-up fade**: right after loading, VSS2 fades in (the first click 0.1 s in comes out
  at half level); `motion` skips the first second.

Not in the state: the preset's **Library** (source-compensation profile) and **Microphone
Position**: only the preset file names them. Since the preset path doesn't change the sound,
whatever they do is already in the stored values.

13 of 198 presets (older ones) have a room group laid out differently; everything before it
(position, levels) decodes, the rest is flagged `undecoded`.

## Altiverb 7 (`stagecraft::altiverb`)

Audio Ease, VST2 id `AVr5`. Chunk = XML plist ("Mission Preset"): the IR as
`ir_ae/<category>/<room>/<position>/info.iri2` and every parameter as a dict
`{ID, Name, Value Float | Value Long}` ("Dry/Wet Mix", "Direct On", "Early Reflections On",
"Tail On", "Direct Gain", "EarlyRef Gain", "Tail Gain", "Pre Delay", "Size", "Reverb Time",
"Stage Positions On", "Bypass", EQ, damping, speaker positions…). Gains in dB.
