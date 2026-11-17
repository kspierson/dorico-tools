//! User settings (JSON). The app keeps them in its config dir.

use crate::policy::PlaybackPolicy;
use anyhow::Result;
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct Settings {
    /// Where the hidden history repositories live. Keep it out of cloud-synced folders.
    pub store_dir: PathBuf,
    /// Folders watched for saved .dorico files (recursively).
    pub watch_dirs: Vec<PathBuf>,
    /// Where restored versions are written. None = next to the original file.
    pub restore_dir: Option<PathBuf>,
    /// Path fragments to ignore while watching (case-insensitive).
    pub ignore: Vec<String>,
    pub playback: PlaybackPolicy,
    /// Snapshot automatically on every save.
    pub auto_snapshot: bool,
    /// Wait this long after the last write before reading a saved file.
    pub settle_ms: u64,
}

impl Default for Settings {
    fn default() -> Self {
        Settings {
            store_dir: default_data_dir().join("store"),
            watch_dirs: default_documents().map(|d| vec![d.join("Dorico Projects")]).unwrap_or_default(),
            restore_dir: None,
            ignore: vec!["Backup Projects".into(), "AutoSave".into(), "Auto-Save".into(), "$RECYCLE.BIN".into()],
            playback: PlaybackPolicy::default(),
            auto_snapshot: true,
            settle_ms: 2000,
        }
    }
}

impl Settings {
    pub fn load(path: &Path) -> Settings {
        std::fs::read(path).ok().and_then(|b| serde_json::from_slice(&b).ok()).unwrap_or_default()
    }

    pub fn save(&self, path: &Path) -> Result<()> {
        if let Some(dir) = path.parent() {
            std::fs::create_dir_all(dir)?;
        }
        std::fs::write(path, serde_json::to_vec_pretty(self)?)?;
        Ok(())
    }

    pub fn is_ignored(&self, path: &Path) -> bool {
        is_ignored(&self.ignore, &self.store_dir, path)
    }
}

pub(crate) fn is_ignored(ignore: &[String], store_dir: &Path, path: &Path) -> bool {
    let p = path.to_string_lossy().to_lowercase();
    path.starts_with(store_dir) || ignore.iter().any(|frag| p.contains(&frag.to_lowercase()))
}

/// $DORIGIT_DATA_DIR if set (tests, portable installs); otherwise
/// %LOCALAPPDATA%\dorigit on Windows, ~/Library/Application Support/dorigit on
/// macOS, $XDG_DATA_HOME/dorigit (or ~/.local/share/dorigit) elsewhere.
pub fn default_data_dir() -> PathBuf {
    let env = |k: &str| std::env::var_os(k).map(PathBuf::from);
    if let Some(d) = env("DORIGIT_DATA_DIR") {
        return d;
    }
    if cfg!(windows) {
        if let Some(d) = env("LOCALAPPDATA") {
            return d.join("dorigit");
        }
    } else if cfg!(target_os = "macos") {
        if let Some(h) = env("HOME") {
            return h.join("Library/Application Support/dorigit");
        }
    } else if let Some(d) = env("XDG_DATA_HOME") {
        return d.join("dorigit");
    } else if let Some(h) = env("HOME") {
        return h.join(".local/share/dorigit");
    }
    PathBuf::from("dorigit-data")
}

fn default_documents() -> Option<PathBuf> {
    let home = std::env::var_os(if cfg!(windows) { "USERPROFILE" } else { "HOME" })?;
    Some(PathBuf::from(home).join("Documents"))
}
