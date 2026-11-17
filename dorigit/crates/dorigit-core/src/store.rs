//! The snapshot store: one bare git repository per Dorico "project family".
//!
//! ```text
//! <store>/
//!   c1609642780.git/            family = Dorico's info/createdDate (survives Save As)
//!     family.json               display name, file -> branch map, pending forks
//!     refs/heads/<file-slug>    one branch per .dorico file, named after the file (not its
//!                               folder), so the same file has the same branch on every machine
//!     refs/tags/<milestone>     annotated tags = milestones
//! ```
//!
//! Each commit's tree:
//!
//! ```text
//! dorigit.json            manifest (see manifest.rs): rebuild recipe + metadata
//! score.xml               decoded score (diffable, ~15-45 KB/version after delta)
//! scorelibrary.xml
//! thumb.png               downscaled first-page preview (if Dorico wrote one)
//! files/...               all other small zip entries, verbatim
//! playback/enginedata     only when the playback policy keeps it (see policy.rs)
//! ```
//!
//! Parent selection (how Save As becomes branching):
//! 1. a pending fork (the file was written by `restore`) -> that commit
//! 2. the tip of this file's branch
//! 3. otherwise the family's most recent snapshot (the file was "Saved As" from it)
//!
//! Writes hold the family's cross-process lock (`lock.rs`) as well as an in-process mutex.

use crate::lock::{FamilyLock, lock_family};
use crate::manifest::*;
use crate::policy::{PlaybackPolicy, PlaybackReason};
use anyhow::{Context, Result, anyhow, bail};
use dorico_format::container::{self, ENGINE_DATA, PREVIEW_PDF, PREVIEW_PNG};
use dorico_format::diff::ScoreDiff;
use crate::listing;
use dorico_format::{Project, Score, dtn, playback, xml};
use git2::{ObjectType, Oid, Repository, Signature, Sort};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, HashMap};
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};
use std::time::Duration;

const FAMILY_FILE: &str = "family.json";
const SCORE_CACHE: usize = 6;
/// How long a write waits for another process (e.g. a snapshot of a large project) to finish.
pub const DEFAULT_LOCK_TIMEOUT: Duration = Duration::from_secs(30);

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct FamilyMeta {
    pub id: String,
    /// Name shown in the UI: stem of the most recently snapshotted file.
    pub display_name: String,
    /// Dorico's project title (often "Untitled Project 1"...).
    pub title: String,
    /// This machine's normalised file paths -> branch name. Local only (never synced): another
    /// machine maps its own paths to the same, machine-independent branch names.
    pub files: BTreeMap<String, String>,
    /// Normalised file path -> commit it was restored from (consumed on first snapshot).
    pub pending_forks: BTreeMap<String, String>,
    pub last_snapshot: Option<i64>,
    pub snapshot_count: usize,
}

