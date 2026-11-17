//! `dorigit.json`: stored in every snapshot's tree. Describes the original
//! `.dorico` so it can be rebuilt exactly, plus metadata for the UI.

use crate::policy::PlaybackReason;
use dorico_format::container::ZipTime;
use dorico_format::playback::PlaybackSetup;
use serde::{Deserialize, Serialize};

pub const MANIFEST_PATH: &str = "dorigit.json";
pub const SCORE_PATH: &str = "score.xml";
pub const LIBRARY_PATH: &str = "scorelibrary.xml";
pub const PLAYBACK_PATH: &str = "playback/enginedata";
pub const THUMB_PATH: &str = "thumb.png";
pub const FILES_DIR: &str = "files";
pub const FORMAT: u32 = 1;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SnapshotKind {
    /// Taken automatically when Dorico saved the file.
    Auto,
    /// Taken on request (e.g. "Save milestone now").
    Manual,
    /// Imported from an existing file / backup.
    Import,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum PartForm {
    /// Original was binary DTN; stored decoded as XML (with marker PI), re-encoded on restore.
    Dtn,
    /// Original was XML; stored verbatim.
    Xml,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Entry {
    /// Name inside the .dorico zip.
    pub name: String,
    pub time: ZipTime,
    pub deflated: bool,
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    pub is_dir: bool,
    /// Path in the snapshot tree, or None if this entry was not stored
    /// (playback / previews under the playback policy).
    pub stored_at: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub form: Option<PartForm>,
    /// git blob id of the entry's original bytes (identifies the content even when not stored).
    pub blob: String,
    pub size: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Source {
    pub path: String,
    pub file_name: String,
    pub size: u64,
    /// File modification time (unix seconds).
    pub modified: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct DoricoInfo {
    pub title: String,
    pub created_date: String,
    pub created_version: String,
    pub last_saved_version: String,
    pub last_saved_date: Option<i64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Playback {
    pub present: bool,
    pub stored: bool,
    pub reason: PlaybackReason,
    /// git blob id of this snapshot's enginedata (whether stored or not)
    pub blob: Option<String>,
    pub size: u64,
    /// Plugins loaded (None if the mixer XML couldn't be read).
    #[serde(default)]
    pub setup: Option<PlaybackSetup>,
    /// Hash of `setup` (for quick comparison).
    #[serde(default)]
    pub setup_id: Option<String>,
    /// When not stored: the snapshot whose stored playback (same setup) restores use.
    #[serde(default)]
    pub borrow_from: Option<String>,
    /// e.g. ["+1 Kontakt"] relative to the parent snapshot.
    #[serde(default)]
    pub setup_changes: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct Summary {
    /// e.g. "12 changes in 3 parts; 2 settings"
    pub text: String,
    pub music_changes: usize,
    pub setting_changes: usize,
    pub parent: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Manifest {
    pub format: u32,
    pub kind: SnapshotKind,
    pub source: Source,
    pub dorico: DoricoInfo,
    pub entries: Vec<Entry>,
    pub playback: Playback,
    /// Hash over all entry blobs: equal content_id = identical file content.
    pub content_id: String,
    pub summary: Summary,
    #[serde(default)]
    pub has_thumb: bool,
}
