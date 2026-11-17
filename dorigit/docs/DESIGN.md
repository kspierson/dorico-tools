# dorigit: design

How the tool works and why it's built this way. For the file-format research behind it see [RESEARCH.md](RESEARCH.md). For current state, known gaps and next steps see [STATUS.md](STATUS.md). For building see [DEV_SETUP.md](DEV_SETUP.md).

## 1. What it does

dorigit gives Dorico projects git-like history without changing how you work in Dorico:

- **Every save is a version.** A watcher sees Dorico write the `.dorico` file and records a snapshot.
- **Save As is understood.** "Cue v2.dorico" saved from "Cue.dorico" continues the same history as a branch. No setup needed.
- **Changes are described musically**, per flow and part, e.g. "Trumpet 1, bar 16 beat 3: B5 quaver: staccato-tenuto removed".
- **Any version can be opened again.** It's rebuilt as a *new* file next to the original and opened in Dorico. Existing files are never modified.
- **Milestones** ("Sent to orchestrator") label important versions.
- **Playback state is handled deliberately** (§6), because it is 95% of the bytes.

## 2. Components

```
dorigit/
├─ (../engine/crates/dorico-format)  Dorico file format: DTN codec, XML, zip container, musical
│                         model, diff/listing, playback-setup reader. No git, no IO beyond files.
│                         Moved to the shared engine (Project S, 2026-10-29); shared by all tools.
├─ crates/dorigit-core    Snapshot store (git2), playback policy, restore, settings, folder watcher.
├─ crates/dorigit-cli     `dorigit` command: show/diff (git textconv), snapshot/import/log/restore/watch.
├─ app/                   Tauri 2 desktop app: Svelte 5 + TS frontend (app/src), thin Rust backend
│                         (app/src-tauri) calling dorigit-core.
└─ research/              Research scripts: merge_probe.py (MERGE.md §8), make_test_files.py
                          (test files A–D). The Python prototype they came from was retired
                          2026-10-30 (backup: ~/dev/dorico-test-backups/2026-10-30-dorigit-prototype.tar.gz).
```

```
 Dorico ──save──▶ Cue.dorico                        (Dorico owns this file; dorigit only reads it)
                     │
           watch.rs  │ notify events → wait until quiet (settle_ms) and the zip is complete
                     ▼
           store.rs  snapshot_file()
                     │  dorico-format: unzip → decode score.dtn → XML; read playback setup
                     │  policy.rs: keep enginedata?  diff vs parent → summary
                     ▼
     <store>/c1609642780.git   (bare git repo per project family)
                     ▲
   app (Tauri) ──────┘  list / diff / thumbnail / restore / milestones
   cli (dorigit) ────┘
```

## 3. Identity: project families, files, branches

- **Family** = Dorico's `info/createdDate` (unix seconds, set when the project is first created). It survives Save As: all 15 "Harry Potter Cues…" files share `1609642780`. One bare git repo per family: `<store>/c<createdDate>.git`. If createdDate is missing, the family is derived from a hash of the path (`p<hash>`).
- **File** → **branch**: each `.dorico` file gets a branch named after the file, `refs/heads/<slug-of-file-name>` ("1m3 Chase.dorico" → `1m3-chase`), so the same file has the same branch on every machine (needed for sync, SYNC.md §6.1). A *different* file with the same name on the same machine gets `-2`, `-3`. `family.json` (local, never synced) maps this machine's normalised paths → branch. Stores made before 2026-10-31 used `<slug>-<6 hex of path hash>`; `Store::open` renames those once (`Store::migrate`).
- **Variants** (MERGE.md §3, `variants.rs`): a variant is a file "<cue> [<name>].dorico" beside the cue whose branch starts at the cue's latest snapshot. Name, optional bar range, notes and tags live in the repository itself: `refs/dorigit/variants` → commit → `variants.json` (one commit per change), so they travel with sync and backups. The board diffs each variant against its merge base with the main version and groups changed events into bar ranges per flow.
- **Notation view** (`notation.rs`, app `Notation.svelte`): MEI generated from the shared read model, drawn by Verovio (npm `verovio`, pinned 6.3.0, **LGPL-3.0**). Verovio is a separate ~8 MB chunk loaded on first use. Before sharing the app beyond your own machines: ship Verovio's license text and a pointer to its source, and keep it replaceable (LGPL); today Tauri embeds the front-end assets in the exe.
- **Tidy diff** (`tidy.rs`): every diff dorigit shows or summarises drops rename-only "moves" and, for a version saved by a newer Dorico (major.minor), format-only changes (new/removed option values, new info fields, `EventMuted` true→kAlways, glissando playback type), replaced by one info line `Re-saved in Dorico`.
- **Concurrency**: every write to a family holds `<family>.git/dorigit.lock`, an OS file lock (`lock.rs`; Windows `LockFileEx`, macOS/Linux `flock`, released if the holder crashes), so the app, the CLI and other tools using `dorigit-core` can share one store. A write waits up to 30 s (`Store::lock_timeout`), then reports "the history store is busy (held by …)". Reads don't lock.
- **Parent selection** (`store.rs`, how Save As becomes branching):
  1. *pending fork*: the file was written by `restore` → parent = the restored snapshot;
  2. else the tip of this file's branch;
  3. else (a new file in the family, i.e. a Save As) the family's most recent snapshot.
