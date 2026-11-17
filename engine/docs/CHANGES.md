# Engine changes

API and behaviour changes that tools must know about, newest first. Breaking changes need a
version bump of the affected interface (IR, findings) and a line here.

## 2026-11-01 (dorico-hp session: Dorico's playback dynamic levels)

Additive; golden unaffected.

- **New `doricokit.dynlevels`**: `level("mf")` → 0.5 (Dorico's playback level of a written
  dynamic; p letters −n, f letters +n, mp −0.5, mf +0.5), `accent=`/`marcato=` boosts
  (`accentDynamicDelta` 0.5 / `marcatoDynamicDelta` 0.8 by default), `curve(level)` → 0..1 in a
  map's range and `to_range(level, lo, hi)` / `from_range` (CC or velocity). Measured with the
  user's test I/I2 MIDI exports (`HPCaptures\dorico\test-I2`); the curve is for
  `dynamicCurveParams` 0.5, 2.5, 2.5 (the user's projects). Tests: `engine/tests/python/test_dynlevels.py`.
- These are also the values of Play mode's **Dynamics lane** (`AutomationEventDefinition`,
  `controllerDefinition` `kDynamic`, absolute; replaces Dorico's dynamics/humanise/beat stress
  inside a drawn span). Belongs with `dorico-playback` (S6) when that is built.
- First user: dorico-hp Apply now writes the Dynamics lane (`doricohp/lane.py`). Golden: the
  `dorico-hp/apply/{romantic,reapply,test-file-A}` cases re-recorded; checked that only
  `kDynamic` lane events were added (notes and CC1 identical, reports differ only by the
  "dynamics lane" notes); the velocity/timing/vibrato-only cases are unchanged.

## 2026-11-01 (Project E session: stagecraft, stage placement)

Additive; no existing API changed, golden unaffected.

- **New `dorico-format::mixer`**: `read_mixer(enginedata) -> Mixer` (VST rack + every channel:
  kind, name, `instrument_id`, fader `gain` (linear, None = not stored), inserts with slot,
  name/uid (None = empty slot), `enabled`, `post_fader`, sends with slot, `enabled`, `gain`);
  `Mixer::rack_slot`, `fx_channels`, `insert(id)`; `db(gain)`.
  `plugin_states(enginedata) -> Vec<PluginState>`: every saved plug-in state with its
  **owner** (XML `id` of the rack instrument or insert it belongs to), uid, raw data and, for
  VST2 plug-ins, the fxBank/fxProgram opaque chunk (`Vst2Chunk { kind, fx_id, chunk }`).
  Layout notes in the module doc and `stagecraft/docs/FORMATS.md`. Tests use synthetic data.
- `playback::mixer_xml` was already public; `mixer` reuses it.
- First user: `stagecraft` (new crate at `stagecraft/`, workspace member). Python binding not
  added yet (ask if a Python tool needs it).
- **`vi-render render --input I.wav`** (user's choice that the stagecraft session adds it): a
  WAV (PCM 16/24/32 or float, must match `--sample-rate`) is fed into the plug-in's inputs
  (file channel n → input n; mono → every input); the render lasts input + `--tail`;
  `--events` is now optional (effects). Prints the plug-in's latency (not removed). Nothing
  else changed; MIDI renders behave as before. Checked: an impulse through Virtual Sound
  Stage 2 (Clarinet 2 state, `--bank`) comes back at 192 samples = its reported latency.
  `doricokit.virender.render` doesn't expose `--input` yet (the Project C session's module).

## 2026-11-01 (Project B session: ad lib harp glissandi, playback model)

New Python modules (prototypes; Rust later with S9). All additive; golden unchanged
(`test-all.sh` green, dorico-hp unit tests OK). Design and evidence: PLANNED_WORK.md §4.9.

- **New `doricokit.midi`**: the SMF reader moved here from dorico-hp's `smf.py` **unchanged**
  (`read`, `Midi`, `NoteEv`, `CtrlEv`), plus `Midi.tick(seconds)` (inverse of `seconds`),
  `Midi.bar_start(bar)` / `Midi.tick_at(bar, crotchets)` (bars from the time signatures, bar 1 at
  tick 0), and a writer: `write(path, [Track], ppq=, tempos=, time_sigs=)`.
  `dorico-hp/doricohp/smf.py` is now a re-export, so `from doricohp import smf` still works.
  Still duplicated: dorico-hp `render.py` has its own SMF writer (`_vlq`, `_track`); it can move
  onto `midi.write` when the dorico-hp session next touches it (check: golden identical).
