# Version control for Dorico: research notes

*25 Oct 2026. Based on 46 real projects (Dorico 2.0.5 to 5.1.60) from your Dorico Projects, Downloads and the Dorico example projects.*

> Session 1 research, kept as the record of how the format was worked out. Option B in §7 was chosen and is now implemented in Rust (see [DESIGN.md](DESIGN.md)). §6 playback handling was refined: playback is kept when the *plugin setup* changes (DESIGN.md §6). Current state: [STATUS.md](STATUS.md).

## TL;DR

- **The file format is cracked.** A `.dorico` file is a zip. The score inside is either plain XML (`score.xml`) or a compact binary form of that same XML (`score.dtn`). I wrote a decoder and encoder. All 88 `.dtn` files in your projects decode, and re-encode **byte-for-byte identical**, both directly and via XML text. So we can read *and write* Dorico projects.
- **Diffs are meaningful at the music level.** Notes, dynamics, articulations, players, layouts and options are all addressable by stable IDs. A prototype diff of "Harry Potter Cues Plus 4 → 5" reports, in musical terms, exactly what you changed (see §3).
- **Git integration works today.** With `dorigit setup-git`, `git diff`, `git log -p` and any git GUI show `.dorico` changes as music ("bar 19 beat 1 dynamic ff → fff", hunk header `### Flute 1`).
- **Storage: the music is cheap, the playback state is not.** In git, 6 versions of a 25 MB score cost about 0.7 MB for the score. The VST plugin state (`enginedata`, e.g. Kontakt) is about 20 MB per save and doesn't compress between versions. It needs its own policy.
- **Dorico's own extensibility is weak.** Lua is limited to macros, with no data access. The Remote Control API (WebSocket, Dorico 4+) can *send commands* (save, open…) but can't read the score. So the right shape is a **companion app that works on the saved files**, optionally nudging Dorico through the Remote API.

---

## 1. What's inside a `.dorico` file

A zip in OCF layout (the EPUB/ODF container standard). From one of your projects:

| Entry | Example size | What it is | Diffable? |
|---|---|---|---|
| `score.dtn` / `score.xml` | 4 MB binary, 25 MB as XML | The whole project: music, players, flows, layouts, options | Yes, once decoded |
| `scorelibrary.dtn` / `.xml` | 0.6 MB, 2.4 MB as XML | Project-local styles: fonts, paragraph styles, playing techniques… | Yes |
| `supplementary_data/vstaudioengine/enginedata` | 2–25 MB | Mixer (XML) + audio device (XML) + **opaque VST plugin states** | Partly (the XML parts) |
| `supplementary_data/preview/preview.{pdf,png}` | 0.1–0.7 MB | First page, written by Dorico 4+ | No, but **free thumbnails** for a history timeline |
| `supplementary_data/workspace/workspace.xml` | ~1 KB | Window/UI state | Noise |
| `META-INF/container.xml` | 270 B | Points at `score.dtn` or `score.xml` | n/a |

### The DTN format (fully decoded, see [dtn.rs](../../engine/crates/dorico-format/src/dtn.rs))

```
u32 4, u32 1
u32 nKeys    + NUL-terminated tag names   (first-use order)
u32 nValues  + NUL-terminated values      ("" first, then first-use order)
u32 nNodes   + node records in pre-order (node 0 = root)
  node: type byte, then LEB128 varints
    leaf:     key, value
    element:  key, 0, nChildren, childIndex...
  type bit 1 = element, bit 0 = array="true", bits 2-7 = a per-file constant (meaning unknown; preserved)
```

It is a lossless binary encoding of the same tree as `score.xml`. Your earlier RLE attempt was the right instinct but the wrong scheme: it's string tables plus varints.

**Interesting clue:** Steinberg's own "Bach – Fugue 16" example ships as `score.xml`, and its `filePath` is `/Users/daniel/git/mono/steam/resource/examples/…`. Steinberg appear to keep example projects **in git, as XML**. Dorico evidently loads XML-form projects, which the test file B (§9) will confirm for your version.