#[derive(Debug, Clone, Serialize)]
pub struct Milestone {
    pub name: String,
    pub message: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct SnapshotInfo {
    pub family: String,
    pub id: String,
    pub short_id: String,
    pub parents: Vec<String>,
    /// Dorico's save time (unix seconds, UTC)
    pub time: i64,
    pub branches: Vec<String>,
    pub file_name: String,
    pub path: String,
    pub kind: SnapshotKind,
    pub milestones: Vec<Milestone>,
    pub summary: Summary,
    pub playback_stored: bool,
    pub playback_reason: PlaybackReason,
    /// Snapshot whose playback a restore of this one would use (if not stored here).
    pub playback_borrow_from: Option<String>,
    /// e.g. ["+1 Kontakt"]: plugin setup changes since the parent.
    pub playback_setup_changes: Vec<String>,
    pub has_thumb: bool,
    pub dorico_version: String,
    pub title: String,
}

#[derive(Debug, Clone, Serialize)]
#[serde(tag = "outcome", rename_all = "snake_case")]
#[allow(clippy::large_enum_variant)] // short-lived return value
pub enum SnapshotOutcome {
    Created {
        snapshot: SnapshotInfo,
    },
    /// File content identical to an existing snapshot; the file's branch now points at it.
    Unchanged {
        family: String,
        id: String,
    },
}

#[derive(Debug, Clone, Serialize)]
pub struct RestoreOutcome {
    pub path: PathBuf,
    /// If the snapshot had no playback state, the snapshot it was borrowed from.
    pub playback_from: Option<String>,
    /// Zip entries that could not be restored (e.g. previews; Dorico rewrites them on save).
    pub omitted: Vec<String>,
}

pub struct Store {
    root: PathBuf,
    pub policy: PlaybackPolicy,
    /// How long writes wait for another process holding the family lock.
    pub lock_timeout: Duration,
    write_lock: Mutex<()>,
    scores: Mutex<Vec<(Oid, Arc<Score>)>>,
}

/// Normalised key for a file path (forward slashes; case-folded on Windows).
pub fn path_key(path: &Path) -> String {
    let abs = path.canonicalize().unwrap_or_else(|_| path.to_path_buf());
    let s = abs.to_string_lossy().replace('\\', "/");
    if cfg!(windows) { s.to_lowercase() } else { s }
}

/// A `path_key` back as a path that can be checked on this machine.
fn key_path(key: &str) -> PathBuf {
    if cfg!(windows) { PathBuf::from(key.replace('/', "\\")) } else { PathBuf::from(key) }
}

fn slug(s: &str, max: usize) -> String {
    let mut out = String::new();
    for ch in s.chars() {
        if ch.is_ascii_alphanumeric() {
            out.push(ch.to_ascii_lowercase());
        } else if !out.ends_with('-') {
            out.push('-');
        }
    }
    let out = out.trim_matches('-');
    let out: String = out.chars().take(max).collect();
    let out = out.trim_end_matches('-').to_owned();
    if out.is_empty() { "untitled".into() } else { out }
}

/// Base branch name for a file: a slug of its name, e.g. "1m3 Chase.dorico" -> "1m3-chase".
/// Machine-independent (SYNC.md §6.1), so laptop and studio PC share a file's history.
pub fn branch_base(path: &Path) -> String {
    let stem = path.file_stem().map(|s| s.to_string_lossy().to_string()).unwrap_or_default();
    slug(&stem, 48)
}

/// Branch for `path` in `meta`: its recorded branch, else the base name, numbered ("-2", "-3")
/// only if a *different* file on this machine that still exists already uses it.
fn branch_for(meta: &FamilyMeta, key: &str, path: &Path) -> String {
    if let Some(b) = meta.files.get(key) {
        return b.clone();
    }
    let base = branch_base(path);
    let taken = |name: &str| meta.files.iter().any(|(k, b)| b == name && k != key && key_path(k).exists());
    let mut name = base.clone();
    let mut n = 2;
    while taken(&name) {
        name = format!("{base}-{n}");
        n += 1;
    }
    name
}

/// Pre-2026-10-31 branch names were slug + a hash of this machine's full path ("cue-1a2b3c");
/// `key` is that path, so the old name can be recomputed exactly.
fn is_legacy_branch(key: &str, name: &str) -> bool {
    let stem = Path::new(key).file_stem().map(|s| s.to_string_lossy().to_string()).unwrap_or_default();
    let h = Oid::hash_object(ObjectType::Blob, key.as_bytes()).expect("sha1");
    name == format!("{}-{}", slug(&stem, 40), &h.to_string()[..6])
}

pub fn family_id(dorico: &DoricoInfo, path: &Path) -> String {
    if !dorico.created_date.is_empty() && dorico.created_date.chars().all(|c| c.is_ascii_digit()) {
        return format!("c{}", dorico.created_date);
    }
    let h = Oid::hash_object(ObjectType::Blob, path_key(path).as_bytes()).expect("sha1");
    format!("p{}", &h.to_string()[..12])
}

fn dorico_info(score: &dtn::Document) -> DoricoInfo {
    let i = score.root.child("info");
    let t = |k: &str| i.map(|n| n.text(k)).unwrap_or("").to_owned();
    DoricoInfo {
        title: t("title"),
        created_date: t("createdDate"),
        created_version: t("createdVersion"),
        last_saved_version: t("lastSavedVersion"),
        last_saved_date: t("lastSavedDate").parse().ok(),
    }
}

fn mtime_secs(m: &fs::Metadata) -> i64 {
    m.modified()
        .ok()
        .and_then(|t| t.duration_since(std::time::UNIX_EPOCH).ok())
        .map(|d| d.as_secs() as i64)
        .unwrap_or(0)
}

fn write_tree(repo: &Repository, files: &BTreeMap<String, Oid>) -> Result<Oid> {
    let mut tb = repo.treebuilder(None)?;
    let mut dirs: BTreeMap<&str, BTreeMap<String, Oid>> = BTreeMap::new();
    for (path, oid) in files {
        match path.split_once('/') {
            Some((head, rest)) => {
                dirs.entry(head).or_default().insert(rest.to_owned(), *oid);
            }
            None => {
                tb.insert(path, *oid, 0o100644)?;
            }
        }
    }
    for (dir, sub) in dirs {
        let t = write_tree(repo, &sub)?;
        tb.insert(dir, t, 0o040000)?;
    }
    Ok(tb.write()?)
}

pub(crate) fn read_path(repo: &Repository, tree: &git2::Tree, path: &str) -> Result<Vec<u8>> {
    let entry = tree.get_path(Path::new(path)).with_context(|| format!("snapshot has no {path}"))?;
    Ok(repo.find_blob(entry.id())?.content().to_vec())
}

fn read_manifest(repo: &Repository, commit: &git2::Commit) -> Result<Manifest> {
    let bytes = read_path(repo, &commit.tree()?, MANIFEST_PATH)?;
    serde_json::from_slice(&bytes).context("reading dorigit.json")
}

fn make_thumbnail(png: &[u8]) -> Option<Vec<u8>> {
    let img = image::load_from_memory_with_format(png, image::ImageFormat::Png).ok()?;
    let small = img.thumbnail(420, 600);
    let mut out = std::io::Cursor::new(Vec::new());
    small.write_to(&mut out, image::ImageFormat::Png).ok()?;
    Some(out.into_inner())
}

fn content_id(entries: &[Entry]) -> String {
    let mut s = String::new();
    for e in entries.iter().filter(|e| !e.is_dir) {
        s.push_str(&e.name);
        s.push('\0');
        s.push_str(&e.blob);
        s.push('\n');
    }
    Oid::hash_object(ObjectType::Blob, s.as_bytes()).expect("sha1").to_string()
}

impl Store {
    pub fn open(root: impl Into<PathBuf>, policy: PlaybackPolicy) -> Result<Store> {
        let root = root.into();
        fs::create_dir_all(&root).with_context(|| format!("creating store {}", root.display()))?;
        let store = Store {
            root,
            policy,
            lock_timeout: DEFAULT_LOCK_TIMEOUT,
            write_lock: Mutex::new(()),
            scores: Mutex::new(Vec::new()),
        };
        // best effort: busy or unreadable families are migrated on their next snapshot
        let _ = store.migrate();
        Ok(store)
    }