- **New `doricokit.harp`**: `Pedals` (`parse("Db C B | E F# G# A")`, `from_model(mark["detail"])`
  for the read model's "harp pedals" marks, `infer(pitches, doubles)`, printed as
  "D♭ C♮ B♮ | E♮ F♯ G♯ A♮"), `strings(pedals)` (47 strings C1–G7 with sounding pitches; enharmonic
  doubles included).
- **New `doricokit.gliss`**: ad lib harp glissandi as sweeps between turning points.
  `Sweep`, `AdLibGliss.notes()` (pedal-aware, even steps, `hang` on the last step, `skip`,
  `layer`, velocity breakpoints), `fit(notes)` (spec from played notes, pedals inferred),
  `compare`, `plan(start, end, pedals, low=, high=, first=, last=, pattern="DUDUD"/"UUU…")`,
  `select(midi, t0, t1)`; CLI `python -m doricokit.gliss fit FILE --start BAR[+CROTCHETS]
  --end … [--write/--replan OUT.mid] [--json]`. Checked on the user's trex-harp.mid: gliss 1
  regenerated 88/88 notes at 0 ms, gliss 2 201/202 (one crafted note outside the pedals).
- Tests: `engine/tests/python/test_gliss.py` (trex part skipped when HPCaptures is absent).
- Same day, after the user listened: `plan` plays as a harpist would. **`repluck` now defaults
  to False** (the turning string sounds once; the next sweep starts on the neighbouring string one
  regular step later). A wave stays in one hand (`layer` = hand) and overlapping same-direction
  restarts switch hands. New `physical_checks(g)` (turn sounding twice, more than two sweeps at
  once, a hand starting before it finished); `fit` adds them to its warnings. New
  `replan_args(g)`; `--json OUT` with `--replan` also writes `OUT-replan.json` (plan arguments +
  spec). The user's preferred results are fixtures in `engine/tests/gliss/*-pick.json`, checked
  to be reproduced exactly.

## 2026-10-31 (dorico-hp session: HP FLUTE print vs playback)

No engine code changed. Golden: the 16 `dorico-hp/*` cases re-recorded (`record --only
dorico-hp/`) after intended Apply/render changes, each checked: open hairpins read as local
swells and brillante ≈ 40 ms (main project identical note for note with the old settings);
passage words no longer taken from `pt.user.*` techniques and slur ends kept long (only the
ET strings with "B Spiccato" change). Details: dorico-hp/research/score-vs-playback.md.
2026-11-01: re-recorded again after removing SWAM "vibrato rate" curves on CC14 (= SWAM Main
Volume): only the 1,456 CC14 points left the main project's output; notes and CC1 identical.

## 2026-11-01 (timeline session: checked against Dorico's MIDI export)

The user's Dorico 5 MIDI exports (reference project, bars-numbers-repeats, ET) now match the
timeline event for event (9 flows; TIMELINE.md has every rule and its evidence).

- `dorico-timeline::tempo` rewritten as Dorico's step function: rit./accel. in quarter-crotchet
  steps from Dorico's stored `initialTempo` when present; fermatas (all seven lengths) and
  caesuras timed from the play options; breath marks add nothing; relative and reset tempos;
  default 120. `TempoMap::from_flow(flow, opts)`; `Segment` has no `ramp` any more.
- `performance`: jumps (D.C., D.S., To Coda, Fine) happen at the mark's position, not the
  bar's end; endings honour `times_played`.