- Consequence: numbered copies ("v2", "v3") form a chain; variants ("SILENT", "VSS") fork. A template reused for a new piece via Save As also joins the template's family (e.g. "IFMC BLANK" → "FLYING SAILOR"). That's harmless but could be split later (see STATUS.md).

## 4. What a snapshot stores

Each commit's tree:

| Path | Content | Why |
|---|---|---|
| `dorigit.json` | Manifest (`manifest.rs`): zip entry order, timestamps, compression; per-entry git blob id of the *original* bytes; DTN/XML form; source path/size/mtime; Dorico versions; playback info; summary | Exact rebuild + UI metadata without parsing the score |
| `score.xml` | Score as Dorico-style XML (from DTN, with `<?dorigit-dtn-marker N?>`), or the original XML verbatim | Diffable; git delta-compresses it to ~15–45 KB per version |
| `scorelibrary.xml` | Same for the library | |
| `files/<zip path>` | All other zip entries, verbatim (workspace, graphics, scoreinfo…) | Small |
| `files/supplementary_data/preview/*` | Dorico's first-page preview PDF/PNG, **only when playback is kept** | Large-ish and not delta-friendly; Dorico regenerates them on the next save |
| `thumb.png` | 420×600 downscaled preview (always, if Dorico wrote one) | Timeline thumbnails |
| `playback/enginedata` | Playback state, **only when the policy keeps it** (§6) | 2–25 MB, opaque |

- Commit time = Dorico's `lastSavedDate` (UTC). Author = `dorigit`. Message: `<file name>: <summary>`, plus `Milestone: <name>` for milestones.
- **Dedupe**: `content_id` = hash over all entries' original blob ids. If it equals the parent's, no commit is made; the file's branch is just pointed at the parent. This handles double watcher events, and Save As without changes.
- **Milestones** = annotated tags `refs/tags/<slug>-<short id>`, with the name as the tag message.
- The repo is a normal bare git repo. `git --git-dir <store>/c….git log --all` works, and any git GUI can open it.

## 5. Restore ("Open this version")

`Store::restore(family, id, dest)`:
1. Read the manifest; rebuild every zip entry in its original order with its original timestamp and compression.
2. `score.xml` with form `dtn` is re-encoded to DTN. This is byte-identical to the original; tested on all 88 DTN files.
3. `enginedata` comes from the snapshot if stored; else an identical blob already in the repo; else the `borrow_from` snapshot (same plugin setup); else the nearest ancestor that kept one; else it's omitted.
4. Previews not stored are omitted (Dorico rewrites them on save).
5. `dest` must not exist. Default name: `<stem> (restored <short id>).dorico` next to the original (or in `restore_dir`).
6. Records a **pending fork** so that when you save the restored file in Dorico, its history continues from the restored snapshot on a new branch.

Verified: restoring "Obi-Wan 2" from a store on Windows reproduced all 20 zip entries byte-for-byte.

## 6. Playback state policy

`supplementary_data/vstaudioengine/enginedata` = length-prefixed chunks: `MixerData`, version, `MixerDocument`, then the **mixer XML** (channels, instrument slots, inserts, routing), then the audio-device XML, then **opaque plugin state blobs** (Kontakt, SWAM, Pianoteq, VSS…). Plugins re-serialise their state on every save: only 2.6% of bytes are shared between two saves a day apart. So git can't compress it, and keeping it on every save costs ~20 MB per save for your orchestral projects.

`dorico_format::playback::read_setup` reads the *setup* from the mixer XML: the multiset of `<instrument>` and `<insert>` plugins (name + class uid). Comparing setups tells "plugins added / removed / swapped" apart from "internals re-saved".

Policy (`policy.rs`, default mode `milestones`). Keep `enginedata` when:
1. the snapshot is a **milestone**;
2. the **setup changed** vs the parent: new player's instrument, SILENT variant, VSS added… The manifest records a readable list (`setup_changes`, e.g. `+1 Kontakt`, `-20 Kontakt`);
3. nothing earlier can be **borrowed** (first version in history);
4. it's **small** (≤ `keep_if_under_bytes`, default 2 MB: HALion/NotePerformer projects);
5. identical bytes are already stored (free).

Otherwise it's skipped, and the manifest records `borrow_from` = the nearest earlier snapshot holding the same setup. Restores use that copy, so the right plugins are always loaded; only plugin-internal settings (Kontakt articulation/level tweaks) may come from that earlier save. Other modes: `always` and `never`.

Measured on your Harry Potter history (14 files over 20 months): every save in a long-lived setup borrows; stored copies line up with real setup changes ("+1 Altiverb 7, +2 Virtual Sound Stage", "SILENT: −20 Kontakt"…).