    pub fn root(&self) -> &Path {
        &self.root
    }

    pub(crate) fn repo_dir(&self, family: &str) -> PathBuf {
        self.root.join(format!("{family}.git"))
    }

    /// Cross-process lock for writing to `family` (see `lock.rs`).
    pub fn lock_family(&self, family: &str) -> Result<FamilyLock> {
        lock_family(&self.repo_dir(family), self.lock_timeout)
    }

    pub(crate) fn repo(&self, family: &str) -> Result<Repository> {
        Repository::open_bare(self.repo_dir(family)).with_context(|| format!("unknown project family {family}"))
    }

    pub(crate) fn load_family(&self, family: &str) -> Result<FamilyMeta> {
        let p = self.repo_dir(family).join(FAMILY_FILE);
        match fs::read(&p) {
            Ok(b) => Ok(serde_json::from_slice(&b)?),
            Err(_) => Ok(FamilyMeta { id: family.into(), ..Default::default() }),
        }
    }

    pub(crate) fn save_family(&self, meta: &FamilyMeta) -> Result<()> {
        let p = self.repo_dir(&meta.id).join(FAMILY_FILE);
        let tmp = p.with_extension("json.tmp");
        fs::write(&tmp, serde_json::to_vec_pretty(meta)?)?;
        fs::rename(tmp, p)?;
        Ok(())
    }

    /// All project families in the store, most recently snapshotted first.
    pub fn families(&self) -> Result<Vec<FamilyMeta>> {
        let mut out = Vec::new();
        for e in fs::read_dir(&self.root)? {
            let p = e?.path();
            if let Some(id) = p.file_name().and_then(|n| n.to_str()).and_then(|n| n.strip_suffix(".git"))
                && p.join(FAMILY_FILE).exists()
            {
                out.push(self.load_family(id)?);
            }
        }
        out.sort_by_key(|f| std::cmp::Reverse(f.last_snapshot));
        Ok(out)
    }

    /// Family a file belongs to, if it has been snapshotted.
    pub fn family_of_file(&self, path: &Path) -> Result<Option<String>> {
        let key = path_key(path);
        Ok(self.families()?.into_iter().find(|f| f.files.contains_key(&key)).map(|f| f.id))
    }

    fn cached_score(&self, id: Oid) -> Option<Arc<Score>> {
        self.scores.lock().unwrap().iter().find(|(o, _)| *o == id).map(|(_, s)| s.clone())
    }

    fn cache_score(&self, id: Oid, s: Arc<Score>) {
        let mut c = self.scores.lock().unwrap();
        c.retain(|(o, _)| *o != id);
        c.push((id, s));
        if c.len() > SCORE_CACHE {
            c.remove(0);
        }
    }

    pub(crate) fn score_at(&self, repo: &Repository, id: Oid) -> Result<Arc<Score>> {
        if let Some(s) = self.cached_score(id) {
            return Ok(s);
        }
        let commit = repo.find_commit(id)?;
        let xml = read_path(repo, &commit.tree()?, SCORE_PATH)?;
        let score = Arc::new(listing::build(&xml::from_xml(&xml)?.root));
        self.cache_score(id, score.clone());
        Ok(score)
    }

    fn latest_commit(repo: &Repository) -> Result<Option<Oid>> {
        let mut best: Option<(i64, Oid)> = None;
        for r in repo.references_glob("refs/heads/*")? {
            if let Ok(c) = r?.peel_to_commit() {
                let t = c.time().seconds();
                if best.is_none_or(|(bt, _)| t > bt) {
                    best = Some((t, c.id()));
                }
            }
        }
        Ok(best.map(|(_, o)| o))
    }

