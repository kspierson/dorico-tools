//! E2: capture a Virtual Sound Stage 2 setting as impulse responses.
//!
//! A sine sweep goes into VSS2's left input only, then its right input only (through
//! `vi-render render --input`, engine/crates/vi-render), and each output is deconvolved:
//! four IRs, L→L, L→R, R→L, R→R ("true stereo"). Optional checks:
//! - **repeat**: capture the left input again; residual vs the first capture;
//! - **level**: sweep 12 dB quieter; residual (a linear plug-in gives the same IR);
//! - **null**: a stereo test signal (tone with vibrato, noise bursts, clicks) through VSS2
//!   vs through the four IRs; residual per output; plus **self-null**: VSS2 loaded a second
//!   time vs the first, the best any capture can do.
//!
//! Residuals are in dB relative to the signal: −60 dB or lower means "the same".
//!
//! Found 2026-11-01 (Clarinet 2): VSS2's **direct sound is deterministic** (repeat −75 dB) but
//! its **reflections are re-randomised every time it loads** (repeat of the early and late
//! parts ≈ −3 dB, i.e. unrelated; same statistics). So the IR null equals VSS2's self-null:
//! a capture is as close to VSS2 as VSS2 is to itself.
//!
//! Found 2026-11-01 (session 3): VSS2 **simulates its main microphones geometrically**. Each
//! output is its own capsule plus the shared centre capsule of the room's Decca tree, each a
//! delayed (distance / 343 m/s, measured within 0.01 ms), scaled, filtered copy of the source;
//! the earliest capsule lands exactly on VSS2's 4 ms latency. Its filters are symmetric around
//! that point, so IRs are saved whole (latency included, `ir_offset_samples`). [`Seat`] holds
//! the numbers per microphone.

use crate::audio::{self, Chans};
use crate::vss2;
use anyhow::{Context, Result, bail};
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};
use std::process::Command;

pub const SR: f64 = 48000.0;
const F1: f64 = 20.0;
/// Top of the capture sweep: captures say nothing above this.
pub const F2: f64 = 23000.0;
const SWEEP_SECS: f64 = 6.0;
const PRE_SECS: f64 = 0.25;
/// IR length kept (VSS2's responses die away within ~0.2 s).
const IR_SECS: f64 = 0.6;

/// A VSS2 setting to capture.
#[derive(Debug, Clone)]
pub struct Source {
    pub name: String,
    pub from: String,
    pub chunk: Vec<u8>,
}

/// One named VSS2 insert of a project.
#[derive(Debug, Clone)]
pub struct Instance {
    pub pin: String,
    /// Mixer channel name.
    pub channel: String,
    /// "rack 22 SWAM Oboe 64bit" (empty when the channel isn't an instrument output).
    pub rack: String,
    /// Preset file name the instance was loaded from ("SWAM Oboe 1").
    pub preset: String,
    pub chunk: Vec<u8>,
}

/// Every named VSS2 insert of a project, in mixer order (leftover states in empty slots are
/// skipped).
pub fn instances(path: &Path) -> Result<Vec<Instance>> {
    let p = dorico_format::Project::read(path)?;
    let e = p.get(dorico_format::container::ENGINE_DATA).context("no playback data")?;
    let m = dorico_format::mixer::read_mixer(&e.data).context("unrecognised enginedata")?;
    let mut out = vec![];
    for s in dorico_format::mixer::plugin_states(&e.data) {
        let Some(v) = s.vst2.as_ref().filter(|v| v.fx_id == "Para") else { continue };
        let Some((ch, ins)) = m.insert(s.owner) else { continue };
        if ins.name.is_none() {
            continue; // leftover state in an empty slot
        }
        let vs = vss2::Vss2::from_props(vss2::parse_state(&v.chunk)?);
        out.push(Instance {
            pin: vs.name.clone(),
            channel: ch.name.clone(),
            rack: ch.instrument_id.and_then(|i| m.rack_slot(i)).map_or(String::new(), |r| format!("rack {} {}", r.slot, r.name)),
            preset: vs.preset_name().to_string(),
            chunk: v.chunk.clone(),
        });
    }
    Ok(out)
}

/// Named VSS2 inserts of a project (all, or those whose pin name matches), identical states once.
pub fn from_project(path: &Path, pin: Option<&str>) -> Result<Vec<Source>> {
    let file = path.file_name().unwrap_or_default().to_string_lossy().into_owned();
    let mut out: Vec<Source> = Vec::new();
    for i in instances(path)? {
        if pin.is_some_and(|p| p != i.pin) || out.iter().any(|o| o.chunk == i.chunk) {
            continue;
        }
        out.push(Source { name: i.pin.clone(), from: format!("{file} / {} / {} ({})", i.rack, i.channel, i.preset), chunk: i.chunk });
    }
    if out.is_empty() {
        bail!("no VSS2 instance{} in {}", pin.map_or(String::new(), |p| format!(" named {p:?}")), path.display());
    }
    Ok(out)
}

/// A `.vss2preset` file as a loadable state (see [`vss2::state_from_preset`]).
pub fn from_preset(path: &Path, room: &[u8]) -> Result<Source> {
    let pr = vss2::read_preset(path)?;
    let chunk = vss2::state_from_preset(path, &win(path)?, 1, room)?;
    Ok(Source {
        name: path.file_stem().unwrap_or_default().to_string_lossy().into_owned(),
        from: format!("preset {} ({}, {})", path.display(), pr.library, pr.mic_position),
        chunk,
    })
}

/// VSS2's room block (room id, microphone setup, level) as saved in a project.
pub fn project_room(path: &Path) -> Result<Vec<u8>> {
    let src = from_project(path, None)?;
    src.iter()
        .find_map(|s| vss2::room_bytes(&s.chunk).map(<[u8]>::to_vec))
        .with_context(|| format!("no VSS2 room settings in {}", path.display()))
}

/// vi-render + the VSS2 DLL.
pub struct Rig {
    exe: PathBuf,
    plugin: String,
}

fn win(p: &Path) -> Result<String> {
    let o = Command::new("wslpath").arg("-w").arg(p).output().context("wslpath")?;
    Ok(String::from_utf8(o.stdout)?.trim().to_string())
}

