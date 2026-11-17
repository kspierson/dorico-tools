//! stagecraft: stage placement and audio-chain profiles for virtual instruments
//! (PLANNED_WORK.md §7, Project E). Resume notes: `stagecraft/docs/STATUS.md`.
//!
//! - [`inventory`]: what a Dorico project's mixer does to place each instrument today (E1)
//! - [`vss2`]: Virtual Sound Stage 2 states and `.vss2preset` files
//! - [`altiverb`]: Altiverb 7 states
//! - [`capture`]: VSS2 settings captured as impulse responses (E2), through vi-render
//! - [`library`]: every VSS2 setting in use plus the preset library, captured (E3)
//! - [`motion`]: how VSS2's reflections move over time
//! - [`stage`]: stagecraft's own placement engine (E5): stage files, taps, IRs, VSS2-compatible stages
//! - [`serve`]: the stage editor (local web page over JSON calls into [`stage`])
//! - [`audio`]: WAV, FFT, sweeps, deconvolution, measurements

pub mod altiverb;
pub mod audio;
pub mod capture;
pub mod inventory;
pub mod library;
pub mod motion;
pub mod serve;
pub mod stage;
pub mod vss2;
