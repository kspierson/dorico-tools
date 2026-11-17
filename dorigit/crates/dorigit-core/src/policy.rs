//! What to do with playback state (`enginedata`) when snapshotting.
//!
//! `enginedata` holds the mixer plus every VST plugin's saved state (Kontakt,
//! VSS, ...). It is large (2-25 MB) and opaque, and plugins re-serialise it on
//! every save, so git cannot delta-compress it: keeping it on every save would
//! cost ~20 MB per save for an orchestral template. The music (score.xml)
//! costs ~15-45 KB per save. So by default playback is kept only at points
//! that matter:
//!
//! - milestones
//! - the first snapshot in a history (so there is always something to borrow)
//! - whenever the playback *setup* changes (plugins added/removed/swapped,
//!   e.g. a new player's instrument, a SILENT or VSS variant). The setup is
//!   read from the mixer XML inside enginedata (dorico_format::playback).
//! - when enginedata is small (e.g. HALion/NotePerformer-only projects)
//!
//! Snapshots that don't keep it record `borrow_from`: the nearest earlier
//! snapshot with the same setup. Restores use that copy, so a restored file
//! always has the right plugins loaded; only plugin-internal settings
//! (Kontakt articulations, mixer levels) may be from that earlier save.

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
#[serde(rename_all = "snake_case")]
pub enum PlaybackMode {
    /// Keep at milestones, first snapshot, setup changes, and when small.
    #[default]
    Milestones,
    /// Keep on every snapshot (simple, large).
    Always,
    /// Never keep (restores get playback from Dorico's defaults / nearest file).
    Never,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct PlaybackPolicy {
    pub mode: PlaybackMode,
    /// In `milestones` mode, also keep playback when enginedata is at most this
    /// many bytes (e.g. NotePerformer-only projects are tiny).
    pub keep_if_under_bytes: u64,
}

impl Default for PlaybackPolicy {
    fn default() -> Self {
        PlaybackPolicy { mode: PlaybackMode::Milestones, keep_if_under_bytes: 2 * 1024 * 1024 }
    }
}

/// Why playback was (or wasn't) stored in a snapshot. Shown in the UI.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum PlaybackReason {
    Milestone,
    /// No earlier snapshot has playback to borrow.
    FirstInHistory,
    /// Plugins added / removed / swapped since the parent snapshot.
    SetupChanged,
    Small,
    PolicyAlways,
    /// Identical bytes already stored (free).
    Unchanged,
    /// Not kept; restores borrow from `borrow_from`.
    Skipped,
    NotPresent,
}

impl PlaybackPolicy {
    /// `can_borrow`: an earlier snapshot holds playback with the same setup.
    pub fn decide(
        &self,
        milestone: bool,
        can_borrow: bool,
        setup_changed: bool,
        size: Option<u64>,
    ) -> (bool, PlaybackReason) {
        let Some(size) = size else { return (false, PlaybackReason::NotPresent) };
        match self.mode {
            PlaybackMode::Always => (true, PlaybackReason::PolicyAlways),
            PlaybackMode::Never => (false, PlaybackReason::Skipped),
            PlaybackMode::Milestones if milestone => (true, PlaybackReason::Milestone),
            PlaybackMode::Milestones if setup_changed => (true, PlaybackReason::SetupChanged),
            PlaybackMode::Milestones if !can_borrow => (true, PlaybackReason::FirstInHistory),
            PlaybackMode::Milestones if size <= self.keep_if_under_bytes => (true, PlaybackReason::Small),
            PlaybackMode::Milestones => (false, PlaybackReason::Skipped),
        }
    }
}