impl Rig {
    pub fn find(repo: &Path) -> Result<Rig> {
        let exe = repo.join("target/x86_64-pc-windows-gnu/release/vi-render.exe");
        if !exe.exists() {
            bail!("{} missing: cargo zigbuild --release --target x86_64-pc-windows-gnu -p vi-render", exe.display());
        }
        let dll = ["/mnt/c/Program Files/Steinberg/VstPlugins", "/mnt/c/Program Files/VstPlugins", "/mnt/c/Program Files/Common Files/VST2"]
            .iter()
            .map(|d| Path::new(d).join("VirtualSoundStage2_x64.dll"))
            .find(|p| p.exists())
            .context("VirtualSoundStage2_x64.dll not found")?;
        Ok(Rig { exe, plugin: win(&dll)? })
    }

    /// Run `input` (stereo) through VSS2 with `state`; returns the output and the latency.
    pub fn run(&self, state: &Path, input: &Path, out: &Path) -> Result<(Chans, usize)> {
        let o = Command::new(&self.exe)
            .args(["render", "--plugin", &self.plugin, "--bank", "--warmup", "1000", "--tail", "1.0", "--sample-rate", "48000"])
            .args(["--state", &win(state)?, "--input", &win(input)?, "--out", &win(out)?])
            .output()
            .context("running vi-render")?;
        let err = String::from_utf8_lossy(&o.stderr);
        if !o.status.success() {
            bail!("vi-render failed: {err}");
        }
        let latency = err.split("plug-in latency ").nth(1).and_then(|s| s.split_whitespace().next()).and_then(|s| s.parse().ok()).unwrap_or(0);
        let (_, y) = audio::read_wav(out)?;
        Ok((y, latency))
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PathStats {
    pub peak_db: f64,
    pub gain_db: f64,
    /// ms after the plug-in's reported latency.
    pub arrival_ms: f64,
    pub direct_pct: f64,
    pub early_pct: f64,
    pub late_pct: f64,
    pub length_ms: f64,
    pub octaves: Vec<(f64, f64)>,
}

/// One microphone's direct sound at one output.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct Tap {
    /// 'L' or 'R'.
    pub output: char,
    /// Which capsule of the room's main microphones: "L", "C", "R" (empty when the geometry
    /// is unknown, e.g. a section source or a room without a saved mic setup).
    pub mic: String,
    /// From the geometry: ms after the earliest microphone (speed of sound 343 m/s).
    pub predicted_ms: Option<f64>,
    /// Measured: ms after the plug-in latency (VSS2 puts the earliest microphone there).
    pub ms: f64,
    /// Peak level, dB (0 = unity).
    pub db: f64,
    /// Gain fitted in 300 Hz–3 kHz (where VSS2's Air EQ is ≈ flat): the level of this
    /// microphone's copy itself, independent of the EQ, dB.
    #[serde(default)]
    pub gain_db: f64,
}

/// What VSS2 does to a mono source (the same signal into both inputs), as numbers a light
/// replacement chain can use. VSS2 simulates its main microphones geometrically (found
/// 2026-11-01): each output is its own capsule plus the shared centre capsule (Decca tree),
/// each a delayed, scaled, filtered copy of the source; then reflections.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct Seat {
    /// Direct arrivals, by output then time.
    pub taps: Vec<Tap>,
    /// Direct sound level per output (all its taps), 1 kHz octave, dB (0 = unity). Measured in
    /// one band so that treble boosts (air settings) don't count as loudness.
    pub direct_db: (f64, f64),
    /// Tone of the strongest tap (both outputs), dB per octave relative to 1 kHz, 250 Hz–16 kHz
    /// (1.25 ms windows: coarse below 1 kHz).
    pub direct_tone_db: Vec<(f64, f64)>,
    /// The same in third octaves, 63 Hz–16 kHz (below ≈ 250 Hz only rough).
    #[serde(default)]
    pub direct_tone_third_db: Vec<(f64, f64)>,
    /// Reflection energy relative to the direct sound (both outputs, 1 kHz octave): from the end
    /// of the direct sound to 80 ms, and after 80 ms (dB).
    pub early_db: f64,
    pub late_db: f64,
    /// Reflection tone (both outputs), dB per octave relative to 1 kHz.
    pub reflection_tone_db: Vec<(f64, f64)>,
    /// Strongest reflections up to 80 ms: (ms after the plug-in latency, dB relative to the
    /// strongest tap, output), by time.
    pub reflections: Vec<(f64, f64, char)>,
}

/// Where the source and the microphones are, for predicting the taps.
pub struct Geometry {
    pub source: [f32; 3],
    pub mic: vss2::Mic,
}

impl Geometry {
    /// From a state: point sources in a room with a decoded mic setup only.
    pub fn of(state: &[u8]) -> Option<Geometry> {
        let v = vss2::Vss2::from_props(vss2::parse_state(state).ok()?);
        if v.emitters > 1 {
            return None;
        }
        let mic = vss2::room(state)?.effective_mic()?;
        Some(Geometry { source: [v.x, v.y, v.z], mic })
    }