    /// Snapshot a .dorico file. `milestone` = Some(name) also tags it and keeps playback.
    pub fn snapshot_file(&self, path: &Path, kind: SnapshotKind, milestone: Option<&str>) -> Result<SnapshotOutcome> {
        let _guard = self.write_lock.lock().unwrap();
        let fs_meta = fs::metadata(path).with_context(|| format!("reading {}", path.display()))?;
        let project = Project::read(path)?;
        let score_doc = project.score()?;
        let dorico = dorico_info(&score_doc);
        let family = family_id(&dorico, path);
        let repo_dir = self.repo_dir(&family);
        let _family_lock = self.lock_family(&family)?; // creates repo_dir if needed
        let repo = if repo_dir.join("HEAD").exists() {
            Repository::open_bare(&repo_dir)?
        } else {
            Repository::init_bare(&repo_dir)?
        };
        let mut meta = self.load_family(&family)?;

        if Self::migrate_branches(&repo, &mut meta)? {
            self.save_family(&meta)?;
        }
        let key = path_key(path);
        let branch = branch_for(&meta, &key, path);
        let refname = format!("refs/heads/{branch}");
        let tip = repo.refname_to_id(&refname).ok();
        let pending = meta.pending_forks.get(&key).and_then(|s| Oid::from_str(s).ok());
        let parent = match pending.or(tip) {
            Some(p) => Some(p),
            None => Self::latest_commit(&repo)?,
        };
        let parent_manifest = match parent {
            Some(p) => read_manifest(&repo, &repo.find_commit(p)?).ok(),
            None => None,
        };

        // Playback: compare the plugin setup with the parent's, then apply the policy.
        let engine = project.get(ENGINE_DATA);
        let setup = engine.and_then(|e| playback::read_setup(&e.data));
        let setup_id = match &setup {
            Some(s) => Some(Oid::hash_object(ObjectType::Blob, s.canonical().as_bytes())?.to_string()),
            None => None,
        };
        let parent_pb = parent_manifest.as_ref().map(|m| &m.playback).filter(|pb| pb.present);
        let setup_changed = match (parent_pb, &setup_id) {
            (Some(pp), Some(id)) => pp.setup_id.as_deref() != Some(id.as_str()),
            _ => false,
        };
        // nearest earlier snapshot holding playback with this same setup
        let borrow = match parent_pb {
            Some(pp) if !setup_changed => {
                if pp.stored {
                    parent.map(|p| p.to_string())
                } else {
                    pp.borrow_from.clone()
                }
            }
            _ => None,
        };
        let setup_changes = match (parent_pb.and_then(|pp| pp.setup.as_ref()), &setup) {
            (Some(old), Some(new)) => new.changes_from(old),
            _ => Vec::new(),
        };
        let engine_size = engine.map(|e| e.data.len() as u64);
        let (mut keep_playback, mut reason) =
            self.policy.decide(milestone.is_some(), borrow.is_some(), setup_changed, engine_size);
        if let Some(e) = engine {
            let id = Oid::hash_object(ObjectType::Blob, &e.data)?;
            if !keep_playback && repo.odb()?.exists(id) {
                // identical bytes already stored once: referencing them is free
                keep_playback = true;
                reason = PlaybackReason::Unchanged;
            }
        }

        let mut files: BTreeMap<String, Oid> = BTreeMap::new();
        let mut entries = Vec::new();
        let mut playback = Playback {
            present: false,
            stored: false,
            reason,
            blob: None,
            size: 0,
            setup,
            setup_id,
            borrow_from: if keep_playback { None } else { borrow },
            setup_changes,
        };
        let mut thumb = None;
        for e in &project.entries {
            if e.is_dir {
                entries.push(Entry {
                    name: e.name.clone(),
                    time: e.time,
                    deflated: e.deflated,
                    is_dir: true,
                    stored_at: None,
                    form: None,
                    blob: String::new(),
                    size: 0,
                });
                continue;
            }
            let blob = Oid::hash_object(ObjectType::Blob, &e.data)?;
            let (stored_at, form, bytes): (Option<String>, Option<PartForm>, std::borrow::Cow<[u8]>) = match e
                .name
                .as_str()
            {
                "score.dtn" => {
                    (Some(SCORE_PATH.into()), Some(PartForm::Dtn), xml::to_xml(&score_doc, true).into_bytes().into())
                }
                "score.xml" => (Some(SCORE_PATH.into()), Some(PartForm::Xml), (&e.data[..]).into()),
                "scorelibrary.dtn" => {
                    let doc = dtn::decode(&e.data).context("decoding scorelibrary.dtn")?;
                    (Some(LIBRARY_PATH.into()), Some(PartForm::Dtn), xml::to_xml(&doc, true).into_bytes().into())
                }
                "scorelibrary.xml" => (Some(LIBRARY_PATH.into()), Some(PartForm::Xml), (&e.data[..]).into()),
                ENGINE_DATA => {
                    playback.present = true;
                    playback.blob = Some(blob.to_string());
                    playback.size = e.data.len() as u64;
                    playback.stored = keep_playback;
                    (keep_playback.then(|| PLAYBACK_PATH.into()), None, (&e.data[..]).into())
                }
                PREVIEW_PNG | PREVIEW_PDF => {
                    if e.name == PREVIEW_PNG {
                        thumb = make_thumbnail(&e.data);
                    }
                    (keep_playback.then(|| format!("{FILES_DIR}/{}", e.name)), None, (&e.data[..]).into())
                }
                other => (Some(format!("{FILES_DIR}/{other}")), None, (&e.data[..]).into()),
            };
            if let Some(at) = &stored_at {
                files.insert(at.clone(), repo.blob(&bytes)?);
            }
            entries.push(Entry {
                name: e.name.clone(),
                time: e.time,
                deflated: e.deflated,
                is_dir: false,
                stored_at,
                form,
                blob: blob.to_string(),
                size: e.data.len() as u64,
            });
        }
        if let Some(t) = &thumb {
            files.insert(THUMB_PATH.into(), repo.blob(t)?);
        }
        let content = content_id(&entries);

        // Identical to the parent? Just point this file's branch at it.
        if let Some(p) = parent {
            let pc = repo.find_commit(p)?;
            if read_manifest(&repo, &pc).map(|m| m.content_id == content).unwrap_or(false) {
                repo.reference(&refname, p, true, "dorigit: unchanged")?;
                meta.files.insert(key.clone(), branch);
                meta.pending_forks.remove(&key);
                self.save_family(&meta)?;
                return Ok(SnapshotOutcome::Unchanged { family, id: p.to_string() });
            }
        }

        // Musical summary against the parent.
        let score = Arc::new(listing::build(&score_doc.root));
        let summary = match parent {
            Some(p) => match self.score_at(&repo, p) {
                Ok(prev) => {
                    let d = crate::tidy::diff(&prev, &score);
                    Summary {
                        text: d.summary(),
                        music_changes: d.music_changes(),
                        setting_changes: d.setting_changes(),
                        parent: Some(p.to_string()),
                    }
                }
                Err(e) => Summary {
                    text: format!("(could not compare: {e})"),
                    parent: Some(p.to_string()),
                    ..Default::default()
                },
            },
            None => Summary { text: "first snapshot".into(), ..Default::default() },
        };

        let file_name = path.file_name().map(|s| s.to_string_lossy().to_string()).unwrap_or_default();
        let manifest = Manifest {
            format: FORMAT,
            kind,
            source: Source {
                path: path.to_string_lossy().to_string(),
                file_name: file_name.clone(),
                size: fs_meta.len(),
                modified: mtime_secs(&fs_meta),
            },
            dorico: dorico.clone(),
            entries,
            playback,
            content_id: content,
            summary: summary.clone(),
            has_thumb: thumb.is_some(),
        };
        files.insert(MANIFEST_PATH.into(), repo.blob(&serde_json::to_vec_pretty(&manifest)?)?);
        let tree = repo.find_tree(write_tree(&repo, &files)?)?;

        let when = dorico.last_saved_date.unwrap_or_else(|| mtime_secs(&fs_meta));
        let sig = Signature::new("dorigit", "dorigit@localhost", &git2::Time::new(when, 0))?;
        let mut message = format!("{file_name}: {}\n", summary.text);
        if let Some(m) = milestone {
            message.push_str(&format!("\nMilestone: {m}\n"));
        }
        let parent_commit = parent.map(|p| repo.find_commit(p)).transpose()?;
        let parents: Vec<&git2::Commit> = parent_commit.iter().collect();
        let id = repo.commit(None, &sig, &sig, &message, &tree, &parents)?;
        repo.reference(&refname, id, true, "dorigit: snapshot")?;
        self.cache_score(id, score);
        if let Some(m) = milestone {
            self.tag(&repo, id, m)?;
        }

        meta.files.insert(key.clone(), branch);
        meta.pending_forks.remove(&key);
        meta.display_name = path.file_stem().map(|s| s.to_string_lossy().to_string()).unwrap_or_default();
        meta.title = dorico.title.clone();
        meta.last_snapshot = Some(when.max(meta.last_snapshot.unwrap_or(0)));
        meta.snapshot_count += 1;
        self.save_family(&meta)?;

        let info = self.info_for(&repo, &family, id, &self.branch_index(&repo)?, &self.milestone_index(&repo)?)?;
        Ok(SnapshotOutcome::Created { snapshot: info })
    }