### Format stability
A Steinberg developer has said the format changes "frequently" (any new option is a format change). The design copes with this: the codec is **schema-agnostic** (it knows nothing about notes or flows), so new options flow through untouched. Only the musical-diff layer reads the schema, and it degrades gracefully when something is unrecognised.

## 2. The score data model (cheat sheet)

```
kScore
├─ info                      title, composer, created/saved dates & versions
├─ scoreOptions              engraving/notation/note-input options (≈ Engraving Options dialog)
├─ library                   project-level defs
├─ scorePlayers[]            playerID, displayName, instruments[]
├─ flows[]
│   ├─ flowPlayers[]         player → eventStreamID, staveStreamIDs, voiceStreamIDs
│   ├─ elementTables[]       shared defs: BarDivision (time sigs), DynamicGroup, Slur, Lyric, Tonality
│   ├─ blocks[]              blockID + events[]
│   │     NoteEventDefinition: eventID, position, duration, pitch(MIDI), propertyTable
│   │     DynamicGroup / Slur / Tuplet / Clef / PlayingTechnique / Tempo / Rest / GraceNote ...
│   ├─ blockInstances[]      place a block on a stream at a position
│   └─ eventStreams[]        kGlobalTimebaseStream | kPlayerStream | kInstrumentStaveStream | kVoiceStream
├─ layouts[]                 full score + parts: layout options, players, frame chains
└─ playModeData              playback (tracks, expression maps, automation)
```

- **Time** is an exact fraction in **crotchets** (`1/4` = semiquaver). Positions are absolute within the stream, so bar:beat comes from the time signatures in the global stream.
- **Pitch** is MIDI, at concert pitch. Spelling is a `kNoteSpelling` property holding the letter.
- **Properties** (articulations, stem direction, accidental visibility…) are `propertyTable` entries, optionally scoped to one layout.
- **Every event has a stable `eventID`** that survives saves. That's what makes precise matching possible.
- **Dynamics**: `intensity = {int: 0=f / 1=p}, {}, {bool: mezzo}, {int: number of f's or p's}`. So `{0},{},{false},{3}` = fff, `{0},{},{true},{}` = mf, `{1},{},{true},{}` = mp (all confirmed in Dorico). Force dynamics (sfz, rfz, mfz, fz) are stored by name in `ForceDynamicDefinition/type`. "f possibile" (`{0},{1},{false},{}`) and "p possibile" (`{1},{1},{false},{}`) decode. **Possibile is a standard Dorico modifier, allowed only on f or p** (user, 2026-10-30; an earlier note wrongly called the ET one an error). Modifiers: `intensityModifier = {amount 2=poco / 4=molto}, {1=meno / 2=più}` (confirmed by the user, `research/refs/ref-dynamics-divisi.dorico`). *Correction 2026-10-25: this note first had f and p swapped.* *2026-10-29:* `{0},{1},{false},{}` (second slot set, no count) is Dorico's **f possibile** (user, ET test file A); counts of 7 and 8 occur too (`{int: 7}` = fffffff).

### Film and divisi (2026-10-30, from copies of two of your projects)

**Film** ("BLACK LABEL", Dorico 3.5 project, 4 flows on one picture):
- `flow/flowVideoData`: `hasVideoAttached`, `videoFilename` (absolute Windows path),
  `videoAttachmentPosition`, and properties `kVideoEventInTime` (1m1: 23.56 s),
  `kVideoClipTimecodeStart` (1m1: 3617.56 s = 01:00:17:14 at 25 fps), `kVideoClipDuration`,
  `kVideoClipFrameRate`. The difference of the two times is the same for 1m1, 1m2 and 1m2 1
  (3594 s). **Settled 2026-10-31** (`research/refs` film v1/v2, confirmed by you):
  `videoAttachmentPosition` = where the picture starts in the flow (crotchets),
  `kVideoEventInTime` = video start offset (seconds into the clip), `kVideoClipTimecodeStart` =
  timecode of the clip's first frame. Markers' `timePosition` is **clip time**; Dorico shows
  timecode start + clip time, and recomputes the beat `position` when tempo or picture moves, so
  markers follow the picture. Edited markers keep their eventID.
