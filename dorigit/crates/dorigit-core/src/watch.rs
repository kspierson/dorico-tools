//! Watch folders for saved .dorico files.
//!
//! Dorico writes the whole zip on each save. We wait until a file has been
//! quiet for `settle` and is a complete zip before reporting it, and skip
//! files whose size+mtime haven't changed since we last reported them.

use crate::settings::is_ignored;
use anyhow::Result;
use dorico_format::container::is_complete;
use notify::{RecursiveMode, Watcher};
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::mpsc;
use std::time::{Duration, Instant, SystemTime};

const MAX_ATTEMPTS: u32 = 30;

pub struct FolderWatcher {
    _watcher: notify::RecommendedWatcher,
    pub watching: Vec<PathBuf>,
    pub errors: Vec<String>,
}

fn is_dorico(p: &Path) -> bool {
    p.extension().is_some_and(|e| e.eq_ignore_ascii_case("dorico"))
}

/// Start watching. `on_ready` runs on a background thread for each saved file.
pub fn watch(
    dirs: &[PathBuf],
    ignore: Vec<String>,
    store_dir: PathBuf,
    settle: Duration,
    on_ready: impl Fn(PathBuf) + Send + 'static,
) -> Result<FolderWatcher> {
    let (tx, rx) = mpsc::channel::<PathBuf>();
    let mut watcher = notify::recommended_watcher(move |res: notify::Result<notify::Event>| {
        if let Ok(ev) = res {
            if matches!(ev.kind, notify::EventKind::Access(_)) {
                return;
            }
            for p in ev.paths {
                if is_dorico(&p) {
                    let _ = tx.send(p);
                }
            }
        }
    })?;
    let mut watching = Vec::new();
    let mut errors = Vec::new();
    for d in dirs {
        match watcher.watch(d, RecursiveMode::Recursive) {
            Ok(()) => watching.push(d.clone()),
            Err(e) => errors.push(format!("{}: {e}", d.display())),
        }
    }

    std::thread::Builder::new().name("dorigit-watch".into()).spawn(move || {
        let mut pending: HashMap<PathBuf, (Instant, u32)> = HashMap::new();
        let mut done: HashMap<PathBuf, (u64, SystemTime)> = HashMap::new();
        loop {
            match rx.recv_timeout(Duration::from_millis(250)) {
                Ok(p) => {
                    if !is_ignored(&ignore, &store_dir, &p) {
                        pending.insert(p, (Instant::now(), 0));
                    }
                }
                Err(mpsc::RecvTimeoutError::Timeout) => {}
                Err(mpsc::RecvTimeoutError::Disconnected) => return,
            }
            let now = Instant::now();
            let due: Vec<PathBuf> =
                pending.iter().filter(|(_, (t, _))| now.duration_since(*t) >= settle).map(|(p, _)| p.clone()).collect();
            for p in due {
                let (_, attempts) = pending.remove(&p).unwrap();
                let Ok(meta) = std::fs::metadata(&p) else { continue }; // deleted / renamed away
                let stamp = (meta.len(), meta.modified().unwrap_or(SystemTime::UNIX_EPOCH));
                if done.get(&p) == Some(&stamp) {
                    continue;
                }
                if !is_complete(&p) {
                    if attempts < MAX_ATTEMPTS {
                        pending.insert(p, (Instant::now(), attempts + 1));
                    }
                    continue;
                }
                done.insert(p.clone(), stamp);
                on_ready(p);
            }
        }
    })?;
    Ok(FolderWatcher { _watcher: watcher, watching, errors })
}
