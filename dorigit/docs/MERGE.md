# Variants, merging and conflicts: design (not built yet)

*Drafted 2026-10-25; **revised 2026-10-30 with your answers** (§2). Status: design + feasibility
data; no merge code exists yet. The edit foundation comes from the engine's S5 phase
(`../../engine/docs/STATUS.md`).*

Goal: work with **versions and variants** of a score the way a composer, orchestrator and film
composer actually do. That means presenting alternatives, folding in collaborators' edits,
rescuing old bars, conforming to picture edits and dropping in inserts. Every time two versions
disagree in a way that could be a creative decision, you choose in a **graphical, notation-based
conflict editor**.

## 1. What we know (feasibility)

- **Dorico accepts files dorigit writes**: a title edit and a pitch edit loaded fine (test files C, D). Structural edits (adding events, players, flows) are not yet tested.
- **Three-way probe on your real files** (`base` → two versions; method in §11):

| Base → A / B | Changes A / B | Identical on both | Different on both sides (conflict regions) |
|---|---|---|---|
| HP Plus 5 → "+ string test" / "+ LASS3" | 5,750 / 5,750 | 5,750 (all) | **0**: the music is identical; they differ only in playback |
| Obi-Wan End Credits → "(VSS)" / "IB" | 4,650 / 4,958 | 4,279 | ~1,050 changes; **177 part-bars** changed differently on both sides |

- **ID collisions are real.** Both Obi-Wan versions independently created event `11727` (an *mp* on one side, an *mf* on the other) and slur `9988`, each pointing at a different slur definition (element IDs 104 vs 86). Every version allocates new IDs from the same counters (`idGenerators`), so after a fork the same ID can mean different things. **Merging must renumber one side's new objects and rewrite every reference to them.**
- **The base matters.** For files saved outside dorigit we don't know the true common ancestor. With dorigit history the merge base is the exact common ancestor commit. Your **milestones** (e.g. "Sent to orchestrator") are the natural bases for incoming collaborator files (§5.1).
- **Film data**: none of your projects has video, markers or timecode attached (only the related layout options exist). Those encodings need a reference file (§9).

## 2. Your answers (2026-10-30)

| Question | Answer | Consequence for the design |
|---|---|---|
| Notation or piano roll in the editor? | **Notation first**; a piano roll can come alongside | Verovio notation panes are part of the first editor release (§8), not a later upgrade |
| Conflict granularity | **Bar level**, with **voice level where voices really exist**: divisi staves (Vln IA vs IB), voices of one stave. Be **stricter than git** where a change could be a creative decision | Three outcomes instead of two: *auto*, *review*, *conflict* (§4) |
| Merges you'd do most | 1. **Fold in a copyist's / orchestrator's edits** (engraving, layout, revoicing, reorchestration, adding/removing whole sections). 2. **Rescue bars from an old version**, combined with new bars that changed or didn't exist. 3. **Combine orchestration variants**, picking parts from each for the final | Structure changes (sections added/removed) are core, not a late extra. Engraving is its own lane. Merges can have **more than two sides** (§5) |
| Main use | **Versioning while writing**, presenting **variations of sections** to yourself and others to help decisions; merging comes later | Variants and side-by-side comparison come **before** merging (§3, §10) |
| Film scoring | Picture edits change during scoring; merge **as smoothly as possible**, including **inserts** written separately from the cue | A conform workflow and cross-project inserts (§6) |
| Remote backup/sync | Connect to a repository (GitHub or other, S3, …) | Separate design: [SYNC.md](SYNC.md) |

## 3. Variants first (versioning while writing)

A **variant** is a named alternative of a *section* of a cue, e.g. "1m3 b.17–32: strings only" vs "… with horns".

- **Make a variant**: from the app ("New variant of this file…"). dorigit writes `Cue [variant: horns].dorico` next to the cue, records it as a branch, and opens it in Dorico. Save As in Dorico still works as today.
- **Variant board**: for one cue, every variant as a column, with the bar ranges where it differs from the main version highlighted. Click a range to see the variants' notation side by side (Verovio, §8). Add notes and tags ("director prefers", "too busy").
- **Present to others**: export a comparison sheet, i.e. the differing bars of each variant as PDF (Remote Control PDF export, engine S9), plus a list of differences. Audio stays in Dorico. Sharing happens through SYNC.md's remotes or a file.
- **Choose**: "use this variant for b.17–32" feeds the same engine as merging (§5.3). Choosing never edits the variants themselves.

**Built (V1, 2026-10-31):** `dorigit-core/src/variants.rs`, CLI `dorigit variant new|list|note`,
and the app's **Variants** view (board cards: given range, detected bar ranges per flow with
players, "changed outside its bars" warning, "main version has N changes since", notes, tags,
Show changes, Open in Dorico; "New variant…" form). Variant info is `variants.json` in a commit
chain under `refs/dorigit/variants` in the family repo (sync must push `refs/dorigit/*`). Not yet:
the comparison PDF (needs engine S9 / Remote Control) and "choose this variant for b.x–y" (M5).

