//! Read and write Dorico project files (shared engine crate, Project S; moved from dorigit).
//!
//! - [`dtn`]: the binary score format (`score.dtn`) <-> tree
//! - [`xml`]: tree <-> Dorico-style XML text (lossless)
//! - [`container`]: the `.dorico` zip
//! - [`model`]: a musician-readable model (flows, players, events with bar/beat)
//! - [`diff`]: listings (for `git diff`) and structured musical diffs
//! - [`playback`]: which plugins the playback state (enginedata) loads
//! - [`mixer`]: mixer channels (inserts, sends, gain) and saved plug-in states by owner
//! - [`ratio`]: exact positions/durations (`"81/4"`) and MIDI-style ticks
//! - [`tree`]: build and edit trees within DTN's rules; event property tables
//! - [`ids`]: allocate IDs from `idGenerators` and check the counters
//! - [`vocab`]: Dorico's vocabulary: raw encodings -> values and readable names (one place)
//! - [`dynamics`]: dynamics -> machine levels and readable names
//! - [`timecode`]: frame rates (23.976–60, drop frame) and SMPTE timecode
//!
//! Format notes: `dorigit/docs/RESEARCH.md` (to be merged into `engine/docs/FORMAT.md`, S10).

pub mod bars;
pub mod container;
pub mod diff;
pub mod dtn;
pub mod dynamics;
pub mod ids;
pub mod mixer;
pub mod model;
pub mod playback;
pub mod ratio;
pub mod timecode;
pub mod tree;
pub mod vocab;
pub mod xml;

pub use container::Project;
pub use dtn::{Document, Node};
pub use model::{Score, build_score};