    /// Rename old path-hash branches ("cue-1a2b3c") to machine-independent names ("cue").
    /// Caller holds the family lock. Returns whether `meta` changed.
    fn migrate_branches(repo: &Repository, meta: &mut FamilyMeta) -> Result<bool> {
        let legacy: Vec<(String, String)> =
            meta.files.iter().filter(|(k, b)| is_legacy_branch(k, b)).map(|(k, b)| (k.clone(), b.clone())).collect();
        let mut changed = false;
        for (key, old) in legacy {
            let mut without = meta.clone();
            without.files.remove(&key);
            let mut new = branch_for(&without, &key, Path::new(&key));
            // never collide with a branch that already exists for another file
            let base = new.clone();
            let mut n = 2;
            while repo.find_reference(&format!("refs/heads/{new}")).is_ok() && new != old {
                new = format!("{base}-{n}");
                n += 1;
            }
            if let Ok(mut r) = repo.find_reference(&format!("refs/heads/{old}")) {
                r.rename(&format!("refs/heads/{new}"), false, "dorigit: machine-independent branch name")?;
            }
            meta.files.insert(key, new);
            changed = true;
        }
        Ok(changed)
    }

    /// Bring every family up to date (branch names), skipping families busy in another process.
    /// Safe to call at startup; returns how many families changed.
    pub fn migrate(&self) -> Result<usize> {
        let mut count = 0;
        for fam in self.families()? {
            let Ok(_lock) = lock_family(&self.repo_dir(&fam.id), Duration::from_millis(500)) else { continue };
            let mut meta = self.load_family(&fam.id)?;
            if Self::migrate_branches(&self.repo(&fam.id)?, &mut meta)? {
                self.save_family(&meta)?;
                count += 1;
            }
        }
        Ok(count)
    }

