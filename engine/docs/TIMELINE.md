# Timeline: time in a Dorico project

*Engine module `dorico-timeline` (MODULE_REVIEW §4 #3). Started 2026-10-31; checked against
Dorico 5's MIDI export 2026-11-01. This file is the design, the evidence and the open questions;
resume here.*

## What it does

```text
notated position (crotchets) ──tempo map──▶ notated seconds
         │ performed order (repeats, endings, D.C./D.S., Fine, Coda)
         ▼
performed position ──▶ performed seconds ──▶ clip time (video) ──▶ timecode (any frame rate)
         └──▶ MIDI tempo events (ticks as Dorico's export writes them)
```

| Question a tool asks | Call (Rust `FlowTimeline` / Python `doricokit.timeline`) |
|---|---|
| When does crotchet 81/4 first sound? Every time it sounds? | `seconds(pos)`, `occurrences(pos)` |
| Ignoring repeats? | `notated_seconds(pos)` |
| What is playing at 1:23.5? | `at_seconds(secs)` |
| Tempo here? | `tempo.bpm_at(pos)` (crotchets per minute) |
| Clip time / timecode of a moment | `clip_time(secs)`, `timecode(secs)` |
| Tempo track for a MIDI file | `tempo_events()` → (tick, crotchets/min), identical to Dorico's export |
| Where does flow 3 start when the whole project plays? | `ProjectTimeline.flow_starts` |
| What did the numbers assume? | `caveats` (per flow) |

## Where the code is (one copy of each thing)

| Piece | Home | Also used by |
|---|---|---|
| Frame rates, SMPTE timecode (23.976–60, 29.97/59.94 drop frame) | `dorico-format::timecode` | dorigit listing (`model::timecode` delegates) |
| Tempo marks, gradual tempos, pauses, video, markers, play options decoded | `dorico-format::vocab` (`tempo_mark`, `gradual_tempo_mark`, `pause`, `video`, `marker`, `playback_timing`, `beat_unit`, `tempo_presets`) | dorigit listing (video, markers) |
| In the read model | `dorico-model`: `Tempo` (+ kind, unit, crotchet_bpm, equation, percent, reset, preset, event_id), `Flow.endings` (+ `times_played`), `Flow.pauses`, `Flow.video`, `Flow.markers`, `Score.playback` | f2d reviewer, dorico-hp, dorigit |
| Tempo map (Dorico's step function) | `dorico-timeline::tempo` | |
| Performed order | `dorico-timeline::performance` | |
| Flow/project timeline, MIDI ticks and tempo events, marker check | `dorico-timeline` (lib) | `doricokit.timeline` (PyO3 class `_native.Timeline`) |

## Encodings and behaviour

Evidence: **M** = matches Dorico 5's MIDI export event for event (ticks exact, tempo within
0.01) — `timeline-ref.dorico` flows 1, 2, 3, 5, 6, 7, the user's `bars-numbers-repeats.dorico`
and the ET score (184 tempo events); **K** = all 174 markers in 362 projects within 1 tick of
Dorico's stored clip time.

| Thing | Encoding / rule | Evidence |
|---|---|---|
| Absolute tempo | `data/absoluteTempo/tempoValue` = µs per **stated beat unit**; `beatUnits` = `{note value code, dots}` (8 = crotchet). ♩. = 60 → 90 crotchets/min | M, K |
| Metric modulation | `type kEquation`, `tempoEquation/left`, `right`, "old = new": × right / left (minim = crotchet halves the tempo) | M (flow 1) |
| Relative tempo | `type kRelative`, `relativePercent` of the tempo in effect. Dorico stores "meno mosso" as the **Mosso** preset at **110 %** (`modifierFlags` 8) and plays it faster; we follow Dorico | M (flow 7) |
| a tempo / tempo primo | `type kReset`, `resetType` `kATempo` (last absolute tempo) / `kTempoPrimo` (the flow's first tempo) | M (flow 7) |
| Gradual tempo | Start: Dorico's stored `initialTempo` when present (`automationDataPoint` true, Play-mode tempo edits; ET: 156.13 where the mark says 155), else the tempo in effect. End: `finalTempoPercent` of the start. **Steps of a quarter crotchet**: n = ⌊length / ¼⌋ (≥ 1), step k at start + k/4 with start + (end − start)·k/n; the final tempo begins at the ramp's end and stays | M (flows 2, 7, ET) |
| No tempo mark | 120 crotchets/min | M (flow 6) |
| Fermata | at p, note length L, E/S = elongation/silence % for its `fermataDuration` (`pausePlaybackOptions`, defaults very short 15/15, short 25/25, normal 50/50, long 100/100, very long 200/200, Henze short 25/25, long 100/100): [p, p+L/2) lasts L·(1+E), [p+L/2, p+L) lasts L·S | M (flow 3, all seven lengths) |
| Caesura | at p after a note of length L: [p−L, p−L/2) lasts L/2 + L·S (`caesuraSilencePercent`) | M (flow 3) |
| Breath mark | no extra time (shortens the note before; not a timing change) | M (flow 3) |
| Pause inside a gradual tempo change | ignored (Dorico help) | help |
| Jumps (D.C., D.S.) | **taken at the jump mark's own position**, not at the bar's end (a D.S. on beat 4 skips the rest of the bar); afterwards the tempo in effect at the target is restated | M (flow 5, bars-numbers-repeats) |
| Repeats | barlines `kStartRepeat`/`kEndRepeat`/`kEndAndStartRepeat`; a repeat back to the flow start replays a pick-up bar | M (bars-numbers-repeats) |
| Endings | `kRepeatEndingLineNumSegments`, `kRepeatEndingLineSegmentDuration` per segment (`propertyOffset "2:k:0:0"`), **`kRepeatEndingLineNumTimesPlayed`** = passes ("repeat 3 times" = 4, user 2026-11-01): first segment on every pass but the last ones, each later segment on one pass ("1.-3.", "4.") | encoding ✅; pass order not in a MIDI export yet (flow 4 exported no notes) |
| Plain repeat count (no endings) | not seen; 2 plays assumed | ❓ |
| To Coda | taken at its position after an "al Coda" jump (same rule as D.C./D.S.) | inferred |
| Video | `flowVideoData`: `videoAttachmentPosition`, `kVideoEventInTime` (clip time there), `kVideoClipTimecodeStart`, `kVideoClipFrameRate`; marker `timePosition` = clip time | K |
| Project frame rate | `timeDisplayPlaybackOptions/projectFrameRate` (`k24`, `k25` seen), `useDropFormat`, `showTimecode` | `k24`/`k25` ✅; other names ❓ (parser accepts `k2997`, `k23976`, `k2398`, `…Drop`) |
| MIDI ticks | Dorico's export rounds half ticks **up** (`midi_tick`); `Ratio::to_ticks` rounds to even (dorico-hp's convention) | M (ET) |
| Between flows | `gapBetweenFlowsSeconds` (5), `preRollBeforeFlowSeconds` (0) | ❓ (one flow per export) |

### Frame rates (user: support all, note what Dorico offers)

All of 23.976, 24, 25, 29.97, 29.97 drop, 30, 47.952, 48, 50, 59.94, 59.94 drop and 60 are
supported, plus any other whole or 1000/1001 rate. Pull-down rates run at exactly
base × 1000/1001 and count frames on the base. Drop frame exists only for 29.97 (2 frame numbers
skipped per minute except every 10th) and 59.94 (4). A drop request at any other rate gives
non-drop. Dorico's help says it supports 23.976 to 60 fps and labels drop-frame "dfps"; the
option names of rates other than 24/25 are still unseen (no 29.97 dfps copy was saved).

## Still open (caveats the code reports)

1. Endings with several passes and To Coda: encodings known, performed order not yet in an
   export (the flute in `timeline-ref.dorico` has no sound, so Dorico exported no notes for the
   flows without tempo changes). A re-export of flow 4 with a playback template applied would show it.
2. Count of plain repeats (no endings).
3. Fermata/caesura length for notes other than crotchets (the rule scales with the note's
   length; checked only on crotchets). Pauses on single staves are timed like whole-flow ones.
   Curlews and per-fermata overrides not seen.
4. Frame-rate option names beyond `k24`/`k25`; gap between flows.

## Tests

- `cargo test -p dorico-timeline`: repeats + endings (incl. 4 passes), D.S. al Coda and D.C. al
  Fine at the marks' positions, dotted beat + metric modulation, rit. steps + MIDI tempo events,
  timecode with video, ending-segment choice.
- `cargo test -p dorico-format timecode`: every rate, drop frame both ways (29.97, 59.94).
- `engine/crates/timeline/tests/real_files.rs`:
  - `tempo_events_match_dorico_midi_export` (runs whenever
    `engine/tests/dorico-check/timeline-ref-midi/` exists): 9 flows, event for event;
  - `markers_match_dorico` (`DORICO_REAL_FILES=1 … --release --test real_files -- --nocapture`):
    every project incl. Backup Projects and dorigit's refs; markers within 3 ticks (worst 1.00).
- `engine/tests/python/test_timeline.py`: the Python bridge on `ref-film-v1`.

## Reference files (Round method)

`engine/tests/dorico-check/make_timeline_ref.py` writes `timeline-ref.dorico` (flows 1–7, see its
docstring); the user added flow 7's relative tempos, a 50 % rit. and "repeat 3 times" in flow 4
and exported MIDI per flow to `timeline-ref-midi/` (2026-11-01), plus the bars-numbers-repeats
and ET exports. The ET export is git-ignored (third-party score).

## Next

1. Optional confirmations (open items 1–4).
2. Switch the consumers (needs the user's OK where output changes):
   - dorico-hp `model.py` `seconds`/`bpm_at`/`ms_per_crotchet` and `render.py` `to_ticks` and its
     tempo events: today they ignore beat units (♩. = 60 is taken as 60 crotchets/min), relative
     tempos, rit./accel., fermatas and repeats, and default to 100 bpm (Dorico: 120);
   - dorico-hp `smf.py` tempo maths belongs to the future `midi` module;
   - dorigit listing timecode could follow the project's drop-frame setting.
3. Position mapping between two versions (dorigit MERGE §7, M4): same module, later.
4. Swing / rhythmic feel (`defaultRhythmicFeel`) changes note timing, not tempo: dorico-hp's concern.
