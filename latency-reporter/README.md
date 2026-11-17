# latency-reporter

A tiny VST3 **insert effect** that passes audio through unchanged but **reports a chosen
latency** (e.g. 440 ms) to the host. Put it on the channel of a virtual instrument that
delays its own output internally without telling the host, and the host's plug-in delay
compensation (PDC) lines that instrument up with everything else again: in playback and
in audio/stem export.

Status: **not started** – this file is the brief. Separate project from `dorico-hp`
(the Human Playback rebuild), which will refer to it.

## Why

Some VIs add processing delay that they don't report to the host. The main case is
**LA Scoring Strings 3 (LASS 3) "look-ahead"**: its Kontakt script delays everything by
about **440 ms** (≈ 460 ms in some configurations) so it can see upcoming notes and time
legato transitions properly. Kontakt doesn't report this as plug-in latency, so in Dorico
the strings sound ~440 ms late.

The user's current workaround: write with look-ahead off; for stem export turn it on and
slide the string stems ~440 ms earlier in the DAW. With this plug-in reporting 440 ms on
the LASS channel, Dorico would send that instrument's MIDI 440 ms early (or delay the
other channels by the same amount) and the exported stems come out aligned, with no
change to the Dorico project's music and no DAW nudging.

How the trick works: the instrument really delays its audio by L but reports 0. The
insert reports L but delays by 0. The channel's *reported* total (L) then equals its
*actual* total (L), so the host's compensation is exact. Tempo doesn't matter: the
delay is in time, not beats.

## Requirements

- **Format:** VST3, 64-bit Windows (Dorico 5 on Windows is the target host). CLAP/AU
  are not needed.
- **Audio:** bit-identical pass-through, any channel count the host offers (at least
  mono and stereo; multi-output Kontakt instances usually feed separate stereo
  channels in Dorico's mixer, one insert per channel).
- **Reported latency:** `round(ms × sampleRate / 1000)` samples; re-computed when the
  sample rate changes (`setupProcessing`) and when the parameter changes (notify the host
  with `restartComponent(kLatencyChanged)`).
- **Parameters:**
  - `Latency (ms)`: 0–2000, default 440, 1 ms steps (also show the value in samples).
  - `Active`: on/off. Off reports 0 so the same project works while writing with the
    VI's look-ahead off. (Don't rely on the host's own bypass for this: some hosts keep
    compensating a bypassed plug-in's latency.)
- **Presets** (nice to have): "LASS 3 look-ahead 440 ms", "LASS 3 look-ahead 460 ms".
- **State:** saved in the project (normal VST3 state), so the setting travels with the
  Dorico file.
- **No UI needed** beyond the host's generic parameter editor; a minimal custom UI is
  optional.
- **Zero CPU/added latency of its own**, no allocations on the audio thread.

## First thing to verify (before building much)

Whether Dorico compensates latency reported by **insert effects** (it certainly does for
instruments: NotePerformer's 1 s look-ahead relies on it), and whether that compensation
also applies to **audio export**. This can be checked with any existing insert that
reports latency (a look-ahead limiter, linear-phase EQ):

1. A project with two instruments playing the same click/attack at the same time.
2. Put the latency-reporting insert on one channel; export audio (both stems and mix).
3. If the two attacks still line up → Dorico compensates inserts. If the processed
   channel is late by the plug-in's latency → it doesn't, and plan B is needed (an
   instrument wrapper that hosts the VI and reports the latency itself; much more work).

Also check: does changing the latency while Dorico is open take effect (some hosts only
re-read latency when playback stops or the project reloads)?

## Related

- `../dorico-hp/research/dorico-integration.md` → "Delay compensation": the design this
  plug-in implements (option 1 there). `dorico-hp` library profiles will carry a
  `lookahead_ms` value per library (LASS 3: 440) and can tell the user what to set here.
- Per-note timing differences (slow attacks, legato transitions without look-ahead) are
  *not* this plug-in's job; `dorico-hp` handles those with per-note played offsets.

## Working notes for whoever builds it

- The user's machine: Windows with Dorico 5 (and Dorico 3.5), Cubase 13, Kontakt;
  development happens from WSL (`/home/ken/dev/dorico-test`). Built plug-ins must end up
  in `C:\\Program Files\\Common Files\\VST3` for Dorico to find them.
- WSL has no system gcc; other projects here use zig as the compiler with shims (see
  `../finale2dorico/docs/STATUS.md`, "Building the extractor"). Cross-compiling a
  Windows VST3 from WSL needs a Windows-targeting toolchain (e.g. zig/clang with the
  Windows SDK, or building on the Windows side with MSVC/CMake).
- SDK choice (VST3 SDK directly, JUCE, iPlug2…) is open; check the licence of whatever
  is used. The plug-in is for personal use only.
- **The user handles all commits and pushes.** Leave changes uncommitted.