**Merging** is designed separately in [MERGE.md](MERGE.md).

**Future idea (not built):** "playback variants" as a first-class concept, where one music history can switch between playback setups (SILENT / VSS / Kontakt). The setup fingerprint and borrow mechanism are the groundwork.

## 7. Watcher

`watch.rs` uses `notify` (ReadDirectoryChangesW on Windows), recursive, on `settings.watch_dirs`:
- only `*.dorico`; ignores paths containing `Backup Projects`, `AutoSave`, … (`settings.ignore`) and the store itself;
- waits until a file has been quiet for `settle_ms` (default 2 s) **and** opens as a complete zip (retries up to 30 times);
- skips files whose (size, mtime) haven't changed since the last snapshot;
- calls back on a background thread; the app emits an `activity` event to the UI.

It doesn't work from WSL on `/mnt/c` (no change notifications across the VM boundary), so the app must run natively on Windows.

## 8. Musical model and diff (dorico-format)

- `model.rs` builds `Score { info, players, flows[events], options, layouts }`. Events have owner (player), lane (voice/stave), kind, exact position, bar/beat (from time signatures in the global stream), text ("Bb4 dotted crotchet"), properties, and Dorico's `eventID`.
- `diff.rs`: events are matched **by eventID**, so a moved or changed note shows as one change, not remove + add. An item deleted and re-entered identically (new ID) is cancelled out. Settings are flattened to paths; array items are keyed by their own ID (`layoutID=3`), so inserting a player doesn't shift everything. A whole added or removed item is reported once.
- `listing()` is the line-per-fact form for `git diff` textconv. It was byte-identical to the retired Python prototype on 32 real projects; it is now pinned by the golden tests (`engine/tests/golden`). Bar numbers follow Dorico (pick-up = 0, bar-number changes).
- Dynamics intensity: `{int: 0=forte|1=piano}, {}, {bool: mezzo}, {int: count}`. Confirmed against Dorico, mezzo included (STATUS.md gap 6). Force dynamics (sfz…) come from `ForceDynamicDefinition/type`.

## 9. Desktop app

- **Backend** (`app/src-tauri/src/main.rs`): state = settings + `Arc<Store>` + watcher. Commands: `status`, `save_settings`, `families`, `snapshots`, `diff`, `thumbnail` (raw PNG bytes via `ipc::Response`), `restore` (+ open in Dorico via the OS default app), `snapshot_now`, `add_milestone`/`remove_milestone`, `import_files`, `open_path`, `reveal`. Heavy work runs in `spawn_blocking`.
- **Background running**: closing the window hides it to the tray; "Quit" in the tray menu exits. `--hidden` starts in the tray (for start-on-login). Single-instance plugin: a second launch focuses the first.
- **Shared settings with the CLI**: `<data dir>/settings.json`, where data dir = `%LOCALAPPDATA%\dorigit` (override with `DORIGIT_DATA_DIR`). Default store `<data dir>\store`. Log: `<data dir>\dorigit.log`.
- **Frontend** (`app/src`): Svelte 5 runes, no UI framework. Three columns: projects | timeline (grouped by day, file colour rail, thumbnails, badges for milestone / playback kept / setup changed / imported, filter by file, keyboard ↑↓) | detail (actions, milestones, playback explanation, compare-with selector, `DiffView`). `lib/mock.ts` provides sample data when run in a plain browser (`npm run dev`), for UI work without Tauri.

## 10. Safety rules

- Never write to a user's `.dorico` file. The only file writes outside the store are restores, to **new** paths (refuses to overwrite).
- Store writes are serialised by a mutex in `Store`. `family.json` is written atomically (temp + rename). Two processes writing the same family at once (app + CLI) is not guarded (STATUS.md).
- Snapshots never fail silently: errors surface as `activity` error events or toasts, and in `dorigit.log`.

## 11. Decisions log

| Decision | Why |
|---|---|
| Tauri 2 + Rust core | Native, small, cross-platform; the core is shared with the CLI; your stated preference |
| git (libgit2 via `git2`, vendored) as storage | Content addressing, deltas, branches, tags for free; the repos stay inspectable with standard tools; no git install needed |
| One bare repo per family, not one global repo | Easy to delete, move or back up per project; no cross-project contention |
| Branch per file path | Mirrors how you already work (Save As = new idea) |
| Store decoded XML, not the DTN bytes | Deltas: 0.7 MB vs ~25 MB for 6 versions; byte-exact rebuild is proven |
| Playback by setup fingerprint | Keeps fidelity where it matters (the right plugins) at a fraction of the size |
| Windows GNU cross-build from WSL (zig) | Builds and smoke-tests the real Windows app without a Windows toolchain; MSVC/NSIS remains the path for installers |
| Settings in `%LOCALAPPDATA%`, store outside cloud folders | git repos and sync clients (OneDrive) don't mix well |
