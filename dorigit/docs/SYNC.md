# Remote backup and sync: design (not built yet)

*Drafted 2026-10-30 from your request: "connect to a repository (GitHub or otherwise / S3 / etc.)
so scores can be easily backed up and synced".*

## 1. What gets synced

dorigit's history is already a set of plain git repositories, one bare repo per project family
in the store (DESIGN.md §3–4). Syncing means pushing and fetching those repos: every snapshot,
branch (file), milestone (tag) and, depending on the remote, the playback data.

Never synced: your `.dorico` working files themselves (Dorico owns them; restore writes new
files), settings, the log.

## 2. Remote types

| Type | Examples | Good for | Limits / notes |
|---|---|---|---|
| **Folder** | external drive, NAS share, a second disk | Simplest backup; no account; fast | Must **not** be a cloud-synced folder holding a live repo (OneDrive/Dropbox corrupt repos with partial syncs). For cloud folders use **bundle mode**: immutable single-file bundles + a small index, written atomically |
| **Git hosting** | GitHub, GitLab, Bitbucket, Azure DevOps, self-hosted Gitea | Off-site backup, multi-machine sync, sharing with collaborators; browsable on the web | GitHub: files over 100 MB rejected, large repos discouraged (playback blobs are 2–25 MB each, so fine individually, but they add up); private repos; tokens/SSH keys |
| **Object storage** | AWS S3, Backblaze B2, Cloudflare R2, MinIO, Wasabi | Cheap bulk storage for playback data; long-term archive | Not browsable as git; dorigit uploads packs/bundles + a refs manifest; credentials needed |

**Playback per remote**: each remote has a "what to send" setting:
- *full* (everything dorigit stored),
- *music only* (skips `playback/enginedata` and previews; small and fast; good for GitHub),
- *full via object storage* (music to git hosting, playback blobs to S3/B2, referenced by hash).

## 3. Layout on the remote

- **One remote repo per project family** by default (e.g. `scores-harry-potter-cues`). Sharing is per project (an orchestrator gets access to one cue/project, not your whole catalogue). Deleting or archiving is per project.
- Option: **one catalogue repo** with refs namespaced per family (`refs/families/<id>/heads/…`), for people who prefer one repo.
- **Readable on the web** (option, on by default for git hosting): each snapshot also stores `listing.txt`, the musical listing (`dorigit show`). GitHub/GitLab's own diff view then shows musical changes ("bar 19 beat 1 dynamic ff → fff") to anyone browsing, without dorigit. It's text, so it delta-compresses well.

## 4. Behaviour

- **Push after each snapshot** (debounced, in the background, queued while offline). Status in the app: "Backed up 2 min ago" / "3 snapshots waiting (offline)".
- **Fetch** on start and periodically; new snapshots from other machines/collaborators appear in the timeline with their origin ("from studio PC", "from orchestrator").
- **Never rewrite history on the remote**: no force pushes outside dorigit's own bookkeeping refs.
- **Same file edited on two machines** (laptop and studio PC both saved "1m3 Chase"): the branches diverge. dorigit keeps both ("1m3 Chase @ laptop") and shows them as variants to merge (MERGE.md §5). Nothing is overwritten.
- **New machine / disaster recovery**: "Connect existing backup" clones the families; any version can then be restored (playback included if the remote has it).
- **Collaborators**: they can use dorigit with the same remote (their snapshots arrive as a branch), or just send a `.dorico` back, which goes through "Import incoming version" (MERGE.md §5.1). Either way the merge base is the milestone they started from.

## 5. Security and confidentiality

Film scores are usually under NDA.
- Remotes are **private** by default; dorigit warns if a git-hosting repo is public.
- Credentials go in the OS keychain (Windows Credential Manager), never in `settings.json`.
- **Client-side encryption** (option) for folder and object-storage remotes: bundles encrypted before upload (e.g. with `age`). Git hosting can't be encrypted transparently without breaking the web view, so offer *music only* + private, or object storage + encryption, for sensitive projects.

## 6. Prerequisites in dorigit (before sync)

1. ~~Machine-independent branch names~~ **Done 2026-10-31**: branches are named after the file ("1m3-chase"), with `-2` only for a different same-named file on one machine; old stores migrate on open (DESIGN.md §3).
2. ~~Cross-process store lock~~ **Done 2026-10-31** (`dorigit-core/src/lock.rs`).
3. Push/fetch must include `refs/dorigit/*` (variant info, MERGE.md §3), not only heads and tags.
4. **Packing** (STATUS.md B5): push/fetch and bundles work better on packed repos.

## 7. Implementation notes

- **git2 transports**: dorigit currently builds libgit2 without network support. HTTPS on Windows can use WinHTTP (no OpenSSL). SSH needs libssh2 (C; builds with the existing zig/MSVC setup). Alternative: `gix` (pure Rust, rustls) for fetch; its push support needs checking at implementation time.
- **Bundles / object storage**: write packfiles with libgit2's PackBuilder plus a JSON refs manifest; S3-compatible upload via a Rust S3 client. B2/R2/MinIO speak the same API.
- **Auth UX**: "Connect GitHub" through a device-code / browser sign-in (no copy-pasting tokens), other git hosts by URL + token or SSH key, S3 by endpoint + key pair.

## 8. Plan

| Step | Content |
|---|---|
| R0 | Prerequisites (§6) |
| R1 | Folder remote (bare mirror on a drive/NAS) + "Backed up" status + restore from it |
| R2 | Git hosting over HTTPS (GitHub first), *music only* / *full*, `listing.txt` option, keychain |
| R3 | Multi-machine sync: fetch, divergent-branch handling, origin labels |
| R4 | Object storage + bundle mode for cloud-synced folders; playback-to-S3 split |
| R5 | Encryption; collaborator sharing flows |

## Your answers (2026-10-30)

| Question | Answer | Effect on the plan |
|---|---|---|
| Services first | **GitHub (private), external drive/NAS, S3/B2/R2** (not cloud-synced folders for now) | R1 folder remote, R2 GitHub, R4 object storage all in scope; bundle mode for OneDrive/Dropbox can wait |
| Machines | **Two or more** | R3 multi-machine sync is required, so §6.1 machine-independent branch names are a must before any remote |
| Collaborators | **Both**: some use dorigit, some send files back | Support both §4 routes; "Import incoming version" (MERGE.md §5.1) needed regardless |
| NDA | **Private is enough by default; encryption switchable per project** when a client requires it | Per-family "encrypt this project" setting (§5). An encrypted family can't use GitHub's web view, so it goes to drive/NAS or object storage, or to git hosting as opaque encrypted bundles |