    /// (capsule label, output it feeds, ms after the earliest capsule).
    pub fn arrivals(&self) -> Vec<(String, u32, f64)> {
        let d: Vec<f64> = self
            .mic
            .capsules
            .iter()
            .map(|c| (0..3).map(|k| (self.source[k] - self.mic.position[k] - c.position[k]) as f64).map(|x| x * x).sum::<f64>().sqrt())
            .collect();
        let min = d.iter().cloned().fold(f64::MAX, f64::min);
        self.mic
            .capsules
            .iter()
            .zip(&d)
            .map(|(c, d)| {
                let label = match c.output {
                    1 => "L",
                    2 => "R",
                    _ => "C",
                };
                (label.to_string(), c.output, (d - min) / 343.0 * 1000.0)
            })
            .collect()
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Capture {
    pub name: String,
    pub from: String,
    pub latency_samples: usize,
    /// Where time zero (the plug-in's latency point) is in the saved IRs, samples. 0 = IRs saved
    /// before 2026-11-01 (session 3), which were trimmed there.
    #[serde(default)]
    pub ir_offset_samples: usize,
    /// Energy in the 4 ms before the latency point, relative to the whole IR (worst path, dB):
    /// what a trimmed IR would lose.
    #[serde(default)]
    pub pre_latency_db: f64,
    #[serde(default)]
    pub seat: Seat,
    /// LL, LR, RL, RR
    pub paths: Vec<PathStats>,
    /// Left input: level of the right output relative to the left (dB) and its delay (ms).
    pub l_cross_db: f64,
    pub l_cross_ms: f64,
    pub r_cross_db: f64,
    pub r_cross_ms: f64,
    /// A mono source (same signal into both inputs), direct sound (first 10 ms): left minus
    /// right level (dB), per band (125 Hz … 8 kHz octaves), and how much later the right
    /// output arrives (ms; positive = image to the left). VSS2 places mainly by this delay.
    pub mono_level_db: f64,
    pub mono_bands_db: Vec<(f64, f64)>,
    pub mono_right_later_ms: f64,
    pub repeat_db: Option<f64>,
    /// Repeat residual of L→L by part of the response: direct (to 5 ms), early (5–80 ms), late.
    pub repeat_parts_db: Option<(f64, f64, f64)>,
    /// Repeat residual of L→L per octave band (centre Hz, dB).
    pub repeat_octaves_db: Option<Vec<(f64, f64)>>,
    pub level_db: Option<f64>,
    pub null_db: Option<(f64, f64)>,
    /// The same test signal through VSS2 loaded a second time vs the first (out L, out R):
    /// how far VSS2 is from itself. The IR null can't be better than this.
    pub self_null_db: Option<(f64, f64)>,
    /// Null test with the left test signal only / right only: (out L, out R) each.
    pub null_l_only_db: Option<(f64, f64)>,
    pub null_r_only_db: Option<(f64, f64)>,
    /// Null residual per octave band, right test signal only, out R (centre Hz, dB).
    pub null_r_only_octaves_db: Option<Vec<(f64, f64)>>,
}

fn stats(h: &[f64]) -> PathStats {
    let ms = |n: usize| n as f64 / SR * 1000.0;
    let a = audio::arrival(h, 0.1);
    let tot = audio::energy(h).max(1e-30);
    let seg = |from: f64, to: f64| {
        let (s, e) = ((a as f64 + from * SR / 1000.0) as usize, ((a as f64 + to * SR / 1000.0) as usize).min(h.len()));
        if s >= e { 0.0 } else { audio::energy(&h[s..e]) / tot * 100.0 }
    };
    let pk = h.iter().fold(0.0f64, |m, v| m.max(v.abs()));
    let last = h.iter().rposition(|v| v.abs() >= pk * 1e-3).unwrap_or(0);
    PathStats {
        peak_db: 20.0 * pk.max(1e-12).log10(),
        gain_db: audio::db(tot),
        arrival_ms: ms(a),
        direct_pct: seg(-1.0, 5.0),
        early_pct: seg(5.0, 80.0),
        late_pct: seg(80.0, 1e6),
        length_ms: ms(last),
        octaves: audio::octave_bands(h, SR),
    }
}

/// Peak position with parabolic interpolation (samples).
fn peak_pos(h: &[f64], i: usize) -> f64 {
    if i == 0 || i + 1 >= h.len() {
        return i as f64;
    }
    let (a, b, c) = (h[i - 1].abs(), h[i].abs(), h[i + 1].abs());
    let den = a - 2.0 * b + c;
    if den.abs() < 1e-30 { i as f64 } else { i as f64 + 0.5 * (a - c) / den }
}

/// VSS2's direct-sound filters are symmetric (linear phase) and centred on its latency point:
/// a filtered pulse spreads this far either side (192 samples = VSS2's reported latency).
const SPREAD_MS: f64 = 4.0;

/// Least-squares gains of each output's taps (known delays) over 300 Hz–3 kHz:
/// H(f) ≈ Σ gᵢ e^(−j2πf tᵢ), solved on the response from 4 ms before the first tap to 4 ms
/// after the last.
pub fn fit_gains(hl: &[f64], hr: &[f64], zero: usize, taps: &mut [Tap]) {
    let at = |ms: f64| (zero as f64 + ms * SR / 1000.0).round().max(0.0) as usize;
    for (h, side) in [(hl, 'L'), (hr, 'R')] {
        let idx: Vec<usize> = (0..taps.len()).filter(|&i| taps[i].output == side).collect();
        if idx.is_empty() {
            continue;
        }
        let first = idx.iter().map(|&i| taps[i].ms).fold(f64::MAX, f64::min);
        let last = idx.iter().map(|&i| taps[i].ms).fold(f64::MIN, f64::max);
        let (a, b) = (at(first - SPREAD_MS), at(last + SPREAD_MS).min(h.len()));
        let nfft = 4096;
        let spec = audio::spectrum(&h[a..b], nfft);
        let t0 = (a as f64 - zero as f64) / SR;
        let n = idx.len();
        let (mut m, mut v) = (vec![vec![0.0; n]; n], vec![0.0; n]);
        let (lo, hi) = ((300.0 * nfft as f64 / SR) as usize, (3000.0 * nfft as f64 / SR) as usize);
        for (bin, y) in spec.iter().enumerate().take(hi + 1).skip(lo) {
            let w = 2.0 * std::f64::consts::PI * bin as f64 * SR / nfft as f64;
            let e: Vec<(f64, f64)> = idx.iter().map(|&i| { let ph = -w * (on_sample(taps[i].ms) / 1000.0 - t0); (ph.cos(), ph.sin()) }).collect();
            for p in 0..n {
                v[p] += e[p].0 * y.re + e[p].1 * y.im;
                for q in 0..n {
                    m[p][q] += e[p].0 * e[q].0 + e[p].1 * e[q].1;
                }
            }
        }
        if let Some(g) = solve(m, v) {
            for (k, &i) in idx.iter().enumerate() {
                taps[i].gain_db = 20.0 * g[k].abs().max(1e-12).log10();
            }
        }
    }
}

/// A time in ms rounded to the nearest sample.
fn on_sample(ms: f64) -> f64 {
    (ms * SR / 1000.0).round() / SR * 1000.0
}

/// Gaussian elimination with partial pivoting (small systems).
fn solve(mut m: Vec<Vec<f64>>, mut v: Vec<f64>) -> Option<Vec<f64>> {
    let n = v.len();
    for i in 0..n {
        let p = (i..n).max_by(|a, b| m[*a][i].abs().total_cmp(&m[*b][i].abs()))?;
        m.swap(i, p);
        v.swap(i, p);
        if m[i][i].abs() < 1e-12 {
            return None;
        }
        let pivot = m[i].clone();
        for r in 0..n {
            if r != i {
                let f = m[r][i] / pivot[i];
                for (x, p) in m[r].iter_mut().zip(&pivot) {
                    *x -= f * p;
                }
                v[r] -= f * v[i];
            }
        }
    }
    Some((0..n).map(|i| v[i] / m[i][i]).collect())
}

/// Energy per band of each output's direct region divided by its taps' comb (delays and peak
/// values), summed over both outputs: the filter the taps share. `bands` = (centre, factor):
/// the band runs from centre / factor to centre × factor.
fn comb_divided(hl: &[f64], hr: &[f64], zero: usize, lreg: (usize, usize), rreg: (usize, usize), amps: &[(char, f64, f64)], bands: &[(f64, f64)]) -> Vec<f64> {
    let nfft = 16384;
    let mut band_e = vec![0.0f64; bands.len()];
    for (h, (a, b), side) in [(hl, lreg, 'L'), (hr, rreg, 'R')] {
        let x = &h[a.min(h.len())..b.min(h.len())];
        let spec = audio::spectrum(x, nfft);
        let t0 = (a as f64 - zero as f64) / SR;
        let tp: Vec<&(char, f64, f64)> = amps.iter().filter(|(s, _, _)| *s == side).collect();
        for (k, (fc, w)) in bands.iter().enumerate() {
            let (lo, hi) = ((fc / w * nfft as f64 / SR) as usize, ((fc * w).min(SR / 2.0) * nfft as f64 / SR) as usize);
            for (bin, sp) in spec.iter().enumerate().take(hi.min(nfft / 2) + 1).skip(lo.max(1)) {
                let om = 2.0 * std::f64::consts::PI * bin as f64 * SR / nfft as f64;
                let (mut re, mut im) = (0.0, 0.0);
                for (_, t, v) in &tp {
                    let ph = -om * (t / 1000.0 - t0);
                    re += v * ph.cos();
                    im += v * ph.sin();
                }
                band_e[k] += sp.norm2() / (re * re + im * im).max(1e-30) / (hi - lo + 1).max(1) as f64;
            }
        }
    }
    band_e
}

/// [`Seat`] numbers from the mono-source responses of the two outputs. `zero` = the sample of
/// the plug-in's latency point; times are reported relative to it.
pub fn seat(hl: &[f64], hr: &[f64], zero: usize, geo: Option<&Geometry>) -> Seat {
    let ms = |n: f64| (n - zero as f64) / SR * 1000.0;
    let at = |ms: f64| (zero as f64 + ms * SR / 1000.0).round().max(0.0) as usize;
    let is_peak = |h: &[f64], j: usize| h[j].abs() >= h.get(j + 1).map_or(0.0, |v| v.abs()) && (j == 0 || h[j].abs() > h[j - 1].abs());
    let db = |v: f64| 20.0 * v.abs().max(1e-12).log10();
    let mut taps = vec![];
    let mut amps: Vec<(char, f64, f64)> = vec![]; // output, ms, signed peak value
    for (h, out, side) in [(hl, 1u32, 'L'), (hr, 2u32, 'R')] {
        let mut found: Vec<(Tap, f64)> = vec![];
        if let Some(g) = geo {
            for (mic, _, pred) in g.arrivals().into_iter().filter(|(_, o, _)| *o == out || *o == 3) {
                let (a, b) = (at(pred - 0.2), (at(pred + 0.2) + 1).min(h.len()));
                let Some(i) = (a..b).max_by(|x, y| h[*x].abs().total_cmp(&h[*y].abs())) else { continue };
                found.push((Tap { output: side, mic, predicted_ms: Some(pred), ms: ms(peak_pos(h, i)), db: db(h[i]), gain_db: 0.0 }, h[i]));
            }
        } else {
            // no geometry: the peaks from the latency point to 12 ms within 12 dB of the strongest
            let (a, n) = (at(-0.5), at(12.0).min(h.len()));
            let pk = h[a..n].iter().fold(0.0f64, |m, v| m.max(v.abs()));
            let mut cand: Vec<usize> = (a..n.saturating_sub(1)).filter(|&j| is_peak(h, j) && h[j].abs() >= pk * 0.25).collect();
            cand.sort_by(|x, y| h[*y].abs().total_cmp(&h[*x].abs()));
            let mut kept: Vec<usize> = vec![];
            for j in cand {
                if kept.iter().all(|k| k.abs_diff(j) >= at(0.3) - zero) {
                    kept.push(j);
                }
            }
            found.extend(kept.into_iter().map(|i| (Tap { output: side, mic: String::new(), predicted_ms: None, ms: ms(peak_pos(h, i)), db: db(h[i]), gain_db: 0.0 }, h[i])));
        }
        found.sort_by(|a, b| a.0.ms.total_cmp(&b.0.ms));
        // VSS2 puts its copies on whole samples: divide them out at those times
        amps.extend(found.iter().map(|(t, v)| (side, on_sample(t.ms), *v)));
        taps.extend(found.into_iter().map(|(t, _)| t));
    }
    fit_gains(hl, hr, zero, &mut taps);
    let seg = |h: &[f64], a: usize, b: usize| -> Vec<f64> { h[a.min(h.len())..b.min(h.len())].to_vec() };
    // direct region of each output: from SPREAD_MS before its first tap to SPREAD_MS after its last
    let region = |side: char| {
        let t: Vec<f64> = taps.iter().filter(|t| t.output == side).map(|t| t.ms).collect();
        let (first, last) = (t.iter().cloned().fold(0.0f64, f64::min), t.iter().cloned().fold(0.0f64, f64::max));
        (at(first - SPREAD_MS), at(last + SPREAD_MS))
    };
    let ((la, lb), (ra, rb)) = (region('L'), region('R'));
    // energy in the 1 kHz octave (octave_bands gives mean power per bin: energy in that band)
    let k1k = |x: &[f64]| audio::octave_bands(x, SR).iter().find(|(f, _)| *f == 1000.0).map_or(0.0, |(_, d)| 10f64.powf(d / 10.0));
    let (el, er) = (k1k(&seg(hl, la, lb)), k1k(&seg(hr, ra, rb)));
    // direct tone: each output's region divided by its taps' comb (delays and peak values), so
    // what is left is the filter the taps share (air absorption and the like)
    // octave and third-octave bands: (centre, half-width factor)
    let octs: Vec<(f64, f64)> = [63.0, 125.0, 250.0, 500.0, 1000.0, 2000.0, 4000.0, 8000.0, 16000.0].iter().map(|f| (*f, 2f64.sqrt())).collect();
    let thirds: Vec<(f64, f64)> = (-12..=12).map(|k| (1000.0 * 2f64.powf(k as f64 / 3.0), 2f64.powf(1.0 / 6.0))).collect();
    let (oct_e, third_e) = (comb_divided(hl, hr, zero, (la, lb), (ra, rb), &amps, &octs), comb_divided(hl, hr, zero, (la, lb), (ra, rb), &amps, &thirds));
    let rel1k = |bands: &[(f64, f64)], e: &[f64], min: f64| {
        let k = bands.iter().position(|(f, _)| (*f - 1000.0).abs() < 1.0).unwrap_or(0);
        bands.iter().zip(e).filter(|((f, _), _)| *f >= min).map(|((f, _), v)| ((f * 10.0).round() / 10.0, audio::db(*v) - audio::db(e[k]))).collect::<Vec<_>>()
    };
    let direct_tone_db = rel1k(&octs, &oct_e, 250.0);
    let direct_tone_third_db = rel1k(&thirds, &third_e, 0.0);
    // reflections: after the direct regions
    let start = lb.max(rb);
    let (e80, n) = (at(80.0), hl.len().min(hr.len()));
    let rel = |e: f64| audio::db(e / (el + er).max(1e-30));
    let tone = |a: &[f64], b: &[f64]| {
        let (x, y) = (audio::octave_bands(a, SR), audio::octave_bands(b, SR));
        let sum: Vec<(f64, f64)> = x.iter().zip(&y).map(|((f, p), (_, q))| (*f, audio::db(10f64.powf(p / 10.0) + 10f64.powf(q / 10.0)))).collect();
        let k = sum.iter().find(|(f, _)| *f == 1000.0).map_or(0.0, |x| x.1);
        sum.iter().filter(|(f, _)| *f >= 250.0).map(|(f, v)| (*f, v - k)).collect::<Vec<_>>()
    };
    let strongest = taps.iter().map(|t| t.db).fold(f64::MIN, f64::max);
    let early = k1k(&seg(hl, start, e80)) + k1k(&seg(hr, start, e80));
    let late = k1k(&seg(hl, e80, n)) + k1k(&seg(hr, e80, n));
    // strongest reflections: local maxima of |h|, 0.5 ms apart at least
    let mut refl = vec![];
    for (h, side) in [(hl, 'L'), (hr, 'R')] {
        let mut cand: Vec<usize> = (start.max(1)..e80.min(h.len() - 1)).filter(|&j| is_peak(h, j)).collect();
        cand.sort_by(|x, y| h[*y].abs().total_cmp(&h[*x].abs()));
        let mut kept: Vec<usize> = vec![];
        for j in cand {
            if kept.iter().all(|k| k.abs_diff(j) >= at(0.5) - zero) {
                kept.push(j);
            }
            if kept.len() == 4 {
                break;
            }
        }
        refl.extend(kept.into_iter().map(|j| (ms(j as f64), db(h[j]) - strongest, side)));
    }
    refl.sort_by(|a, b| a.0.total_cmp(&b.0));
    Seat {
        direct_db: (audio::db(el), audio::db(er)),
        direct_tone_db,
        direct_tone_third_db,
        early_db: rel(early),
        late_db: rel(late),
        reflection_tone_db: tone(&seg(hl, start, n), &seg(hr, start, n)),
        reflections: refl,
        taps,
    }
}

fn stereo(l: Vec<f64>, r: Vec<f64>) -> Chans {
    vec![l, r]
}

/// A stereo test signal for the null test: different material on each side.
fn test_signal() -> Chans {
    let n = (3.0 * SR) as usize;
    let mut seed = 12345u64;
    let mut noise = move || {
        seed = seed.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
        2.0 * ((seed >> 33) as f64 / (1u64 << 31) as f64) - 1.0 // uniform in [-1, 1), no DC
    };
    let mut l = vec![0.0; n];
    let mut r = vec![0.0; n];
    for i in 0..n {
        let t = i as f64 / SR;
        let f = 440.0 * (1.0 + 0.006 * (2.0 * std::f64::consts::PI * 5.5 * t).sin());
        let ph = 2.0 * std::f64::consts::PI * f * t;
        let env = if t < 2.0 { (t * 20.0).min(1.0) * ((2.0 - t) * 20.0).min(1.0) } else { 0.0 };
        l[i] = 0.12 * env * (ph.sin() + 0.5 * (2.0 * ph).sin() + 0.25 * (3.0 * ph).sin());
        let burst = ((t * 4.0) as usize).is_multiple_of(2) && t < 2.5;
        r[i] = if burst { 0.08 * noise() } else { 0.0 };
    }
    for k in 0..6 {
        let i = ((0.3 + 0.45 * k as f64) * SR) as usize;
        l[i] += 0.4;
        r[i + 2400] += 0.4;
    }
    stereo(l, r)
}

/// Recomputes the seat numbers of an earlier capture in folder `d` from its saved IRs
/// (after the analysis changed); rewrites `capture.json`.
pub fn reseat(d: &Path, state: &[u8]) -> Result<Capture> {
    let mut c: Capture = serde_json::from_str(&std::fs::read_to_string(d.join("capture.json"))?)?;
    anyhow::ensure!(c.ir_offset_samples > 0, "{}: IRs from before 2026-11-01 session 3 (trimmed); capture again", d.display());
    let (_, h) = audio::read_wav(&d.join("ir-true-stereo.wav"))?;
    anyhow::ensure!(h.len() == 4, "{}: not a true-stereo IR", d.display());
    let hl: Vec<f64> = h[0].iter().zip(&h[2]).map(|(a, b)| a + b).collect();
    let hr: Vec<f64> = h[1].iter().zip(&h[3]).map(|(a, b)| a + b).collect();
    c.seat = seat(&hl, &hr, c.ir_offset_samples, Geometry::of(state).as_ref());
    std::fs::write(d.join("capture.json"), serde_json::to_string_pretty(&c)?)?;
    Ok(c)
}

/// `out/<name>` with characters that are awkward in file names replaced.
pub fn folder(out: &Path, name: &str) -> PathBuf {
    let safe: String = name.chars().map(|c| if c.is_alphanumeric() || c == ' ' || c == '-' { c } else { '_' }).collect();
    out.join(safe.trim())
}

/// Capture one source into folder `d`. `checks` adds repeat, level and null tests.
pub fn capture(rig: &Rig, src: &Source, d: &Path, checks: bool) -> Result<Capture> {
    std::fs::create_dir_all(d)?;
    let state = d.join("state.bin");
    std::fs::write(&state, &src.chunk)?;

    let pre = vec![0.0; (PRE_SECS * SR) as usize];
    let make = |amp: f64| -> Vec<f64> { pre.iter().copied().chain(audio::sweep(SR, SWEEP_SECS, F1, F2, amp)).collect() };
    let x = make(0.25); // −12 dBFS peak
    let zeros = vec![0.0; x.len()];
    let ir_len = (IR_SECS * SR) as usize;
    let run_sweep = |x: &Vec<f64>, left: bool, tag: &str| -> Result<(Vec<f64>, Vec<f64>, usize)> {
        let input = d.join(format!("sweep-{tag}.wav"));
        let chans = if left { stereo(x.clone(), zeros.clone()) } else { stereo(zeros.clone(), x.clone()) };
        audio::write_wav(&input, &chans, SR as u32)?;
        let out = d.join(format!("out-{tag}.wav"));
        let (y, lat) = rig.run(&state, &input, &out)?;
        std::fs::remove_file(&input).ok();
        if !checks {
            std::fs::remove_file(&out).ok(); // 2.8 MB each; kept only with the checks
        }
        if y.len() < 2 {
            bail!("expected stereo output");
        }
        Ok((audio::deconvolve(x, &y[0], SR, F1, F2, ir_len), audio::deconvolve(x, &y[1], SR, F1, F2, ir_len), lat))
    };
    let (ll, lr, lat) = run_sweep(&x, true, "L")?;
    let (rl, rr, _) = run_sweep(&x, false, "R")?;

    let mut c = Capture {
        name: src.name.clone(),
        from: src.from.clone(),
        latency_samples: lat,
        ir_offset_samples: 0,
        pre_latency_db: 0.0,
        seat: Seat::default(),
        paths: vec![],
        l_cross_db: 0.0,
        l_cross_ms: 0.0,
        r_cross_db: 0.0,
        r_cross_ms: 0.0,
        mono_level_db: 0.0,
        mono_bands_db: vec![],
        mono_right_later_ms: 0.0,
        repeat_db: None,
        repeat_parts_db: None,
        repeat_octaves_db: None,
        level_db: None,
        null_db: None,
        self_null_db: None,
        null_l_only_db: None,
        null_r_only_db: None,
        null_r_only_octaves_db: None,
    };
    if checks {
        let (ll2, lr2, _) = run_sweep(&x, true, "L-repeat")?;
        c.repeat_db = Some(audio::residual_db(&ll, &ll2).max(audio::residual_db(&lr, &lr2)));
        let a = audio::arrival(&ll, 0.1);
        let at = |ms: f64| (a as f64 + ms * SR / 1000.0) as usize;
        let part = |from: usize, to: usize| audio::residual_db(&ll[from..to.min(ll.len())], &ll2[from..to.min(ll.len())]);
        c.repeat_parts_db = Some((part(a.saturating_sub(48), at(5.0)), part(at(5.0), at(80.0)), part(at(80.0), ll.len())));
        let diff: Vec<f64> = ll.iter().zip(&ll2).map(|(p, q)| p - q).collect();
        let (bd, br) = (audio::octave_bands(&diff, SR), audio::octave_bands(&ll, SR));
        c.repeat_octaves_db = Some(bd.iter().zip(&br).map(|((f, d), (_, r))| (*f, d - r)).collect());
        audio::write_wav(&d.join("ir-L-repeat-diff.wav"), &[diff], SR as u32)?;
        let (ll3, lr3, _) = run_sweep(&make(0.0625), true, "L-quiet")?;
        c.level_db = Some(audio::residual_db(&ll, &ll3).max(audio::residual_db(&lr, &lr3)));
        let ts = test_signal();
        let tin = d.join("test-in.wav");
        audio::write_wav(&tin, &ts, SR as u32)?;
        let (yv, _) = rig.run(&state, &tin, &d.join("test-vss2.wav"))?;
        let add = |a: Vec<f64>, b: Vec<f64>| -> Vec<f64> { a.iter().zip(&b).map(|(p, q)| p + q).collect() };
        let yl = add(audio::convolve(&ts[0], &ll), audio::convolve(&ts[1], &rl));
        let yr = add(audio::convolve(&ts[0], &lr), audio::convolve(&ts[1], &rr));
        audio::write_wav(&d.join("test-ir.wav"), &[yl.clone(), yr.clone()], SR as u32)?;
        c.null_db = Some((audio::residual_db(&yv[0], &yl), audio::residual_db(&yv[1], &yr)));
        let (yv2, _) = rig.run(&state, &tin, &d.join("test-vss2-again.wav"))?;
        c.self_null_db = Some((audio::residual_db(&yv[0], &yv2[0]), audio::residual_db(&yv[1], &yv2[1])));
        // one side at a time: does each input behave like its IRs on its own?
        let silent = vec![0.0; ts[0].len()];
        for (left, slot) in [(true, &mut c.null_l_only_db), (false, &mut c.null_r_only_db)] {
            let sig = if left { stereo(ts[0].clone(), silent.clone()) } else { stereo(silent.clone(), ts[1].clone()) };
            let tag = if left { "L" } else { "R" };
            let tin = d.join(format!("test-in-{tag}.wav"));
            audio::write_wav(&tin, &sig, SR as u32)?;
            let (yv, _) = rig.run(&state, &tin, &d.join(format!("test-vss2-{tag}.wav")))?;
            let (h0, h1) = if left { (&ll, &lr) } else { (&rl, &rr) };
            let src = if left { &ts[0] } else { &ts[1] };
            let (p0, p1) = (audio::convolve(src, h0), audio::convolve(src, h1));
            *slot = Some((audio::residual_db(&yv[0], &p0), audio::residual_db(&yv[1], &p1)));
            if !left {
                let n = yv[1].len().min(p1.len());
                let diff: Vec<f64> = yv[1][..n].iter().zip(&p1[..n]).map(|(a, b)| a - b).collect();
                let (bd, br) = (audio::octave_bands(&diff, SR), audio::octave_bands(&yv[1][..n], SR));
                c.null_r_only_octaves_db = Some(bd.iter().zip(&br).map(|((f, a), (_, b))| (*f, a - b)).collect());
            }
        }
    }

    // IRs for use: kept whole, latency included. VSS2's direct-sound filters are symmetric
    // around its latency point (found 2026-11-01: up to −5 dB of a flute's response comes before
    // it), so trimming the latency off would cut them in half. A convolver using these IRs
    // reproduces VSS2 with VSS2's own latency (`ir_offset_samples`).
    let pre = (0.004 * SR) as usize;
    c.pre_latency_db = [&ll, &lr, &rl, &rr]
        .iter()
        .map(|h| audio::db(audio::energy(&h[lat.saturating_sub(pre).min(h.len())..lat.min(h.len())]) / audio::energy(h).max(1e-30)))
        .fold(f64::MIN, f64::max);
    c.ir_offset_samples = lat;
    audio::write_wav(&d.join("ir-true-stereo.wav"), &[ll.clone(), lr.clone(), rl.clone(), rr.clone()], SR as u32)?;
    audio::write_wav(&d.join("ir-from-L.wav"), &[ll.clone(), lr.clone()], SR as u32)?;
    audio::write_wav(&d.join("ir-from-R.wav"), &[rl.clone(), rr.clone()], SR as u32)?;
    let hl: Vec<f64> = ll.iter().zip(&rl).map(|(a, b)| a + b).collect();
    let hr: Vec<f64> = lr.iter().zip(&rr).map(|(a, b)| a + b).collect();
    c.seat = seat(&hl, &hr, lat, Geometry::of(&src.chunk).as_ref());

    // the summary numbers below are taken from the latency point on
    let cut = |h: &Vec<f64>| h[lat.min(h.len())..].to_vec();
    let (ll, lr, rl, rr) = (cut(&ll), cut(&lr), cut(&rl), cut(&rr));
    c.paths = [&ll, &lr, &rl, &rr].iter().map(|h| stats(h)).collect();
    let p = &c.paths;
    (c.l_cross_db, c.l_cross_ms) = (p[1].gain_db - p[0].gain_db, p[1].arrival_ms - p[0].arrival_ms);
    (c.r_cross_db, c.r_cross_ms) = (p[2].gain_db - p[3].gain_db, p[2].arrival_ms - p[3].arrival_ms);
    let w = (0.010 * SR) as usize;
    let hl: Vec<f64> = (0..w).map(|i| ll[i] + rl[i]).collect();
    let hr: Vec<f64> = (0..w).map(|i| lr[i] + rr[i]).collect();
    c.mono_level_db = audio::db(audio::energy(&hl) / audio::energy(&hr).max(1e-30));
    let (bl, br) = (audio::octave_bands(&hl, SR), audio::octave_bands(&hr, SR));
    c.mono_bands_db = bl.iter().zip(&br).filter(|((f, _), _)| (125.0..=8000.0).contains(f)).map(|((f, a), (_, b))| (*f, a - b)).collect();
    let max_lag = (0.0015 * SR) as i64;
    let xc = |lag: i64| -> f64 { (0..w as i64).filter(|i| (0..w as i64).contains(&(i + lag))).map(|i| hl[i as usize] * hr[(i + lag) as usize]).sum() };
    let best = (-max_lag..=max_lag).max_by(|a, b| xc(*a).total_cmp(&xc(*b))).unwrap_or(0);
    c.mono_right_later_ms = best as f64 / SR * 1000.0;
    std::fs::write(d.join("capture.json"), serde_json::to_string_pretty(&c)?)?;
    Ok(c)
}

pub fn table_header() -> &'static str {
    "| Pin | Source | Mono source: L−R level / right later by | Gain L→L / R→R | Cross L→R / R→L | Arrival L→L / R→R | Direct / early / late (L→L) | Length | Repeat direct / early / late | Level | Null L / R (VSS2 vs itself) |\n|---|---|---|---|---|---|---|---|---|---|---|"
}

pub fn table_row(c: &Capture) -> String {
    let p = &c.paths;
    let o = |x: Option<f64>| x.map_or("–".into(), |v| format!("{v:.0} dB"));
    format!(
        "| {} | {} | {:+.1} dB / {:+.2} ms | {:.1} / {:.1} dB | {:+.1} dB {:+.2} ms / {:+.1} dB {:+.2} ms | {:.2} / {:.2} ms | {:.0} / {:.0} / {:.0} % | {:.0} ms | {} | {} | {} |",
        c.name,
        c.from,
        c.mono_level_db,
        c.mono_right_later_ms,
        p[0].gain_db,
        p[3].gain_db,
        c.l_cross_db,
        c.l_cross_ms,
        c.r_cross_db,
        c.r_cross_ms,
        p[0].arrival_ms,
        p[3].arrival_ms,
        p[0].direct_pct,
        p[0].early_pct,
        p[0].late_pct,
        p[0].length_ms.max(p[3].length_ms),
        c.repeat_parts_db.map_or("–".into(), |(a, b, x)| format!("{a:.0} / {b:.0} / {x:.0} dB")),
        o(c.level_db),
        match (c.null_db, c.self_null_db) {
            (Some((a, b)), Some((p, q))) => format!("{a:.0} / {b:.0} dB ({p:.0} / {q:.0})"),
            _ => "–".into(),
        }
    )
}

/// Blind A/B listening files (E7 groundwork): each (capture folder, stem) pair is processed by
/// VSS2 (the capture's `state.bin`, through vi-render) and by the capture's true-stereo IR; the
/// results are summed, given one common gain (peaks ≤ −1 dBFS), and written as `A.wav` /
/// `B.wav` in random order, with `dry.wav` (unplaced) and `key.txt` (which is which).
pub fn ab(rig: &Rig, pairs: &[(PathBuf, PathBuf)], start: f64, secs: f64, out: &Path) -> Result<String> {
    std::fs::create_dir_all(out)?;
    let n = (secs * SR) as usize;
    let a0 = (start * SR) as usize;
    let mut mix = [vec![vec![0.0; n]; 2], vec![vec![0.0; n]; 2], vec![vec![0.0; n]; 2]]; // vss, ir, dry
    for (k, (cap, stem)) in pairs.iter().enumerate() {
        let (sr, x) = audio::read_wav(stem)?;
        anyhow::ensure!(sr as f64 == SR, "{} is {sr} Hz; captures are at 48 kHz", stem.display());
        let fade = (0.02 * SR) as usize;
        let ex: Chans = (0..2)
            .map(|c| {
                let src = x.get(c).unwrap_or(&x[0]);
                (0..n)
                    .map(|i| {
                        let g = (i.min(n - 1 - i) as f64 / fade as f64).min(1.0);
                        src.get(a0 + i).copied().unwrap_or(0.0) * g
                    })
                    .collect()
            })
            .collect();
        let tmp = out.join(format!("in-{k}.wav"));
        audio::write_wav(&tmp, &ex, SR as u32)?;
        let (yv, lat) = rig.run(&cap.join("state.bin"), &tmp, &out.join(format!("vss-{k}.wav")))?;
        std::fs::remove_file(&tmp).ok();
        std::fs::remove_file(out.join(format!("vss-{k}.wav"))).ok();
        let (_, h) = audio::read_wav(&cap.join("ir-true-stereo.wav"))?;
        let off = std::fs::read_to_string(cap.join("capture.json")).ok().and_then(|j| serde_json::from_str::<Capture>(&j).ok()).map_or(0, |c| c.ir_offset_samples);
        let yi = audio::apply_true_stereo(&ex, &h);
        for c in 0..2 {
            for i in 0..n {
                mix[0][c][i] += yv[c].get(i + lat).copied().unwrap_or(0.0);
                mix[1][c][i] += yi[c].get(i + off).copied().unwrap_or(0.0);
                mix[2][c][i] += ex[c][i];
            }
        }
    }
    let peak = mix.iter().flatten().flatten().fold(0.0f64, |m, v| m.max(v.abs()));
    let g = if peak > 0.0 { 0.891 / peak } else { 1.0 };
    for m in mix.iter_mut() {
        for c in m.iter_mut() {
            c.iter_mut().for_each(|v| *v *= g);
        }
    }
    let flip = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map_or(0, |d| d.subsec_nanos()) % 2 == 1;
    let (a, b) = if flip { (1, 0) } else { (0, 1) };
    audio::write_wav(&out.join("A.wav"), &mix[a], SR as u32)?;
    audio::write_wav(&out.join("B.wav"), &mix[b], SR as u32)?;
    audio::write_wav(&out.join("dry.wav"), &mix[2], SR as u32)?;
    let name = |i: usize| if i == 0 { "VSS2 (live plug-in)" } else { "captured impulse responses" };
    let key = format!(
        "A = {}\nB = {}\n\nSources: {}\nExcerpt: {start} s for {secs} s; common gain {:+.1} dB.\n",
        name(a),
        name(b),
        pairs.iter().map(|(c, s)| format!("{} <- {}", s.file_name().unwrap_or_default().to_string_lossy(), c.file_name().unwrap_or_default().to_string_lossy())).collect::<Vec<_>>().join("; "),
        20.0 * g.log10()
    );
    std::fs::write(out.join("key.txt"), &key)?;
    let d = |x: &Chans, y: &Chans| (audio::residual_db(&x[0], &y[0]) + audio::residual_db(&x[1], &y[1])) / 2.0;
    Ok(format!("A/B written to {}; A vs B residual {:.1} dB (key in key.txt)", out.display(), d(&mix[0], &mix[1])))
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Taps placed where the geometry says are found there, with their levels, and a pure
    /// two-tap response has a flat direct tone (the comb is divided out).
    #[test]
    fn seat_finds_microphone_taps() {
        let mic = vss2::Mic::parse(&crate::vss2::tests::decca_mic()).unwrap();
        let g = Geometry { source: [3.2, 7.9, 1.5], mic };
        let arr = g.arrivals();
        let zero = 192;
        let n = (0.3 * SR) as usize;
        let (mut hl, mut hr) = (vec![0.0; n], vec![0.0; n]);
        for (mic, out, ms) in &arr {
            let i = zero + (ms * SR / 1000.0).round() as usize;
            let v = if mic == "C" { 0.2 } else { 0.6 };
            if *out == 1 || *out == 3 {
                hl[i] += v;
            }
            if *out == 2 || *out == 3 {
                hr[i] += v;
            }
        }
        hl[zero + (30.0 * SR / 1000.0) as usize] = 0.05; // one reflection at 30 ms
        let s = seat(&hl, &hr, zero, Some(&g));
        assert_eq!(s.taps.len(), 4);
        for t in &s.taps {
            assert!((t.ms - t.predicted_ms.unwrap()).abs() < 0.02, "{t:?}");
            let want = if t.mic == "C" { 0.2f64 } else { 0.6 };
            assert!((t.db - 20.0 * want.log10()).abs() < 0.01, "{t:?}");
            assert!((t.gain_db - 20.0 * want.log10()).abs() < 0.05, "{t:?}");
        }
        assert!(s.direct_tone_db.iter().all(|(_, d)| d.abs() < 0.5), "{:?}", s.direct_tone_db);
        assert!((s.reflections[0].0 - 30.0).abs() < 0.03 && s.reflections[0].2 == 'L');
    }
}