- `FlowTimeline::tempo_events()` (no step argument; Python `tempo_events(flow)`) = Dorico's MIDI
  tempo track; new `midi_tick` (halves round up, as Dorico's export); `FlowTimeline::ticks` removed.
- `vocab::TempoMark`: `relativePercent` read, new `reset` (`kATempo`, `kTempoPrimo`), kind
  "reset". `dorico-model`: `Tempo.reset`, `Ending.times_played`
  (`kRepeatEndingLineNumTimesPlayed`; "repeat 3 times" = 4).
- New test `tempo_events_match_dorico_midi_export`; `.gitignore`: the ET MIDI export.

## 2026-10-31 (timeline session: `dorico-timeline`, timecode, film data in the model)

New module, design and evidence in [TIMELINE.md](TIMELINE.md). All additive; golden unchanged.

- **New crate `dorico-timeline`** (`engine/crates/timeline`): `TempoMap` (notated position <->
  seconds; absolute tempos with beat units, metric modulation, relative tempos, rit./accel.),
  `performance::perform` (performed order: repeats, endings, D.C./D.S., al Fine, al Coda,
  `playRepeats`, `playRepeatsAfterDS`), `FlowTimeline` (`seconds`, `occurrences`,
  `notated_seconds`, `at_seconds`, `clip_time`, `timecode`, `tempo_events`, `check_markers`),
  `ProjectTimeline` (flows with `gapBetweenFlowsSeconds`, pre-roll). Unconfirmed assumptions
  are listed per flow in `caveats`. Checked: all 174 markers in 346 user projects within 1 tick.
- **New `dorico-format::timecode`**: `FrameRate` (23.976–60, exact 1000/1001 pull-down rates,
  29.97/59.94 drop frame), `from_dorico("k2997", drop)`, `from_fps`, `format`, `parse`, `label`
  ("29.97 dfps"). dorigit's `model::timecode` now delegates to it (same output).
- `dorico-format::vocab`: `beat_unit`, `tempo_presets`/`TempoPreset`, `tempo_mark`/`TempoMark`
  (kind, bpm of the stated unit, `unit`, `crotchet_bpm`, `bpm_max`, `equation`, `percent`),
  `gradual_tempo_mark`, `pause`/`Pause` (`kind`, `fermata_duration`, `name`), `video`/`Video`
  (moved from the listing's private `read_film`, which now uses it), `marker`/`Marker`,
  `playback_timing`/`PlaybackTiming` (repeats, pauses, flow gap, pre-roll, frame rate, drop).
- **Fix** `vocab::pause_name` and the model's pause marks: `pauseType`/`fermataDuration` sit
  under `pauseData`, so pause marks had an empty type and name ("fermata (very long)" now).
- `dorico-model` (additive): `Tempo` gains `event_id`, `kind`, `unit`, `crotchet_bpm`, `bpm_max`,
  `equation`, `percent`, `preset` (**note**: `bpm` is per *stated* beat unit: ♩. = 60 has bpm 60
  and crotchet_bpm 90); `Flow.endings` (`Ending` with segment lengths), `Flow.pauses` (whole-flow
  fermatas etc.), `Flow.video`, `Flow.markers` (REQUESTS.md "film data" row);
  `Score.playback` (`PlaybackTiming`).
- `doricokit.timeline` (new; PyO3 class `_native.Timeline`); `doricokit.model` converts
  `segments` and `equation` to Fractions.
- `engine/tests/dorico-check/make_timeline_ref.py` -> `timeline-ref.dorico` (reference project
  for the user to export from Dorico; steps in that folder's README.txt).
- `test-all.sh`: clippy includes `dorico-timeline`; new `engine/tests/python/test_timeline.py`.

## 2026-10-31 (engine session 3: one copy of every decoder; findings v2)

User's goal: every decoding and readable name exists once in the engine and every tool uses
it ("unintended decoherence" is what the engine is meant to avoid).

**New `dorico-format::vocab`** (Dorico's vocabulary, the start of MODULE_REVIEW §4 #1):
`clean_value`, `variant_tokens`, `variant_ints`, `glyphs` (♭♯♮), `humanize`, `rich_text`,
`event_text`, `player_name`, `tempo_bpm`, `technique_appearances` / `TechniqueAppearance {name,
text, technique}` / `technique_name` (library `name` first; `text` can be an internal key),
`tuplet` → `Tuplet {num, den, note_value, dots, unit, name}`, `note_value_length/_name`,
`key_signature` → `Key {fifths, mode, tonic, name}` (major/minor/atonal; custom keys counted from
their accidentals), `ARTICULATIONS`, `ARTICULATION_PROPERTIES`, `articulation_name`, `clef_name`,
`ottava_name`, `ornament_name`, `arpeggio_name`, `glissando_line_name`, `pause_name`,
`divisi_name`, `spell`, `accidental_text`, `pitch_name`, `duration_name`; Dorico version forms:
`event_muted` (`true` = `kAlways`), `glissando_playback` (absent = `kChromatic`).

- `dorico-format::dynamics`: now also holds `decode_intensity` (moved from `model`) and a machine
  decoder `level(sub) -> Level {kind, level, extra, duration}` (what `dorico-model` had privately,
  incl. its 4-entry combined table, now derived from the same code as `describe`: combined
  dynamics beyond fp/ffp/fpp/pf get names such as "mf-mp" instead of "kDown0/0").
- `dorico-format::tree::element_tables` / `ElementTables` (was copied in `model` and `dorico-model`).
- `dorico-format::model` (dorigit's listing): its private decoders are gone; `clean_value`,
  `decode_intensity`, `pitch_name`, `duration_name` are re-exported from `vocab`/`dynamics` so
  old imports still compile (use the new paths in new code).
- `dorico-model` (all additive; existing fields unchanged): `Player.label` and
  `Part.player_label` (glyph tokens as ♭♯♮; `name`/`player_name` stay raw), `Flow.keys`
  (`KeyChange {pos, event_id, fifths, mode, tonic, name}`; `key_changes` kept), `Mark.name`
  (readable: technique, tuplet, clef, ottava, arpeggio, ornament, pause, divisi, pedal, line, key,
  glissando line), `Mark.tuplet`, `Mark.key` (stave-local keys, e.g. open-key staves in the Rite
  of Spring), `DynamicItem.name` (= `dynamics::describe`; `level` stays the machine value),
  `Note.muted`. New mark kinds instead of raw Dorico names: `key` (was `TonalityDivision`),
  `ornament` (was `Ornament`), `pause`, `line` (was `HorizontalLine`; detail style, placement,
  attachments), `bar rest` (was `BarRest`), `stave count change` (was `StaveCountChange`).
  Glissandi gain detail `from_event`, `to_event`, `playback`. `ARTICULATIONS`, `event_text`,
  `technique_appearances`, `TechniqueAppearance` are re-exports from `vocab` (now public).
  `Mark::plain(...)` constructor.
- `doricokit.model`: `unit` (tuplet note length) converts to `Fraction`.
- `doricokit.view`: staff labels come from the model's `player_label` (its own ♭ code is gone);
  `Note.event`, `Staff.stave_id`, `Flow.id`, `Flow.bar_label(pos)`.
- dorigit-core (caller switches, agreed with the dorigit session): `listing.rs` and
  `notation.rs` use `vocab` and the model's keys, tuplets, dynamic names; their copies of
  technique names, tuplet decoding (×2), key decoding, glyphs (×2), humanize, rich text, divisi,
  ottava/arpeggio/pause/ornament names and pitch spelling are gone. Notation keys now come from
  the flow's global keys only (before, a stave-local open key at the same position could win).

**Findings format v2** (`doricokit.findings`, `FINDINGS_VERSION = 2`), additive: every v1 field
keeps its name and position; new optional `tool` (owner of the check/rule, default
"doricokit"), `flow_id`, `bar` (Dorico's bar number, "35a"), `beat` (exact, "5/2"), `staves`
(Dorico stave IDs), `events` (Dorico event IDs of the items concerned), `change: {before, after}`
(rules only; left out otherwise). JSON reports gain `"findings_version": 2`. New
`Finding.to_dict/from_dict`, `findings.from_json` (reads v1 and v2), `owner_of`.
`Reviewer.add(..., staff=, events=)` and `Cleaner.change(..., staff=, events=, change=)`; shared
`review.located(...)`. Every built-in check and rule fills them; f2d's "not-converted" gets
`tool: "finale2dorico"` and no events (it comes from the converter's report).

Tool output: dorigit and dorico-hp golden identical; f2d text output identical; f2d
`review.json` (40 review + 8 convert cases) gains the v2 fields only (checked: v1 fields equal
finding for finding, 18,657 findings); re-recorded with the user's OK. Combined dynamics beyond
the old 4 now have names in `DynamicItem.level` ("ff-mp", HP BRASS TEST horns): no reviewer
message changed; `tests/parity/model_vs_python.py` translates the old reader's raw form.

## 2026-10-31 (dorigit session: tidy diff, ♭ names)

- No engine code changed. dorigit's listing shows player names with ♭/♯/♮ instead of
  `{@flat@}` tokens, and dorigit's diffs drop rename-only moves and newer-Dorico format noise
  (`dorigit-core/src/tidy.rs`). Golden: 9 `dorigit/show/*` cases re-recorded (token swaps only).
- For the engine (optional): `diff::event_changes` matches events across versions by player
  *name*, so a rename turns every event into "moved"; matching by player id would fix it at
  the source for all tools.

## 2026-10-31 (dorigit session: listing names, golden)

- No engine code changed. dorigit's listing now comes from `dorigit_core::listing::build`
  (`build_score` + readable names for techniques, tuplets, clefs, text, divisi, ottavas,
  ornaments, arpeggios, pauses, note articulations), using `dorico_model::ARTICULATIONS`.
  Golden: the 37 changed `dorigit/show/*` cases re-recorded (`--only dorigit/`); every change is
  an in-place rewrite of a line at the same bar/beat. f2d and dorico-hp cases untouched.
- Found for the read model (REQUESTS.md): technique appearances should prefer the library
  `name` over `text`; `text` can be an internal key ("opentext").

## 2026-10-31 (finale2dorico session: shared reviewer, cleaner, edit layer, findings)

At the user's request (2026-10-31: tools must be modular, usable by house styles and the
others), four Python modules moved from finale2dorico into `doricokit`; f2d keeps thin
wrappers (`f2d/review.py`, `f2d/clean.py`, `f2d/dorico/read.py`) and its commands are
unchanged. Golden: all identical (71/71 fast set, f2d 54/54).

- `doricokit.findings` (new): one `Finding` type for checks and rules (FINDINGS_VERSION 1 = the
  reviewer's existing shape) and a **registry**: `register_check(name, description, fn,
  scope="staff"|"flow"|"project")`, `register_rule(name, description, fn, default=False)`.
  Registration order = run and report order. Tools add their own (f2d registers
  "not-converted").
- `doricokit.view` (was f2d/dorico/read.py): the reviewer's view over `doricokit.model`, now
  with dynamics-group event IDs and `Staff.marks` (trills/techniques with event IDs);
  `read_bytes`, `from_model`. Player labels show ♭/♯/♮ instead of `{@flat@}`.
- `doricokit.review` (was f2d/review.py): the reviewer's checks, registered; `section_clusters`
  shared with the cleaner; `Reviewer.run(only=[...])`.
- `doricokit.edit` (new): **Python prototype of the S5 edit layer**: `Project.open/to_bytes/save`
  (only the score re-encoded; no change -> original bytes; never over the source; `ids.check`
  before saving), `FlowEdit` (events and dynamics elements by ID, `remove_event`,
  `link_dynamic_group`, `event_content`, `dynamic_group_content`), `canon`/`same` (content
  without IDs; default-valued properties and both empty-list forms equal). Meant to be replaced
  by the Rust `dorico-edit` crate with the same operations.
- `doricokit.clean` (new; was f2d/clean.py): the cleaner, rules `dedupe` and `link` registered
  as default rules; `clean()`, `after_check()`, `format_text()`, `to_json()`.
- Tests: `engine/tests/python/test_clean.py` (no-op byte-identical, never overwrites, cleaner
  on sample A, a third-party rule and check through the registry).

## 2026-10-31 (dorigit session: harmonics)

- Listing: notes with `kNoteHarmonicType` / `kNoteHarmonic` read "B4 dotted minim, artificial
  harmonic (partial 4)"; those two properties leave `props`. The number is the partial
  (confirmed by the user on the Rite of Spring: int 5 = partial 5). No golden changes (no golden
  project has harmonics).

## 2026-10-31 (dorigit session: film)

- Listing (`model::build_score`): new `Flow.video` (text, omitted when no video): "clip.mov at
  bar 2 beat 1, clip from 00:00:06:00 (timecode 01:00:06:00), 25 fps". Markers are now kind
  `marker` with text `"name" at HH:MM:SS:FF` (+ " (important)"); their text/important
  properties are no longer repeated in `props`. New `model::timecode(secs, fps)` (non-drop).
  Encodings confirmed by the user with `dorigit/research/refs/ref-film-v1/v2.dorico`
  (`videoAttachmentPosition` = start in the flow, `kVideoEventInTime` = offset into the clip,
  `kVideoClipTimecodeStart` = timecode of clip frame 0, marker `timePosition` = clip time).
- `diff`: prints `   video: …` under a flow's meters; `FlowDiff.video` = (old, new) when the
  picture settings change ("none" when absent), shown as `~ video: …`.
- No golden changes (no golden project has video or markers). The shared read model
  (`dorico-model`) doesn't have film data yet; see REQUESTS.md.

## 2026-10-30 (dorigit session: dynamic modifiers)

- `dorico-format::dynamics`: immediate-dynamic modifiers by name: `intensityModifier` =
  `{amount: 2=poco, 4=molto}, {1=meno, 2=più}` ("poco f", "molto più p"); unseen values stay
  readable ("f (modifier …)"). Force and gradual dynamics show a modifier raw if one ever
  appears (none seen; Dorico omits the field when unset). Source: the user's
  `dorigit/research/refs/ref-dynamics-divisi.dorico`, mapping confirmed by the user.
- `model::decode_intensity`: "p possibile" confirmed (`{int: 1}, {int: 1}, …`). Possibile is a
  **standard** Dorico modifier allowed only on f or p (user correction: not an error in ET);
  possibile combined with mezzo or a letter count now gives the raw form, so callers show
  "custom dynamic (…)" instead of silently dropping the possibile.
- `model::variant_tokens` is now `pub(crate)`. No golden changes (no corpus file has modifiers).

## 2026-10-30 (dorigit session: dynamics)

- New `dorico-format::dynamics` (`describe`, `describe_group`): every dynamic Dorico offers by
  default named in full: force levels (ffz, rffz, sffz), sf/rf (no-z property), combined
  dynamics (fp, ffp, fpp, pf, mf-mp, ff-mp…), subito on any dynamic, messa di voce, niente
  (dal/al), poco a poco, flared hairpins. Anything unrecognised reads "custom dynamic (…)"
  instead of raw encoding (user decision 2026-10-30: support custom dynamics, never create them).
  Dynamic modifiers (poco/molto/più…) are shown raw as "(modifier …)" until a reference file
  shows their encoding.
- `dorico-format::model` (dorigit listing) uses it. Golden: the 15 `dorigit/show/*` cases
  re-recorded (only dynamic lines changed: sfz->sffz, combined->fp/ff-mp…, subito, messa di voce,
  al niente). `dorico-model` (f2d reviewer, dorico-hp) is unchanged; adopting the shared decoder
  there is open (`REQUESTS.md`).

## 2026-10-30 (session 2)

- New `doricokit.listing.read(path)` (PyO3 `listing_json`): dorigit's listing model
  (`dorico-format::model`: events with owner/lane/bar/beat, players, flattened options) for
  Python research scripts. Used by `dorigit/research/merge_probe.py`.
- `dorigit/prototype/` deleted; the `listing_matches_python_prototype` test and the
  `DORIGIT_PY_PARITY` switch are gone. Listing regressions are caught by the golden tests.
- `golden.py`: the test files are always `corpus.test_files` (no fallback to the prototype).

## 2026-10-29 (session 1, cont.: tool switches)

- `dorico-format::bars` (moved from dorico-model): `Bar` gains `number`, `sub`, `label`
  (Dorico's displayed bar number: pick-up = 0, bar-number changes); `compute_bars(divisions,
  changes, end)`; `read_division`, `NumberChange`, `bar_at`, `letters`.
- `dorico-format::model` (dorigit listing): bar numbers in `where`/`bar` and meters now follow
  Dorico (pick-up = bar 0, bar-number changes, "35a"); `Flow.bars` (not serialised).
- `decode_intensity`: `{int: 0}, {int: 1}, {bool: false}, {}` -> "f possibile".
- `dorico-model`: `Score.instruments` (entity -> name + ranges), `Stave.divisi`,
  `Voice.stave_id`, `Flow.bar_number_changes`, `Flow.repeats` (segno, coda, jump, ending).
- `doricokit.container.open_score(path)`.
- finale2dorico now uses `doricokit` (codec, container, model); `f2d/dtn.py` is gone.
- dorico-hp `notation.py` and f2d `read.py` are views over `doricokit.model`.

## 2026-10-29 (session 1)

- `dorico-format` moved from `dorigit/crates/` to `engine/crates/`; the Cargo workspace is the
  repo root.
- `dorico-format::container`: folder entries flagged deflated are now written deflated (as
  Dorico writes them) instead of stored. File entries unchanged.
- `dorico-format`: new `tree` (element/array builders, `push_child`, `insert_child`,
  `remove_children`, `set_text`, `array_items`, `props::{entries,get,get_int,set,entry,table}`,
  `event_head`), `ids` (`next_id`, `counters`, `max_used`, `check`), `ratio::TICKS_PER_CROTCHET`,
  `Ratio::{to_ticks, from_ticks}` (half-to-even rounding).
- New crates: `dorico-paths` (host/WSL paths, Dorico install and user data, corpus),
  `dorico-model` (read model), `doricokit-py` (Python bridge).
- New Python package `doricokit`: `format` (drop-in for the old `dtn.py`), `container`,
  `positions`, `ids`, `model`, `paths`.
- dorico-hp now imports `doricokit` (codec, container, positions); its `dtn.py` is gone.