**Your choices (2026-10-31):** variant files go **next to the cue** ("1m3 Chase [horns].dorico");
the section is **both** given (optional bar range when making it) and **detected** (bars where it
differs, always shown; dorigit warns if changes fall outside the given range); notes and tags
**travel with the history** (stored in the project's repository, so they sync and back up).

## 4. Change model and conflict rules

Inputs: a **base** (common ancestor or chosen milestone) and two or more **sides** (yours, theirs, variants).

### 4.1 Lanes

Changes are sorted into lanes, because who "owns" a change differs per lane:

| Lane | What's in it | Typical owner |
|---|---|---|
| **Structure** | bars inserted/deleted, time signatures, tempo, key changes, flows added/removed, repeats | composer (and picture edits) |
| **Music** | notes, rests, voices, articulations, dynamics, slurs, techniques, lyrics, chord symbols, per player and stave/voice | composer / orchestrator |
| **Orchestration** | players/instruments added or removed, material moved between players | orchestrator |
| **Engraving** | layout-specific properties (positions, slur shapes, stem directions in a layout), layout options, frame/system breaks, casting off, note spacing, page formatting | copyist / engraver |
| **Settings & library** | engraving/notation options, paragraph/character styles, techniques' appearances | copyist / house style |
| **Playback** | `enginedata`, expression maps, playback-only properties | mock-up / you |

### 4.2 Regions

A **region** is `(flow, player, stave, voice, bar)`:
- **Divisi staves** (Vln IA / IB) and **separate voices** count as separate regions.
- Players with one stave and one voice reduce to `(flow, player, bar)`, the bar level you asked for.
- **Global** items (tempo, time signature, rehearsal marks) are in `(flow, global, bar)`.

### 4.3 Three outcomes (stricter than git)

| Outcome | When | What you do |
|---|---|---|
| **Auto** | Only one side changed a region, and nothing nearby on the other side depends on it | Nothing (listed under "All changes"; can be unticked) |
| **Review** | Combinable, but could be a creative decision: both sides changed *different voices / divisi staves of the same bar* (IA on one side, IB on the other); one side changed notes and the other changed dynamics/articulations/engraving of the same bar; changes in *adjacent* bars joined by ties, slurs or hairpins; orchestration moved material another side edited | Confirm the proposed combination, or choose a side |
| **Conflict** | Both sides changed the *same region* differently; one side deleted what the other edited; structure changed on both sides in overlapping bars | Choose: this / other / original (or both voices where possible) |

**Identical changes** on several sides are applied once and are never conflicts.

**M1 built (2026-10-31):** `dorigit-core/src/merge.rs` (read-only preview). Lanes are assigned
from each change (global stream = structure; layout-specific/position/visibility properties =
engraving; mute/velocity/playback properties = playback; players = orchestration; options =
settings; layouts = engraving; everything else = music). Outcomes as in §4.3 plus **Same**:
identical changes on both sides are set aside first (Dorico's internal element numbers such as
`slurElementID` are ignored), and only what remains decides auto / review / conflict. Structure:
bars added/removed or bar lengths changed per side; both sides restructuring a flow = conflict
(position re-mapping is M4). The ID checker (`ids::check`) runs on both sides. CLI:
`dorigit merge-preview <file|family> <ours> <theirs> [--base]` and
`dorigit merge-preview-files BASE OURS THEIRS`; app: **Merge preview with main** on each variant.
Test files: `research/refs/merge/` (from your divisi file via `research/make_merge_tests.py`):
IA vs IB in bar 5 = review, same IA note two ways = conflict, different bars = automatic.
Real projects: Harry Potter Plus 5 vs "+ string test" / "+ LASS3" = 2 automatic, 1,015
identical; Obi-Wan End Credits vs "(VSS)" / "IB" = 59 conflicts (e.g. bassoons *mf* vs *mp*),
82 to review, 43 automatic, 821 identical.

## 5. Workflows

### 5.1 Folding in a copyist's or orchestrator's edits (most frequent)

1. You **mark a milestone** when you send the score ("Sent to orchestrator, 30 Oct").
2. Their file comes back: **Import incoming version…**. dorigit recognises the project family and suggests the milestone as the base (the last version they had). You can pick another base.
3. Merge with **role presets** (editable):
   - *Copyist*: Engraving and Settings lanes default to **theirs**; Music defaults to **yours** wherever you changed it since the milestone. Any other overlap becomes review/conflict.
   - *Orchestrator*: Music and Orchestration lanes default to **theirs** for regions you didn't touch; your changes since the milestone are conflicts where they overlap.
4. **Engraving that no longer fits**: they adjusted a slur on a note you've since deleted. That change is dropped *with a notice* ("3 engraving tweaks referred to music that no longer exists"), never silently.
5. **Reorchestration** (a line moved from Flute to Oboe) shows as "moved" when the same notes leave one player and appear in another in the same bars. Otherwise as removed + added.
6. **Sections added or removed** by them are structure changes (§7): your later edits are re-mapped onto their bar structure, or you choose whose structure wins for that flow.

### 5.2 Rescuing bars from an old version

- Pick a version in the history, select a bar range and parts in its notation, then **Restore into current…**:
  - **Replace** bars X–Y of the current version, or
  - **Insert** them as new bars at a bar/position (when the old bars no longer exist in the new structure).
- **Joins** are checked at both ends: ties/slurs/hairpins crossing the seam, time signature, key and tempo, dynamics continuity. Anything that doesn't line up is a review item.
- Parts that exist in only one version are listed: drop them, or map to another player.

### 5.3 Combining orchestration variants (N-way)

- **Assemble**: a grid of *sections × variants*. For each section (bar range, optionally per part), pick the variant that supplies it.
- Each pick is a two-way apply onto the base. Overlaps between picks become conflicts.
- The result is a new file and a merge snapshot whose parents are all the variants used.

## 6. Film scoring

### 6.1 Conforming to a new picture edit

When the edit changes, a cue written against the old cut has to move:
- **Track the picture in history**: video file, start timecode, attachment position and markers/hit points are versioned and shown in diffs ("hit point 'door slam' moved +1.2 s", "video changed to v5 cut"). Encodings to be learned (§9).
- **Conform assistant** (later): given old and new marker times, suggest the structural edits (bars to insert or delete, tempo changes) to make each hit land. You apply them in Dorico, or dorigit writes a new version once the edit layer can.
- **Merging across a conform**: work done on the old-cut version after the conform started (e.g. orchestration polish) is re-mapped onto the conformed structure through §7's position mapping. Bars that only existed in one cut become review items.

### 6.2 Inserts

An **insert** is a short piece written separately (often its own project, e.g. "1m3 insert A") to be placed into a cue at a bar or timecode.
- **Place insert…**: choose the insert file, the cue, and the point (bar, or timecode once markers are decoded), as an **insert** (new bars) or a **replacement** of bars X–Y.
- **Player mapping**: by instrument and name ("Horn 1" → "Horn (F) 1"), with a review list for anything unmatched. Inserts often use fewer players; the others get rests.
- **Cross-project**: an insert usually belongs to a different project family, so **every** object is new (all IDs renumbered, styles/techniques copied into the cue's library as needed) and joins are checked as in §5.2.
- Afterwards the cue's history records "insert A placed at b.45 (+8 bars)", and the insert's own history keeps going. When the insert changes later, **Update placed insert** re-applies it at the same spot.

## 7. Structure changes (core, needed by §5–§6)

- **Detect** insert/delete/split operations per flow from the bar structure: time signatures and bar divisions in the global stream, together with the uniform shift of everything after a point.
- Build a **position map** between versions (old position → new position, or "deleted").
- **Re-map** the other side's changes through it before comparing.
- Both sides restructured overlapping bars → flow-level **conflict**: choose whose structure, then re-map the rest.
- Tempo and timecode: with video attached, inserting bars moves later hit points. Show the effect on markers when the decoding exists (§9).

## 8. The editor

**N1 built (2026-10-31):** `dorigit-core/src/notation.rs` writes MEI for a bar range from the
shared read model (key and time signatures, clefs incl. changes, divisi staves, chords, ties
across barlines, tuplets, beams per beat, accidentals from key and bar state, grace notes,
dynamics with dorigit's names incl. modifiers, hairpins). The app draws it with Verovio 6.3.0
(`Notation.svelte`, loaded on first use). In every diff (History and the variant board) each
changed flow has **Show notation**: before/after of the changed bars (±1 bar, at most 12), only
the players with changes, added notes green, changed blue, removed red, concert pitch. CLI:
`dorigit notation <file> --bars 1-8 [--player …]` prints the MEI. Not yet: articulations,
slurs, techniques and text in the notation; score order of players (STATUS B7); the merge
editor's side-by-side panes (M3).

Modelled on VS Code's 3-way merge editor, in notation:

```
┌ Fold in "1m3 Chase (orchestrator)" · base ★ Sent to orchestrator  ✔ 412 auto  ◐ 23 review  ⚠ 9 conflicts ┐
├───────────────────────┬─────────────────────────────────────────────────────────────────────────────────┤
│ Lanes: ▣Music ▣Struct │  Vln I · div. IA / IB · bars 12–14                                ◀ prev  next ▶ │
│ ▣Engraving ▣Settings  │   ORIGINAL            YOURS                    THEIRS                           │
│ ▾ 1m3 Chase           │   [ notation ]        [ notation ]             [ notation ]       (Verovio)     │
│   ⚠ Hn 1   b.12–14    │                       IA: b.13 rewritten       IB: b.12 revoiced                │
│   ◐ Vln IA/IB b.12–14 │   Proposed: IA from YOURS + IB from THEIRS  [ Accept ] [ Yours ] [ Theirs ]     │
│   ✔ Tpt 1   b.20      │                                             [ Original ]  Apply to: region/part │
│ ▸ Structure (1)       │   ─ piano roll (toggle) ─                                                       │
│ ▸ Engraving (37)      │                                                                                 │
├───────────────────────┴─────────────────────────────────────────────────────────────────────────────────┤
│ Result preview b.10–16                                     [ Cancel ]   [ Create merged file & open ]   │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

- **Notation panes from the start**: MEI generated from the read model for the region, plus a bar of context on each side. Rendered with **Verovio** (WASM in the webview; LGPL-3.0). Changed notes are coloured. A **piano roll** toggle sits alongside. It's approximate engraving, for deciding, not for print.
- **Lanes** can be filtered and get defaults per role preset (§5.1).
- **Review items** show the proposed combination with one-click accept.
- **Finish**: integrity check → new file → "Open in Dorico" (Remote Control, engine S9) at the first bar that needs a look.

## 9. Reference files (your help, like the dynamics rounds)

Instructions and starter files: [`research/refs/README.md`](../research/refs/README.md) (2026-10-30).
What your existing projects already answered (read from copies, RESEARCH.md "Film and divisi"):
- **Divisi** ("Have Yourself A Merry Little Christmas"): `DivisiEventDefinition` in the instrument's
  stave stream lists the sections; each extra section gets its own stave (`divisiIndex`) and
  voice. So §4.2 regions can key on (stave, divisi section) directly.
- **Film** ("BLACK LABEL"): per-flow `flowVideoData` (file path, two times, duration, frame rate);
  markers are `MarkerEventDefinition` events in the flow's global stream, with text, an
  "important" flag, a time in seconds and a beat position.

Still asked for (in the README):
1. ~~Dynamic modifiers~~ and 2. ~~Divisi changes~~: done 2026-10-30 (`research/refs/ref-dynamics-divisi.dorico`; results in the refs README). I'll make the IA/IB edit pair myself from that file.
3. ~~Film v1/v2~~: done 2026-10-31. Markers are stored in **clip time** and follow the picture; Dorico recomputes their beat positions. So a new cut shows up as: video settings changed + markers moved/added/removed (by eventID), with the music unchanged, which is exactly the input §6.1's conform assistant needs. dorigit's diff already shows it (`research/refs/README.md`).
4. (Later) An insert placed by hand in Dorico, so dorigit's automated insert can be checked against it.

## 10. Plan (re-ordered by your priorities)

| Milestone | Content | Depends on |
|---|---|---|
| **V1 Variants** | "New variant" from the app; variant board (where variants differ, by bar range); comparison PDF via Remote Control | read model; engine S9 for PDF |
| **N1 Notation panes** | MEI from the read model for a bar range; Verovio in the app; used by the diff view first (see any change in notation) | read model |
| **M1 Preview** | Reference-integrity checker; lane + region classifier (auto/review/conflict) incl. divisi/voice regions; `dorigit merge-preview` CLI; structure detection (§7) in report form | read model; `ids::check` exists |
| **M2 Apply** | On engine **S5** (`dorico-edit`): restore bars into current (replace/insert, joins), bring over part/flow, renumbering | **engine S5** |
| **M3 Fold-in** | Import incoming version with milestone base; role presets; merge editor (notation panes, lanes, review/conflict) | M1, M2, N1 |
| **M4 Structure** | Position mapping across inserted/deleted bars; merging across conforms | M3 |
| **M5 Assemble** | N-way variant assembly grid | M3 |
| **F1 Film** | Picture data in history and diffs; place/update inserts (cross-project); conform assistant | reference file 2; M2, M4 |

## 11. Probe method (reproducible)

Script: [research/merge_probe.py](../research/merge_probe.py) (`uv run python dorigit/research/merge_probe.py BASE A B` from the repo root). Base/A/B loaded with dorigit's listing model (`doricokit.listing`). Changes per side = events added / removed / modified (owner, lane, position, text, props) vs base, keyed by `(flowID, eventID)`. Identical changes on both sides are set aside. A conflict region = a `(flow, player, bar)` with remaining changes on both sides. `idGenerators` were compared to spot counters that advanced on both sides. M1 re-implements this in Rust with the finer regions of §4.2.