- Project frame rate: `playbackOptions/timeDisplayPlaybackOptions/projectFrameRate` (k25), drop
  frame flag beside it.
- Markers: `MarkerEventDefinition` in the flow's global-timebase block, next to tempo and bar
  divisions. `position` (crotchets), `timePosition` (seconds, 6 decimals), properties
  `kMarkerText` and `kMarkerIsImportant`. 1m2 has hit-point runs ("BEAT B1"…"B5", 0.52 s apart).
  dorigit's listing shows markers by name with timecode, and a `video:` line per flow (2026-10-31).

**Divisi** ("Have Yourself A Merry Little Christmas"):
- `DivisiEventDefinition` in the instrument's stave stream (`kInstrumentStaveStream`): `sections`
  holds one `section` per division (label text "1", "2"), plus `soloists`, `soloistGroups`,
  `sectionsGroups`, `groupNameVisibility`, `sectionNumberVisibility`.
- Each extra section has its own `staveStreamInfo` with `divisiIndex/index` = 0, 1… (normal
  staves: -1) and its own voice whose `defaultLogicalStaveID` is that stave. dorigit's listing
  shows them as "[stave 2]" / "[voice 2]"; naming them "section 2" needs the divisi index.
- **Settled 2026-10-30** (`research/refs/ref-dynamics-divisi.dorico`): unison = a divisi event with
  empty `sections`; a soloist split = `soloists` + `sections`; Dorico reuses the one extra stave.

### Listing names (2026-10-31)

- Tuplets: `tupletDefinition` = `{n}, {m}, {list: {note value}, {dots}}, {bool}`; note value 8 =
  crotchet, 7 = quaver, 6 = semiquaver, 5 = demisemiquaver (each step halves; checked against
  tuplet lengths in the Rite of Spring). Listed "3:2 quavers".
- Playing techniques: the library's `name` ("Open (remove mute)") is readable; `text` can be an
  internal key ("opentext").
- Divisi: see `research/refs/README.md`; listed "1 / 2", "unison", "Solo + gli altri".

### Dorico 4.3 vs 5.1, and harmonics (2026-10-31, Rite of Spring, from copies)

The user's Rite of Spring Part I was last saved with **Dorico 5.1.60** (`fileVersion` 1.1299);
two of its flows were exported by the engraver with **Dorico 4.3.30** (`fileVersion` 1.1143).
Same music, two versions:
- Every event matches (8,957 and 5,979 events), with the **same eventIDs**: exporting a flow
  keeps IDs, which helps cross-project inserts (MERGE.md §6.2).
