# dorigit: status and resume notes

*Last updated: 2026-10-30 (to-do list reviewed against the shared engine). Read this first when picking the work back up.*

> **Project S (2026-10-29, engine session):** `dorico-format` now lives in
> `../engine/crates/dorico-format` and the Cargo workspace is the repo root (`../Cargo.toml`,
> one `Cargo.lock` and `target/` there). Commands below still work from this folder. Test files
> A–H moved to `../engine/tests/dorico-files/`. One behaviour change: restored `.dorico` files
> now write folder entries the way Dorico does (empty, deflated). dorigit's listing/diff output is
> unchanged. Details: `../engine/docs/STATUS.md`.
>
> **Later the same day (S4, with the user's OK):** the listing's bar numbers now come from the
> shared bar code (`engine/crates/dorico-format/src/bars.rs`, also used by the read model):
> a pick-up bar is **bar 0** and bar-number changes are followed (primary "30", subordinate
> "35a"), checked against the user's reference file. Dynamics: Dorico's "f possibile"
> (`{int: 0}, {int: 1}, {bool: false}, {}`) is decoded. **Correction (user, 2026-10-30):** possibile is a
> standard Dorico modifier, allowed only on f or p, not an error in the ET score. Listing changes in the user's files:
> only "brass test" (pick-up) and the ET test files (f possibile). The Windows binaries in
> `dist/` were rebuilt on 2026-10-30 and include these changes (checked: brass test pick-up = bar 0, f possibile).
>
> **2026-10-30 (user's OK):** the Python prototype (`prototype/`) is **retired**. Its two scripts
> moved to `research/` and now run on the shared engine with byte-identical results
> (`merge_probe.py` via the new `doricokit.listing`, the same Rust model as `dorigit show`;
> `make_test_files.py`). The prototype listing parity test is gone; listings are pinned by the
> golden tests. Backup: `~/dev/dorico-test-backups/2026-10-30-dorigit-prototype.tar.gz`.
> Subordinate bar numbers ("35a", "35b") confirmed by the user in Dorico.
> Open: in the reference file Dorico counts one bar fewer than `bars.rs` near the end (the
> coda's last bar is 35h, the code says 35i); see engine/docs/STATUS.md, "Waiting on you" 4.

## Where things stand

| Area | State | How it was verified |
|---|---|---|
| DTN codec (Rust) | ✅ complete | 64 DTN files from your Dorico Projects re-encode byte-for-byte, directly and via XML text (`real_files` test) |
| Musical model / listing / diff | ✅ working | Rust listing == Python prototype for 32 projects (before the prototype was retired; now pinned by golden tests); diffs checked by hand on HP 4→5, Obi-Wan 1→2, Christmas 2→3; dynamics and bar/beat positions confirmed by you in Dorico |
| Playback setup reader | ✅ working | Reads SWAM / Kontakt / Pianoteq / VSS / HALion setups from real files |
| Snapshot store | ✅ working | `dorigit-core/tests/store.rs` (synthetic projects): snapshot, dedupe, Save-As forks, milestones, restore + pending fork, playback policy incl. setup change |
| Import of existing files | ✅ working | HP family (14 files) and Obi-Wan (6 files) imported, on both WSL and native Windows |
| Restore | ✅ working | Obi-Wan 2 restored on Windows: all 20 zip entries byte-identical |
| Watcher | ✅ working on Windows | Windows CLI `watch`: new save → snapshot, identical save → skipped, different project → new family |
| CLI (`dorigit`) | ✅ working | Linux and Windows builds |
| Desktop app | 🟡 first version, smoke-tested | Windows exe starts (hidden, tray), watcher runs, UI loads and calls the backend, a save produced a snapshot (`dorigit.log`). UI checked via headless-Edge screenshots with mock data (light + dark). **Not yet used interactively by you.** |
| Merge / conflict editor | 📝 designed only | [MERGE.md](MERGE.md); three-way probe on your files; waiting on your answers to its open questions |
| Dorico accepts files we write | ✅ confirmed | You opened test files A–D in Dorico (2026-10-25): all four opened; C's title edit and D's Horn 2 octave edit were visible. B shows Dorico also opens projects stored as plain XML (RESEARCH.md §9) |

## Try it (Windows)

Built binaries (not committed; rebuild with `scripts/build-windows.sh`):
`\\wsl.localhost\Ubuntu-26.04\home\ken\dev\dorico-test\dorigit\dist\windows\`

- `dorigit-app.exe`: the app. Keep `WebView2Loader.dll` in the same folder. Copy the folder somewhere on Windows (e.g. `C:\Tools\dorigit\`) rather than running it from the `\\wsl` path.
- `dorigit.exe`: the CLI.

First run: the app creates `%LOCALAPPDATA%\dorigit\settings.json`, watching `Documents\Dorico Projects`. Use **Import existing files…** to build history from your numbered copies. Closing the window keeps it in the tray; use the tray menu → Quit to stop.

To experiment without touching your real setup, set `DORIGIT_DATA_DIR` to a scratch folder first.

## What's left (reviewed 2026-10-30 against the engine, f2d and dorico-hp)

Priorities changed because the shared engine (Project S, `../engine/docs/STATUS.md`) now covers
or will cover several items. **Owner** says who does it: *dorigit* = this tool's session,
*engine* = the engine session (requests go in `../engine/REQUESTS.md`), *you* = the user.

### Done since the first list
- ~~Bar numbers~~: pick-up = bar 0, bar-number changes, "35a" subordinates (shared `bars.rs`; confirmed by you).
- ~~Concert pitch~~: accepted as is (Dorico handles transposition).
- ~~Dynamics decoding~~: confirmed by you (fff/mf/mp/sfz), "f possibile" decoded.
- ~~Dorico accepts files we write~~: test files A–D (and the engine's later checks) open fine.
- ~~Python prototype~~: retired; research scripts in `research/` run on the shared engine.
- ~~Dynamics by name~~ (2026-10-30): new shared `dorico-format::dynamics`: ffz/rffz/sffz, sf/rf, combined (fp, ff-mp…), subito, messa di voce, dal/al niente, poco a poco; unknown ones read "custom dynamic (…)". Checked on your `ref-extras*.dorico`. **Modifiers** (poco, molto, più, meno) and p possibile added the same day from your `research/refs/ref-dynamics-divisi.dorico`; possibile is standard (f or p only).

### A. Needs you
1. **Use the app on real work** (the rebuilt app is in `dist/windows/`). Still the biggest unknown.
2. ~~Answer the merge questions~~ (answered 2026-10-30; MERGE.md revised: variants first, notation panes, auto/review/conflict, film conform + inserts).
   ~~Sync questions~~ (answered 2026-10-30, SYNC.md "Your answers").
   ~~Check ff-mp~~ (confirmed by you 2026-10-30: Plus 5, *Rainy Nights…*, Horn 1 bar 11 beat 1 is ff-mp).
   ~~Reference files~~: ref-dynamics-divisi (2026-10-30) and film v1/v2 (2026-10-31) done;
   results in [research/refs/README.md](../research/refs/README.md). Divisi and film basics
   were learned from "Have Yourself A Merry Little Christmas" and "BLACK LABEL" (RESEARCH.md).
3. ~~Open questions~~ (answered 2026-10-30, see "Decisions" below).
4. Dorico 6 samples: **lower priority now**. PLANNED_WORK.md targets Dorico 5 (5.1.60) for now.

### B. dorigit work, ready now (suggested order)
**Your pick (2026-10-31): groundwork first (B3 store lock → SYNC R0 machine-independent branch names → B2 listing on the shared read model), then V1 Variants, then N1 notation view.**

1. ~~Rebuild the Windows app~~ **Done 2026-10-30** (`dist/windows/`, verified on brass test and ET test file A).
2. ~~Move the listing and diff onto the shared read model~~ **Done 2026-10-31** as `dorigit-core/src/listing.rs`: the shared listing plus readable names for techniques ("Pizzicato", "Open (remove mute)"), tuplets ("3:2 quavers"), clefs, text, divisi ("1 / 2", "unison", "Solo + gli altri"), ottavas, ornaments, arpeggios, pauses and note articulations ("tenuto accent"); golden re-recorded (only in-place line rewrites). Still raw: slurs (element ids), trills' interval, condensing/layout events. Was: It already has
   technique names (from the library), slurs, trills, glissandi, text, clefs, keys, tempos,
   rehearsal marks, repeats, harp pedals, ottavas, divisi staves and combined dynamics (fp…).
   This replaces old gap 7 ("other events shown as raw field=value") with **little new
   decoding work**. Changes listing output, so re-record the golden cases. (Was "richer event
   descriptions", a big item; **now mostly integration**.)
3. ~~Cross-process store lock~~ **Done 2026-10-31** (`lock.rs`, DESIGN.md §3; tested with a second holder). Also done: **machine-independent branch names** (SYNC R0.1) with automatic migration. Was: PLANNED_WORK §2.11 has Score
   Workbench and Playback snapshot before/after their changes through the `dorigit-core`
   library while the dorigit app's watcher runs. Two processes would race on `family.json`.
   Add a lock file per family repo.
4. App polish: ~~a proper "Snapshot now / milestone" dialog~~ (done 2026-10-31: "Save a version now…" dialog, `SnapshotDialog.svelte`); still open: import progress, "milestone the current file now", snapshot-error notifications, start on login
   (`--hidden` exists).
5. Store housekeeping: size per project, optional thinning of old automatic versions, pack/gc.
6. Use the `dorico-paths` crate for default folders (Documents, AppData) instead of dorigit's
   own `settings.rs` guesses (small).
7. Player order: list players in score order (layout order) rather than setup order. Not in
   the shared model yet; add it there so f2d's reviewer gets it too.
8. Family split: "make this file its own project" for pieces started from a shared template.
9. ~~Timeline: fold save bursts~~ **Done 2026-10-31** (`Timeline.svelte`: same file, each save within 10 min of the next, milestones never folded; the selected version's burst opens by itself). Was: (your answer 2026-10-30): keep every save, but group saves of
   the same file a few minutes apart into one expandable row (milestones never folded).
10. **macOS build** (your answer 2026-10-30): Windows + macOS, Linux easy later. Test machine: your
    2014 Mac mini, **macOS 10.15 or newer** (fine for Tauri 2) with **Dorico 3.5**. Consequences:
    dorigit reads 3.5 projects (BLACK LABEL is one and lists fine), but Dorico 3.5 can't open
    files saved by Dorico 5, so on the Mac only 3.5-made versions restore into something it can
    open; the app should show each version's "saved with Dorico x.y" and warn before restoring a
    newer one. Build on the Mac itself (rustup + Xcode command-line tools) or via CI; WSL can't
    bundle a .app. Keep paths/OS code behind `dorico-paths`.

11. ~~Dorico-version upgrades in diffs~~ **Done 2026-10-31** (`dorigit-core/src/tidy.rs`, used for every dorigit diff): a player rename no longer makes all its notes "moved", and when the newer version was saved by a newer Dorico, format-only changes are hidden behind one notice ("Saved with a newer Dorico (4.3.30 → 5.1.60). 1440 format-only changes hidden"). Rite of Spring 4.3 export vs 5.1 save: the shared flow went from 1,255 changes to none. Player names show ♭/♯ instead of Dorico's `{@flat@}` tokens. Was: (from the Rite of Spring 4.3 vs 5.1 saves): when a
    version's `lastSavedVersion` is newer than its parent's, mark the diff "re-saved in Dorico
    5.1" and fold the known upgrade-only changes (flat tokens in names, `EventMuted` true →
    kAlways, glissando playback type, new default options) into one collapsed line, so the
    musical changes stay visible. List in RESEARCH.md "Dorico 4.3 vs 5.1".

### B2. Variants, merging and sync (plan in MERGE.md §10 and SYNC.md §8)
**V1 Variants built 2026-10-31** (MERGE.md §3 "Built"): make a variant (CLI/app), board with
detected bar ranges, given range + warning, notes/tags stored in the history, compare and open.
Left in V1: comparison PDF (engine S9), choosing a variant into the main version (M5).
**N1 notation view built 2026-10-31** (MERGE.md §8 "N1 built"). Your three picks are done; next
candidates: B4 app polish / B9 save-burst folding / B11 upgrade-noise folding, M1 merge preview,
SYNC R1 folder remote, or notation extras (articulations, slurs, techniques; score order B7).

**M1 merge preview built 2026-10-31** (see session log). Order by your priorities: **V1 variants** (new variant, variant board, comparison PDF) → **N1
notation panes** (Verovio, also for the diff view) → **M1 merge preview** (integrity checker,
auto/review/conflict classifier incl. divisi/voice regions, structure detection) → M2–M5 on the
engine's S5 edit layer → **F1 film** (picture data in history, inserts, conform). Sync: **R0
prerequisites** (machine-independent branch names, store lock, packing) can start now; R1 folder
remote next.

### C. Waiting on the engine (don't duplicate in dorigit)
1. ~~Custom dynamics~~ **Mostly done 2026-10-30** in `dorico-format::dynamics` (dorigit uses it). Modifiers, possibile, film and harmonics added 2026-10-30/31. Open in `../engine/REQUESTS.md`: the shared read model (f2d reviewer, dorico-hp) adopting the decoder and film data.
2. **S5 edit layer (`dorico-edit`)**: the engine's next phase. It's the foundation for MERGE.md
   M2 ("restore bars from an older version", "bring over a part/flow") and the merge itself:
   transactions, byte-identical untouched data, ID allocation (`ids.rs` exists), and the
   renumbering rules from MERGE.md. **Merge M2+ should be built on S5, not as a dorigit-only
   apply engine.** MERGE.md M1 (`merge-preview` + reference-integrity checker) can start now on
   the read model; `ids::check` already verifies the counters.
3. **S6 playback**: `playback.rs` merges with dorico-hp's playback code into `dorico-playback`.
   dorigit's policy keeps working; no dorigit work.
4. **S9 automation (Remote Control client)**: **de-risked.** The converter session connected
   to your Dorico 5 (`finale2dorico/research/tools/dorico_remote.ps1`): `File.Open`, switching
   mode and PDF export all work; it runs on the Windows side only (WSL can't reach port 4560). It
   unlocks dorigit's "Save & snapshot", "open this version in the running Dorico", and a
   **visual diff** (export a version's full score as PDF on demand) without dorigit writing its
   own client.
5. **S11 shared UI kit**: dorigit's Svelte components become the kit for Workbench and Playback.
   Keep dorigit UI changes component-friendly; extraction is the engine/UI session's job.

### D. Later
- Playback variants as a first-class concept (DESIGN.md §6).
- Signed Windows installer (MSVC + `npm run tauri build`).
- Dorico 6 support (after you move to it).

### Known limitations (unchanged, lower priority)
- Large-file speed: ~1–2 s per 25 MB project snapshot; fine for saves, slow for bulk imports.
- Windows GNU build needs `WebView2Loader.dll` beside the exe; not code-signed.
- "ffffff"-style 6–8 f counts exist in your files (Horn 2 bar 89, Timpani bar 69 in test file A); Dorico's display not checked.

## Decisions (your answers, 2026-10-30)

- **Platforms:** Windows and macOS (test Mac: 2014 Mac mini, macOS 10.15+, Dorico 3.5); keep Linux easy to add. → B10.
- **Quick repeated saves:** keep every save; the timeline folds bursts into one expandable row. → B9.
- **Restored versions:** next to the original by default; configurable. Already there: Settings > "Restored versions go to" (`restore_dir`).
- **Sync:** GitHub (private), external drive/NAS and S3/B2; two or more machines; collaborators both use dorigit and send files back; private is enough by default, with per-project encryption as an option. → SYNC.md.

## How to resume development

```sh
cd ~/dev/dorico-test/dorigit
. scripts/dev-env.sh                       # Rust + zig on PATH (WSL)
cargo test                                 # unit + synthetic store tests
DORICO_SAMPLES="/mnt/c/Users/kspie/Documents/Dorico Projects" \
  cargo test -p dorico-format --release --test real_files   # real-file round trips (~1 min)
(cd app && npm run check && npm run dev)   # UI in a browser with mock data (http://localhost:1420)
scripts/build-windows.sh                   # Windows exe + CLI into dist/windows/
```

Smoke-test the Windows app without touching real settings (from WSL), as done in session 2:
set `DORIGIT_DATA_DIR` to a Windows temp folder containing a `settings.json` with a scratch `watch_dirs`, export `WSLENV=DORIGIT_DATA_DIR`, run `dorigit-app.exe --hidden`, then read `dorigit.log`.

## Session log

- **Engine session 2** (2026-10-30): prototype retired; `merge_probe.py` and `make_test_files.py` moved to `research/` on the shared engine (same output).
- **Engine session 1, cont.** (2026-10-29): listing bar numbers from the shared bar code (pick-up = 0, bar-number changes) and "f possibile" decoding; prototype parity test skips projects whose bar numbers intentionally differ.
- **Engine session 1** (2026-10-29, Project S): crate + workspace moved to the repo root/engine (see note at the top); dorigit's tests, real-file tests (64 round trips, 32 listings = prototype) and the Windows cross-build all pass after the move.
- **Session 1** (2026-10-25): format research; DTN cracked; Python prototype (diff, git textconv); storage experiment; RESEARCH.md.
- **2026-10-31, M1 merge preview**: `merge.rs` (lanes, regions, same/auto/review/conflict, structure notes, ID check), `Store::merge_preview`, CLI `merge-preview` / `merge-preview-files`, app "Merge preview with main" on variant cards (`MergePreview.svelte`), divisi test files + generator, 2 store tests; checked on real Harry Potter and Obi-Wan variants (MERGE.md §4 "M1 built"). Next: M2 apply needs the engine's edit layer (S5); meanwhile SYNC R1, rest of B4, notation extras.
- **2026-10-31, engine handoff**: the engine session (0c) switched `listing.rs` and `notation.rs` to the engine's shared decoders (`dorico_format::vocab`, new `dorico-model` fields: `Flow.keys`, `Mark.name`/`tuplet`, `DynamicItem.name`); no behaviour change (golden 40/40 identical, tests green, checked here); notation now uses global keys only (local open-key staves no longer override them). dist/windows rebuilt.
- **2026-10-31, polish**: save-burst folding in the timeline (B9); `tidy.rs` diff (renames not "moved", newer-Dorico format noise hidden, B11) with a notice in the app; ♭/♯ in player names (golden re-recorded for dorigit: token swaps only); "Save a version now…" dialog replacing `prompt()` (B4 part); screenshots checked; Windows build. Next candidates: M1 merge preview, SYNC R1 folder remote, rest of B4 (import progress, error notices, start on login), notation extras.
- **2026-10-31, N1 notation**: `notation.rs` (MEI from the read model; key/clef/divisi/tuplets/beams/ties/accidentals/dynamics), `Store::notation`/`notation_diff`, CLI `dorigit notation`, app `Notation.svelte` + "Show notation" in every diff (Verovio 6.3.0, lazy chunk); tests incl. a real ET edit (A→D); renders checked on ET, the divisi ref file and the mock diff; Windows build.
- **2026-10-31, V1 variants**: `variants.rs` (+ integration test), `dorigit variant new|list|note`, app Variants view (History/Variants switch; screenshots checked light/dark; History view unchanged), Tauri commands `variant_board`/`new_variant`/`update_variant`; Windows build + smoke test (app watching while CLI made a variant on scratch data).
- **2026-10-31, groundwork 2**: B2 done (listing names via `listing.rs`, golden re-recorded for dorigit only); engine requests filed (technique `name` vs `text`, public helper, tuplet codes). Groundwork complete except packing (B5/SYNC R0.3, not needed until sync). Next: V1 Variants.
- **2026-10-31, groundwork 1**: cross-process family lock (`lock.rs`) on every store write; branch names now follow the file name (machine-independent, migrated on open); 2 new store tests; CLI smoke test on a scratch store. Next: B2 (listing/diff on the shared read model), coordinating with finale2dorico's new engine module.
- **2026-10-31, Rite flows**: the engraver's Dorico 4.3 exports of "Spring Rounds" and "The Dancing Out of the Earth" compared with Part I (which is a Dorico 5.1 save): identical music and eventIDs; Dorico 5's re-save changes listed (RESEARCH.md); harmonics decoded and named (partial number confirmed by you). B11 added.
- **2026-10-31, ref round 2**: film v1/v2 decoded (video fields, markers in clip time follow the picture, timecode = clip start TC + clip time; confirmed by you). Listing/diff: `video:` line per flow, markers as `"name" at HH:MM:SS:FF (important)`, picture changes in the app's diff view. Rite of Spring I/II (Dorico 3.5 demo-sized files): byte-exact round trip, all 6,800 dynamics named; remaining gaps filed in `engine/REQUESTS.md`. Windows app rebuilt.
- **2026-10-30, ref round 1**: your `ref-dynamics-divisi.dorico` decoded: modifiers poco/molto/più/meno (confirmed by you), p possibile, divisi unison and Solo/gli altri. Possibile corrected to "standard, f or p only" everywhere.
- **2026-10-30, latest**: ff-mp confirmed; your answers on sync, platforms, save bursts and restore location recorded; divisi (Christmas arrangement) and film data (BLACK LABEL) decoded from copies; reference round started in `research/refs/` (starter files + README).
- **2026-10-30, later**: dynamics decoder (`dorico-format::dynamics`, golden re-recorded for dorigit's 15 changed listings); MERGE.md revised with your answers (variants first, notation, auto/review/conflict, copyist/orchestrator fold-in, rescue bars, N-way variants, film conform + inserts); new SYNC.md (remote backup/sync); Windows app rebuilt.
- **2026-10-30 review**: to-do list re-prioritised against the engine, f2d and dorico-hp (section "What's left"); custom dynamics to be fully supported (your decision; engine request filed).
- **Session 2 follow-up 2** (2026-10-26): dynamics confirmed by you (fff/mf/mp/sfz); forte/piano mapping fixed.
- **Session 2 follow-up** (2026-10-25): you confirmed test files A–D all open in Dorico, with the C and D edits visible. Merge/conflict design + three-way probe on your files → docs/MERGE.md.
- **Session 2** (2026-10-25): folder restructure; Rust port (`dorico-format`) with parity tests; `dorigit-core` (store, policy, restore, watcher); setup-aware playback policy; CLI; Tauri app (backend + Svelte UI); Windows cross-build from WSL (zig); Windows smoke tests; docs.
