//! dorigit core: git-backed history for Dorico projects.
//!
//! - [`store::Store`]: snapshot / list / diff / restore / milestones
//! - [`variants`]: named alternatives of a cue, the variant board
//! - [`policy`]: what happens to playback state (enginedata)
//! - [`watch`]: snapshot-on-save folder watching
//! - [`settings`]: user settings
//! - [`listing`]: the musical listing (shared listing + readable names for the rest)
//! - [`notation`]: a bar range as MEI for the app's notation view (Verovio)
//! - [`tidy`]: dorigit's diff (renames and "re-saved in a newer Dorico" noise removed)
//! - [`merge`]: merge preview (auto / review / conflict per region, MERGE.md §4)
//! - [`lock`]: cross-process lock per project family (app, CLI and other tools share a store)
//!
//! Design: `docs/DESIGN.md`.

pub mod listing;
pub mod lock;
pub mod notation;
pub mod manifest;
pub mod merge;
pub mod policy;
pub mod settings;
pub mod store;
pub mod tidy;
pub mod variants;
pub mod watch;

pub use manifest::SnapshotKind;
pub use policy::{PlaybackMode, PlaybackPolicy};
pub use settings::Settings;
pub use store::{SnapshotInfo, SnapshotOutcome, Store};