    fn tag(&self, repo: &Repository, id: Oid, name: &str) -> Result<()> {
        let obj = repo.find_object(id, Some(ObjectType::Commit))?;
        let sig = Signature::now("dorigit", "dorigit@localhost")?;
        let short = &id.to_string()[..7];
        let tag_name = format!("{}-{short}", slug(name, 40));
        repo.tag(&tag_name, &obj, &sig, name, true)?;
        Ok(())
    }

    /// Mark an existing snapshot as a milestone. (Playback is kept only if the
    /// snapshot already stored it; use `snapshot_file(.., Some(name))` to
    /// capture the current file with full playback.)
    pub fn add_milestone(&self, family: &str, id: &str, name: &str) -> Result<()> {
        let _guard = self.write_lock.lock().unwrap();
        let repo = self.repo(family)?;
        let _family_lock = self.lock_family(family)?;
        self.tag(&repo, Oid::from_str(id)?, name)
    }

    pub fn remove_milestone(&self, family: &str, id: &str, name: &str) -> Result<()> {
        let _guard = self.write_lock.lock().unwrap();
        let repo = self.repo(family)?;
        let _family_lock = self.lock_family(family)?;
        let tag_name = format!("{}-{}", slug(name, 40), &id[..7.min(id.len())]);
        repo.tag_delete(&tag_name)?;
        Ok(())
    }

    fn branch_index(&self, repo: &Repository) -> Result<HashMap<Oid, Vec<String>>> {
        let mut m: HashMap<Oid, Vec<String>> = HashMap::new();
        for r in repo.references_glob("refs/heads/*")? {
            let r = r?;
            if let (Some(name), Ok(c)) = (r.shorthand().map(str::to_owned), r.peel_to_commit()) {
                m.entry(c.id()).or_default().push(name);
            }
        }
        Ok(m)
    }

    fn milestone_index(&self, repo: &Repository) -> Result<HashMap<Oid, Vec<Milestone>>> {
        let mut m: HashMap<Oid, Vec<Milestone>> = HashMap::new();
        for r in repo.references_glob("refs/tags/*")? {
            let r = r?;
            let Ok(c) = r.peel_to_commit() else { continue };
            let message = r.peel_to_tag().ok().and_then(|t| t.message().map(str::to_owned)).unwrap_or_default();
            let name = message.lines().next().unwrap_or("").to_owned();
            m.entry(c.id()).or_default().push(Milestone { name, message });
        }
        Ok(m)
    }

    fn info_for(
        &self,
        repo: &Repository,
        family: &str,
        id: Oid,
        branches: &HashMap<Oid, Vec<String>>,
        milestones: &HashMap<Oid, Vec<Milestone>>,
    ) -> Result<SnapshotInfo> {
        let c = repo.find_commit(id)?;
        let m = read_manifest(repo, &c)?;
        Ok(SnapshotInfo {
            family: family.into(),
            id: id.to_string(),
            short_id: id.to_string()[..7].into(),
            parents: c.parent_ids().map(|p| p.to_string()).collect(),
            time: c.time().seconds(),
            branches: branches.get(&id).cloned().unwrap_or_default(),
            file_name: m.source.file_name,
            path: m.source.path,
            kind: m.kind,
            milestones: milestones.get(&id).cloned().unwrap_or_default(),
            summary: m.summary,
            playback_stored: m.playback.stored,
            playback_reason: m.playback.reason,
            playback_borrow_from: m.playback.borrow_from.clone(),
            playback_setup_changes: m.playback.setup_changes.clone(),
            has_thumb: m.has_thumb,
            dorico_version: m.dorico.last_saved_version,
            title: m.dorico.title,
        })
    }

    /// All snapshots in a family, newest first.
    pub fn snapshots(&self, family: &str) -> Result<Vec<SnapshotInfo>> {
        let repo = self.repo(family)?;
        let branches = self.branch_index(&repo)?;
        let milestones = self.milestone_index(&repo)?;
        let mut walk = repo.revwalk()?;
        walk.set_sorting(Sort::TOPOLOGICAL | Sort::TIME)?;
        walk.push_glob("refs/heads/*")?;
        walk.push_glob("refs/tags/*")?;
        let mut out = Vec::new();
        for id in walk {
            out.push(self.info_for(&repo, family, id?, &branches, &milestones)?);
        }
        Ok(out)
    }

