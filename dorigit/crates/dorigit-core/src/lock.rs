//! Cross-process lock per project family.
//!
//! The dorigit app's watcher, the `dorigit` CLI and other tools that use this library (Score
//! Workbench, Playback; PLANNED_WORK.md §2.11) may write to the same store at once. Every write
//! to a family (snapshot, milestone, restore bookkeeping) holds `<family>.git/dorigit.lock`, an
//! OS file lock (`LockFileEx` on Windows, `flock` on macOS/Linux) that the OS releases if the
//! holder crashes. Readers don't lock: `family.json` is replaced atomically and git objects are
//! immutable.

use anyhow::{Context, Result, bail};
use std::fs::{File, OpenOptions, TryLockError};
use std::io::{Read, Seek, SeekFrom, Write};
use std::path::{Path, PathBuf};
use std::time::{Duration, Instant};

pub const LOCK_FILE: &str = "dorigit.lock";

/// Held for the duration of one write; released on drop.
#[derive(Debug)]
pub struct FamilyLock {
    file: File,
    path: PathBuf,
}

impl FamilyLock {
    pub fn path(&self) -> &Path {
        &self.path
    }
}

impl Drop for FamilyLock {
    fn drop(&mut self) {
        let _ = self.file.unlock();
    }
}

/// Lock the family whose repository lives in `repo_dir` (created if missing), waiting up to
/// `timeout` for another process to finish.
pub fn lock_family(repo_dir: &Path, timeout: Duration) -> Result<FamilyLock> {
    std::fs::create_dir_all(repo_dir).with_context(|| format!("creating {}", repo_dir.display()))?;
    let path = repo_dir.join(LOCK_FILE);
    let mut file = OpenOptions::new()
        .read(true)
        .write(true)
        .create(true)
        .truncate(false)
        .open(&path)
        .with_context(|| format!("opening {}", path.display()))?;
    let start = Instant::now();
    loop {
        match file.try_lock() {
            Ok(()) => break,
            Err(TryLockError::WouldBlock) if start.elapsed() < timeout => {
                std::thread::sleep(Duration::from_millis(50));
            }
            Err(TryLockError::WouldBlock) => {
                let mut holder = String::new();
                let _ = file.read_to_string(&mut holder);
                let holder = holder.trim();
                bail!(
                    "the history store is busy ({}); try again in a moment",
                    if holder.is_empty() { "another program is writing to it" } else { holder }
                );
            }
            Err(TryLockError::Error(e)) => return Err(e).with_context(|| format!("locking {}", path.display())),
        }
    }
    // say who holds it, for the "busy" message another process may show
    let program = std::env::current_exe()
        .ok()
        .and_then(|p| p.file_stem().map(|s| s.to_string_lossy().into_owned()))
        .unwrap_or_else(|| "?".into());
    let _ = file.set_len(0).and_then(|_| file.seek(SeekFrom::Start(0)));
    let _ = write!(file, "held by {program} (process {})", std::process::id());
    let _ = file.flush();
    Ok(FamilyLock { file, path })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn second_holder_waits_then_fails() {
        let dir = tempfile::tempdir().unwrap();
        let first = lock_family(dir.path(), Duration::from_secs(1)).unwrap();
        let err = lock_family(dir.path(), Duration::from_millis(150)).unwrap_err().to_string();
        assert!(err.contains("busy") && err.contains("held by"), "{err}");
        drop(first);
        lock_family(dir.path(), Duration::from_millis(150)).unwrap();
    }
}