- What Dorico 5 rewrote on re-save (pure format "upgrade noise"):
  - instrument names use glyph tokens: "Clarinetto piccolo (E Flat)" → "(E{@flat@})";
  - "Clarinetto basso (B Flat)" → "Clarinetto basso" (Dorico 5's naming);
  - `kEventMuted` `true` → `kAlways` (bool became an enum);
  - every glissando gains `kGlissandoPlaybackType` = `kChromatic`;
  - options: `barNumberNotationOptions/useGlobalDivisionsMapForBarNumbers` and the plugin
    rack's `programContents` bank/program fields are gone; many new options appear
    (note-expression, pause, chord-symbol, space data in Play mode, `pageSequenceOverrides`).
  - dorigit's diff should recognise a "saved with a newer Dorico" change and group these
    (STATUS.md B11).
- **Harmonics** (6 notes, "The Dancing Out of the Earth" bar 4): note properties
  `kNoteHarmonicType` = `kArtificial` (natural presumably `kNatural`) and `kNoteHarmonic` =
  **partial number** (int 5 = partial 5, confirmed by the user in Dorico). Listed as "D3 dotted
  minim, artificial harmonic (partial 5)". Spring Rounds has none; its harmonics are playing
  techniques (`pt.artificialHarmonic`, `naturalHarmonic`).

## 3. How readable are real revisions?

`python3 -m dorigit diff "Harry Potter Cues Plus 4.dorico" "Harry Potter Cues Plus 5.dorico"`:

```
Flow: Quidditch 2004  (25 changes)
  Trumpet (B Flat) 1
    ~ bar 16 beat 3 [voice 1] note B5 quaver: removed ArticulationDuration=kStaccatoTenuto
    ~ bar 18 beat 3+1/2 [voice 1] note B5 quaver: removed ArticulationDuration=kStaccatoTenuto
  Flute 1
    ~ bar 19 beat 1 dynamic: ff -> fff
  ...
Score options: 2 changes
  engravingOptions/fingeringEngravingOptions/verticalGapBetweenCoincidentFingerings: 1/4 -> 1/8
```

`Obi-Wan → Obi-Wan 2` shows players renamed, removed and added, a *rit.* moved from bar 34 to bar 32, and whole part layouts added and removed. `Have Yourself… 2 → 3` shows a note respelled from A♭ to A♮ in bar 7, a quintuplet replaced in bar 20, and so on.

**Noise sources** to filter: `lastSavedDate`, `filePath`, `originalSourcePath`, `workspace.xml`, previews, and `enginedata` (it changes on every save, even when nothing in playback changed). If a note is deleted and re-entered identically it gets a new ID. The diff cancels these out.

## 4. Storage experiment

6 consecutive versions of "Harry Potter Cues" (128 MB of `.dorico` files) committed to git, after `git gc --aggressive`:

| Approach | Repo size |
|---|---|
| Raw `.dorico` files | 104 MB |
| Exploded (XML + raw extras) | 94 MB |
| …of which the **score + library XML** | **~0.7 MB** (15–45 KB per new version) |
| …of which **enginedata** | ~93 MB |

Zip compression defeats git's delta compression, which is why raw files barely shrink. Exploding fixes that for the music. `enginedata` is different: content-defined chunking finds only **2.6%** shared bytes between two saves a day apart. The Kontakt and VSS plugin states are re-serialised in a proprietary, high-entropy form on every save. Your "SILENT" copies (4 MB vs 24 MB) are you already working around this by hand.

**Options for enginedata** (pick per project, or per snapshot):
1. **Keep only at milestones.** Auto-snapshots store the music and reuse the last milestone's `enginedata` on restore. The music is exact; the mixer/plugin state may be slightly older. (Recommended default.)
2. **Keep always.** Simple, but about 20 MB per save for an orchestral project with Kontakt.
3. **Separate playback variants:** see §6. The playback setup becomes its own versioned thing that you switch between.
4. Further R&D: split `enginedata` into chunks (mixer XML, audio XML, per-plugin blobs) and dedupe per plugin by hash, so unchanged plugins cost nothing. This only helps if a plugin's bytes are stable when its settings didn't change; the 2.6% figure suggests Kontakt's aren't.

## 5. Ways to hook into Dorico

| Mechanism | What it can do | Use for |
|---|---|---|
| **Watching the saved file** | Everything we need for history. Dorico writes the whole project on each save. | Core trigger: snapshot on save |
| Dorico **Backup Projects** folder | Dorico already keeps the last N saves per project (default 5) | Import existing history; safety net |
| **Remote Control API** (WebSocket on localhost ~4560, Dorico 4+, session-token handshake) | Send any internal command (`File.Save`, `File.Open?File=…`, …) and read app status and the current selection. Can't read the score. Reports say the handshake changed in 6.x. | "Save & snapshot" button; "open this version in Dorico"; knowing which project is open |
| Lua scripts (Script menu) | Replay recorded macros. No data access, no UI. | Not useful here |
| MusicXML export | Lossy (no layouts, options, playback) | Optional: render visual diffs with an engraver |

Community references: [Dorico.Net](https://github.com/scott-janssens/Dorico.Net) (C# Remote API client), and Dorico MCP servers on glama.ai, which wrap the same API.

## 6. Product ideas

Your Dorico Projects folder shows exactly what the tool should replace:

- **Linear revisions:** `Harry Potter Cues`, `… Plus`, `… Plus 2`, `3`, `4`, `5`; `Obi-Wan`, `Obi-Wan 2`
- **Experiments:** `… TEST`, `… + string test`, `HP BRASS TEST`
- **Playback variants of the same music:** `… (SILENT)`, `… (VSS)`, `… IB`, `… + LASS3`
- **Template work:** `… - TEMPLATE WORK`, `Full Orchestra Template NEW FULL v5`

Git concepts, translated into musician terms:

| Git | In the app | Notes |
|---|---|---|
| commit (auto) | **Snapshot**: every save, automatic and silent | Like Time Machine. No messages needed. |
| commit + tag | **Milestone**: "Sent to orchestrator", "v2 approved by director" | Has a name, keeps the full playback state |
| branch | **Alternate**: "Darker ending", "Strings-only" | Try ideas without "Copy of…" files |
| diff | **What changed**: per flow → player → bar | Plus thumbnails from `preview.png` |
| checkout | **Open this version**: written as a *new* `.dorico` file, then opened via the Remote API | Never touches the open file |
| blame / log -L | **History of this bar**: "when did bars 16–18 of the trumpets change?" | Easy to add once events are indexed |
| merge | **Bring over…**: a flow, a player's part, or non-conflicting edits from an alternate | Possible because we can write files (test D proves the path) |

Ideas specific to Dorico:
- **Playback variants as a first-class concept.** Keep one history of the *music* and swap the *playback setup* (NotePerformer / VSS / Kontakt / silent) independently. That solves the SILENT/VSS/LASS3 file sprawl.
- **Cue workflow (film/TV):** label milestones with picture versions ("cut v3"), and compare "what changed since the last spot session" across all cues.
- **Parts safety:** "What changed in the Horn 2 part since parts went out?" Per-player diff filtered to one layout.
- **Visual diff, later:** shade the changed bars on the preview PDF, or render the old and new versions side by side via MusicXML export and an engraver (Verovio).

## 7. Architecture options

**A. Pure git + textconv (works now).** `dorigit setup-git` and you're done. Every git tool shows musical diffs. Weaknesses: you have to commit by hand; each version costs the full `.dorico` size; no thumbnails or restore UX.

**B. Companion desktop app over git (recommended).**
```
Dorico ──save──▶ MyCue.dorico  (stays the real working file; Dorico owns it)
                     │ file watcher (debounced, waits for zip to be complete)
                     ▼
            ┌──────────────────────┐
            │ snapshotter          │ explode → score.xml, scorelibrary.xml,
            │                      │ extras; enginedata per policy (§4)
            └──────────┬───────────┘
                       ▼
            .dorigit/ (hidden git repo per project folder, via libgit2/dulwich)
                       ▲
            ┌──────────┴───────────┐
            │ UI: timeline + thumbnails, musical diff, milestones,
            │ alternates, "open this version" (rebuild → new file → Remote API File.Open)
            └──────────────────────┘
```
- Runs **natively on Windows/macOS**, where Dorico runs. WSL can't watch Windows files efficiently.
- Stack: **Tauri** (Rust core + web UI) is light and cross-platform. The DTN codec is about 150 lines and ports easily. Alternatively Electron + a Python/TS core. The git layer is libgit2 (`git2-rs`) or the git CLI, so the repo is still a normal repo you can open in any git tool.
- Dorico's own file stays the source of truth. The tool only *reads* it, and only *writes* new files.

**C. A custom VCS / database.** Not worth it: git already handles content addressing, deltas, branches, and the ecosystem.

## 8. Risks and unknowns

- **Dorico 6 files untested.** Your newest file is 5.1.60. Please share a Dorico 6 save. The codec is generic, so it will most likely just work.
- **Can Dorico open files we write?** Test files A–D answer this (§9). Writing is needed for restore-from-XML and for merge.
- **Merge safety:** new events need fresh IDs (the `idGenerators` counters must be bumped), and layout and playback cross-references must stay consistent. Start with coarse merges (whole flow or whole player) before note-level ones.
- **Meaning of the per-file marker bits** in DTN type bytes: unknown, but harmless because we preserve them.
- **Bar numbers** (2026-10-29): bars start at every global bar division (time signature or barline, even mid-bar); `irregularBarLength` makes a pick-up; a pick-up at the start is bar 0. Bar-number changes are `barDivisionData/barNumberChangeIfAny` (`type` kRestartSequence, `sequence` kUsePrimarySequence | kUseSubordinateSequence, `index`, `hidePrimaryNumbers`) on hidden bar divisions that Dorico stored in a **stave** stream (the top player's) in the user's reference file. Repeats don't renumber bars. Code: `engine/crates/dorico-format/src/bars.rs`. Player order follows `scorePlayers`, not the layout's score order.
- **EULA / reverse engineering:** this is format interoperability for your own files. Keep it personal or open-source; don't redistribute Steinberg content.

## 9. Experiments for you to run in Dorico

The test files are in [engine/tests/dorico-files/](../../engine/tests/dorico-files/) (moved from `prototype/experiments/dorico-tests/` on 2026-10-29). They're generated from "ET The Flying Theme mASTER" (Dorico 5.1.60) by [make_test_files.py](../research/make_test_files.py) (A–D; E–H by dorico-hp). From Windows: `\\wsl.localhost\Ubuntu-26.04\home\ken\dev\dorico-test\engine\tests\dorico-files\`.

| File | Question | Expected |
|---|---|---|
| `A-rebuilt` | Does our decode → XML → encode round trip open? | Identical to the original (the bytes are identical) |
| `B-xml-inside` | Does your Dorico open projects stored as plain XML? | Probably yes (Steinberg's examples do this) |
| `C-title-edit` | Does Dorico accept a file *we* wrote? | Title ends with "[dorigit C: title edit]" |
| `D-note-edit` | Does Dorico accept a musical edit we made? | Horn (F) 2, bar 1 beat 1: the G4 quaver (concert) is an octave higher |

**Results (2026-10-25):** all four opened in your Dorico. C showed the edited title and D showed Horn 2's note an octave higher. So Dorico accepts files dorigit writes (simple edits), and it loads projects stored as plain XML (B).

Also please check:
- Dynamics hypothesis: in "Harry Potter Cues Plus 5", Quidditch 2004 flow, bar 19, the woodwinds should show **ppp**. **Result:** they show **fff** (Plus 4: ff). The bar was right but forte/piano were swapped; fixed.
- Which Dorico version you're on now, and whether you'd want the app on Windows only or also macOS.

## 10. Suggested roadmap

1. **Now:** done in this session: codec, explode/rebuild, musical listing and diff, git textconv integration. Use `setup-git` on a real project for a week.
2. **Validate:** results of tests A–D, a Dorico 6 sample, bar-number edge cases (pickups, repeats), more event types (lyrics, chord symbols, text, key signatures).
3. **Snapshotter:** watch a folder, snapshot on save into `.dorigit/`, enginedata policy, import the existing Backup Projects folder and your numbered files as history.
4. **Desktop UI (Tauri):** timeline with preview thumbnails, the musical diff view, milestones, "open this version".
5. **Remote API:** save-and-snapshot, open a version in Dorico, detect the current project.
6. **Alternates and merge:** branches; bring over a flow or player; then event-level 3-way merge.
7. **Playback variants:** split `enginedata` from the music history.