    pub fn manifest(&self, family: &str, id: &str) -> Result<Manifest> {
        let repo = self.repo(family)?;
        read_manifest(&repo, &repo.find_commit(Oid::from_str(id)?)?)
    }

    pub fn score(&self, family: &str, id: &str) -> Result<Arc<Score>> {
        let repo = self.repo(family)?;
        self.score_at(&repo, Oid::from_str(id)?)
    }

    /// Musical diff from `old` (default: the snapshot's parent) to `new`.
    pub fn diff(&self, family: &str, old: Option<&str>, new: &str) -> Result<ScoreDiff> {
        let repo = self.repo(family)?;
        let new_id = Oid::from_str(new)?;
        let old_id = match old {
            Some(o) => Oid::from_str(o)?,
            None => match repo.find_commit(new_id)?.parent_ids().next() {
                Some(p) => p,
                None => bail!("first snapshot has nothing to compare with"),
            },
        };
        let (a, b) = (self.score_at(&repo, old_id)?, self.score_at(&repo, new_id)?);
        Ok(crate::tidy::diff(&a, &b))
    }

    fn score_root(&self, repo: &Repository, id: Oid) -> Result<dtn::Document> {
        let xml = read_path(repo, &repo.find_commit(id)?.tree()?, SCORE_PATH)?;
        xml::from_xml(&xml)
    }

    /// Notation (MEI) of a bar range of a snapshot (`notation.rs`).
    pub fn notation(&self, family: &str, id: &str, req: &crate::notation::Request) -> Result<String> {
        let repo = self.repo(family)?;
        crate::notation::render(&self.score_root(&repo, Oid::from_str(id)?)?.root, req)
    }

    /// Before/after notation of one flow's changed bars between `old` (default: parent) and `new`.
    pub fn notation_diff(
        &self,
        family: &str,
        old: Option<&str>,
        new: &str,
        flow_id: &str,
    ) -> Result<crate::notation::DiffNotation> {
        let repo = self.repo(family)?;
        let new_id = Oid::from_str(new)?;
        let old_id = match old {
            Some(o) => Oid::from_str(o)?,
            None => repo.find_commit(new_id)?.parent_ids().next().context("first snapshot has nothing to compare with")?,
        };
        let d = self.diff(family, Some(&old_id.to_string()), new)?;
        let (a, b) = (self.score_root(&repo, old_id)?, self.score_root(&repo, new_id)?);
        crate::notation::diff_notation(&a.root, &b.root, &d, flow_id)
    }

    /// Merge preview of two snapshots (`merge.rs`); `base` defaults to their common ancestor.
    pub fn merge_preview(
        &self,
        family: &str,
        ours: &str,
        theirs: &str,
        base: Option<&str>,
    ) -> Result<crate::merge::Preview> {
        let repo = self.repo(family)?;
        let (o, t) = (Oid::from_str(ours)?, Oid::from_str(theirs)?);
        let b = match base {
            Some(b) => Oid::from_str(b)?,
            None => repo.merge_base(o, t).context("these versions have no common ancestor; choose a base")?,
        };
        let (sb, so, st) = (self.score_at(&repo, b)?, self.score_at(&repo, o)?, self.score_at(&repo, t)?);
        let mut p = crate::merge::preview(&sb, &so, &st);
        for (label, id) in [("ours", o), ("theirs", t)] {
            for problem in dorico_format::ids::check(&self.score_root(&repo, id)?.root) {
                p.integrity.push(format!("{label}: {problem}"));
            }
        }
        Ok(p)
    }

    pub fn thumbnail(&self, family: &str, id: &str) -> Result<Option<Vec<u8>>> {
        let repo = self.repo(family)?;
        let tree = repo.find_commit(Oid::from_str(id)?)?.tree()?;
        Ok(read_path(&repo, &tree, THUMB_PATH).ok())
    }

    /// Find stored playback for a snapshot: an identical stored blob, the
    /// recorded `borrow_from` snapshot (same plugin setup), or as a last resort
    /// the nearest ancestor that kept one.
    fn find_playback(&self, repo: &Repository, id: Oid, m: &Manifest) -> Result<Option<(Vec<u8>, Option<Oid>)>> {
        if let Some(b) = m.playback.blob.as_deref().and_then(|b| Oid::from_str(b).ok())
            && let Ok(blob) = repo.find_blob(b)
        {
            return Ok(Some((blob.content().to_vec(), None)));
        }
        if let Some(from) = m.playback.borrow_from.as_deref().and_then(|b| Oid::from_str(b).ok())
            && let Ok(c) = repo.find_commit(from)
            && let Ok(bytes) = read_path(repo, &c.tree()?, PLAYBACK_PATH)
        {
            return Ok(Some((bytes, Some(from))));
        }
        let mut walk = repo.revwalk()?;
        walk.set_sorting(Sort::TOPOLOGICAL | Sort::TIME)?;
        walk.push(id)?;
        for anc in walk.skip(1) {
            let c = repo.find_commit(anc?)?;
            if let Ok(am) = read_manifest(repo, &c)
                && am.playback.stored
            {
                return Ok(Some((read_path(repo, &c.tree()?, PLAYBACK_PATH)?, Some(c.id()))));
            }
        }
        Ok(None)
    }

    /// Rebuild a snapshot as a new .dorico file. Never overwrites.
    pub fn restore(&self, family: &str, id: &str, dest: &Path) -> Result<RestoreOutcome> {
        let _guard = self.write_lock.lock().unwrap();
        if dest.exists() {
            bail!("{} already exists", dest.display());
        }
        let repo = self.repo(family)?;
        let oid = Oid::from_str(id)?;
        let commit = repo.find_commit(oid)?;
        let tree = commit.tree()?;
        let m = read_manifest(&repo, &commit)?;
        let mut project = Project::default();
        let mut playback_from = None;
        let mut omitted = Vec::new();
        for e in &m.entries {
            let data = if e.is_dir {
                Vec::new()
            } else if let Some(at) = &e.stored_at {
                let bytes = read_path(&repo, &tree, at)?;
                match e.form {
                    Some(PartForm::Dtn) => dtn::encode(&xml::from_xml(&bytes)?),
                    _ => bytes,
                }
            } else if e.name == ENGINE_DATA {
                match self.find_playback(&repo, oid, &m)? {
                    Some((bytes, from)) => {
                        playback_from = from.map(|o| o.to_string());
                        bytes
                    }
                    None => {
                        omitted.push(e.name.clone());
                        continue;
                    }
                }
            } else if let Ok(blob) = repo.find_blob(Oid::from_str(&e.blob)?) {
                blob.content().to_vec() // e.g. an identical preview stored elsewhere
            } else {
                omitted.push(e.name.clone());
                continue;
            };
            project.entries.push(container::Entry {
                name: e.name.clone(),
                data,
                is_dir: e.is_dir,
                time: e.time,
                deflated: e.deflated,
            });
        }
        if let Some(parent) = dest.parent() {
            fs::create_dir_all(parent)?;
        }
        project.write(dest)?;

        let _family_lock = self.lock_family(family)?;
        let mut meta = self.load_family(family)?;
        meta.pending_forks.insert(path_key(dest), id.to_owned());
        self.save_family(&meta)?;
        Ok(RestoreOutcome { path: dest.to_path_buf(), playback_from, omitted })
    }

    /// A free file name like "Cue (restored a1b2c3d).dorico" in `dir`.
    pub fn restore_path(dir: &Path, original_file_name: &str, short_id: &str) -> PathBuf {
        let stem =
            Path::new(original_file_name).file_stem().map(|s| s.to_string_lossy().to_string()).unwrap_or_default();
        let mut n = 1;
        loop {
            let suffix = if n == 1 { String::new() } else { format!(" {n}") };
            let p = dir.join(format!("{stem} (restored {short_id}{suffix}).dorico"));
            if !p.exists() {
                return p;
            }
            n += 1;
        }
    }

    /// Import existing files (e.g. "Cue 2", "Cue 3", ...) in Dorico save order.
    pub fn import(&self, paths: &[PathBuf]) -> Vec<(PathBuf, Result<SnapshotOutcome>)> {
        let mut dated: Vec<(i64, PathBuf)> = paths
            .iter()
            .map(|p| {
                let t = Project::read(p)
                    .and_then(|pr| pr.score())
                    .ok()
                    .and_then(|d| dorico_info(&d).last_saved_date)
                    .unwrap_or_else(|| fs::metadata(p).map(|m| mtime_secs(&m)).unwrap_or(0));
                (t, p.clone())
            })
            .collect();
        dated.sort();
        dated
            .into_iter()
            .map(|(_, p)| {
                let r = self.snapshot_file(&p, SnapshotKind::Import, None);
                (p, r)
            })
            .collect()
    }

    /// Bytes used by a family's repository on disk.
    pub fn family_size(&self, family: &str) -> u64 {
        fn walk(p: &Path) -> u64 {
            let Ok(rd) = fs::read_dir(p) else { return 0 };
            rd.filter_map(Result::ok)
                .map(|e| match e.metadata() {
                    Ok(m) if m.is_dir() => walk(&e.path()),
                    Ok(m) => m.len(),
                    Err(_) => 0,
                })
                .sum()
        }
        walk(&self.repo_dir(family))
    }
}

/// Error helper for callers that look up snapshots by short id.
pub fn resolve_id(snapshots: &[SnapshotInfo], prefix: &str) -> Result<String> {
    let hits: Vec<&SnapshotInfo> = snapshots.iter().filter(|s| s.id.starts_with(prefix)).collect();
    match hits.as_slice() {
        [one] => Ok(one.id.clone()),
        [] => Err(anyhow!("no snapshot matches {prefix}")),
        _ => Err(anyhow!("{prefix} is ambiguous")),
    }
}
