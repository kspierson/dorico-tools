//! E5: stagecraft's own placement engine. A **stage** = a space (microphones, levels, timing
//! rules), an air EQ and the players' seats, all plain numbers in a TOML file that can be
//! edited. From it each player gets per-output **taps** (one delayed, scaled copy per
//! microphone) and an EQ, or a rendered impulse response.
//!
//! `stages/vss2-compat.toml` holds VSS2's behaviour as measured in E3; [`Stage::from_vss2`]
//! turns a project's VSS2 settings into a stage that sounds like VSS2's direct sound, and
//! [`check`] compares such a stage with the captures. Everything VSS2 fixed (microphone plan,
//! distance law, centre-capsule level, mic position limits, alignment of every player to its
//! nearest microphone) is a setting here.

use crate::audio::{self, Chans};
use crate::vss2;
use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use std::path::Path;

/// A microphone and where it goes in the mix.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Mic {
    pub name: String,
    /// Metres: x across (− = left as heard), y back from the stage edge (− = in front), z up.
    pub position: [f64; 3],
    /// Where it points (any length).
    pub direction: [f64; 3],
    /// 0 = omni, 0.5 = cardioid, 1 = figure of eight.
    #[serde(default)]
    pub pattern: f64,
    /// Mix level into the left / right output, dB (absent = not routed there).
    #[serde(default)]
    pub left_db: Option<f64>,
    #[serde(default)]
    pub right_db: Option<f64>,
    /// Extra delay for this microphone (an engineer's time alignment of spot mics), ms.
    #[serde(default)]
    pub delay_ms: f64,
}

/// The space: microphones and the rules every player follows.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Space {
    pub name: String,
    #[serde(default = "default_c")]
    pub speed_of_sound: f64,
    /// Level falls as 1 / distance^exponent (1.0 = inverse distance, the physical value).
    #[serde(default = "one")]
    pub distance_exponent: f64,
    /// Overall level, dB.
    #[serde(default)]
    pub level_db: f64,
    /// Arrival times: 0 = every player's nearest microphone at the same moment (VSS2: depth by
    /// level and tone only); 1 = real arrival times, measured from `depth_reference_m`.
    #[serde(default)]
    pub depth_delay: f64,
    /// Distance (m) that arrives with no delay when `depth_delay` > 0.
    #[serde(default)]
    pub depth_reference_m: f64,
    /// true = fractional-sample delays (exact timing); false = whole samples, as VSS2 does
    /// (found 2026-11-02: each microphone's travel time rounded, minus the earliest one's).
    #[serde(default = "yes")]
    pub exact_delays: bool,
    /// Physical air absorption (ISO 9613-1) on every path, by its length: treble loss that
    /// grows with distance. VSS2 has none (its "Air" is a fixed EQ per player).
    #[serde(default)]
    pub air_absorption: bool,
    #[serde(default = "twenty")]
    pub temperature_c: f64,
    #[serde(default = "fifty")]
    pub humidity_pct: f64,
    /// A shoebox around the stage: each surface gives every player one first reflection.
    #[serde(default)]
    pub room: Option<Room>,
    /// Per-player send level into a shared early-reflection layer (front drier, back wetter).
    #[serde(default)]
    pub reflections: Option<Sends>,
    pub mics: Vec<Mic>,
}

fn default_c() -> f64 {
    343.0
}
fn one() -> f64 {
    1.0
}
fn yes() -> bool {
    true
}
fn twenty() -> f64 {
    20.0
}
fn fifty() -> f64 {
    50.0
}

/// A rectangular room: x from −width/2 to +width/2, y from `front_m` to `front_m + length_m`,
/// z from 0 (floor) to `height_m`. Each surface's `*_db` is its reflection level (0 = a
/// perfect mirror, −3 ≈ half the energy absorbed); absent = that surface gives no reflection.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Room {
    pub width_m: f64,
    pub length_m: f64,
    pub height_m: f64,
    /// y of the front wall (behind the microphones: negative).
    pub front_m: f64,
    #[serde(default)]
    pub floor_db: Option<f64>,
    #[serde(default)]
    pub ceiling_db: Option<f64>,
    #[serde(default)]
    pub left_db: Option<f64>,
    #[serde(default)]
    pub right_db: Option<f64>,
    #[serde(default)]
    pub front_db: Option<f64>,
    #[serde(default)]
    pub back_db: Option<f64>,
}

/// Send level = `send_db` + `per_m_db` × (player's distance to the main microphones −
/// `reference_m`).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Sends {
    pub send_db: f64,
    #[serde(default)]
    pub per_m_db: f64,
    #[serde(default)]
    pub reference_m: f64,
}

/// Air absorption in dB per metre (ISO 9613-1, sea-level pressure).
pub fn absorption_db_per_m(f: f64, temperature_c: f64, humidity_pct: f64) -> f64 {
    let t = temperature_c + 273.15;
    let (t0, t01) = (293.15, 273.16);
    let c = -6.8346 * (t01 / t).powf(1.261) + 4.6151;
    let h = humidity_pct * 10f64.powf(c);
    let fr_o = 24.0 + 4.04e4 * h * (0.02 + h) / (0.391 + h);
    let fr_n = (t / t0).powf(-0.5) * (9.0 + 280.0 * h * (-4.170 * ((t / t0).powf(-1.0 / 3.0) - 1.0)).exp());
    let f2 = f * f;
    8.686 * f2 * (1.84e-11 * (t / t0).sqrt() + (t / t0).powf(-2.5) * (0.01275 * (-2239.1 / t).exp() / (fr_o + f2 / fr_o) + 0.1068 * (-3352.0 / t).exp() / (fr_n + f2 / fr_n)))
}

/// An EQ that is `amount × shape(f)` dB (VSS2's "Air"; linear phase).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AirEq {
    pub shape_hz: Vec<f64>,
    pub shape_db: Vec<f64>,
    /// `amount` as a function of a player's `air` value (VSS2's scale), interpolated.
    pub amount_air: Vec<f64>,
    pub amount: Vec<f64>,
    /// Amount for a player without an `air` value.
    #[serde(default)]
    pub no_air_amount: f64,
}

impl AirEq {
    pub fn amount_for(&self, air: Option<f64>) -> f64 {
        let Some(a) = air else { return self.no_air_amount };
        interp(&self.amount_air, &self.amount, a, true)
    }

    /// dB at `f` for `amount` (shape interpolated in log frequency; above the last point it
    /// continues ∝ f², below the first it is 0).
    pub fn db(&self, f: f64, amount: f64) -> f64 {
        let (hz, db) = (&self.shape_hz, &self.shape_db);
        if hz.is_empty() || f <= hz[0] {
            return 0.0;
        }
        let last = hz.len() - 1;
        let s = if f >= hz[last] {
            db[last] * (f / hz[last]).powi(2)
        } else {
            let lf: Vec<f64> = hz.iter().map(|x| x.ln()).collect();
            interp(&lf, db, f.ln(), false)
        };
        amount * s
    }

    /// A brightness EQ on the same shape, `db16k` dB at 16 kHz (positive = brighter).
    pub fn brightness_db(&self, f: f64, db16k: f64) -> f64 {
        let unit = self.db(16000.0, 1.0);
        if db16k == 0.0 || unit == 0.0 { 0.0 } else { self.db(f, 1.0) / unit * db16k }
    }
}

/// Linear interpolation in sorted `xs` (clamped at the ends unless `extrapolate`).
fn interp(xs: &[f64], ys: &[f64], x: f64, extrapolate: bool) -> f64 {
    if xs.len() < 2 {
        return ys.first().copied().unwrap_or(0.0);
    }
    let i = xs.iter().position(|v| *v >= x).unwrap_or(xs.len() - 1).clamp(1, xs.len() - 1);
    let (x0, x1, y0, y1) = (xs[i - 1], xs[i], ys[i - 1], ys[i]);
    let t = (x - x0) / (x1 - x0);
    let t = if extrapolate { t } else { t.clamp(0.0, 1.0) };
    y0 + t * (y1 - y0)
}

/// One player's seat.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Player {
    pub name: String,
    pub position: [f64; 3],
    #[serde(default)]
    pub gain_db: f64,
    /// VSS2-scale air value (−100 … 100; see [`AirEq`]); stagecraft stages use `brightness_db`
    /// and the space's physical `air_absorption` instead.
    #[serde(default)]
    pub air: Option<f64>,
    /// Presence: dB at 16 kHz on the air shape (positive = brighter), independent of distance.
    #[serde(default)]
    pub brightness_db: f64,
    /// Degrees; 0 = facing the front (the microphones), positive = turned toward +x.
    #[serde(default)]
    pub facing_deg: f64,
    /// A section's width (m): the left input plays from the left end, the right input from the
    /// right end (across the facing direction). 0 = a point (both inputs from one spot).
    #[serde(default)]
    pub width_m: f64,
    /// Where the seat came from (free text).
    #[serde(default)]
    pub note: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Stage {
    pub space: Space,
    pub air: AirEq,
    #[serde(default)]
    pub players: Vec<Player>,
}

/// One microphone's copy of a player in one output.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Tap {
    pub mic: String,
    /// 0 = left, 1 = right.
    pub output: usize,
    /// Which input feeds it: 0 = left, 1 = right, 2 = both (a point: each at half level).
    #[serde(default = "two")]
    pub input: usize,
    /// "direct", or the surface it reflects from ("floor", "ceiling", "left wall", …).
    #[serde(default = "direct")]
    pub path: String,
    pub delay_ms: f64,
    pub gain_db: f64,
    /// Path length (m) and the shift subtracted from every copy of this player (ms), for
    /// rounding as VSS2 does; the microphone's own extra delay (ms).
    #[serde(default)]
    pub distance_m: f64,
    #[serde(default)]
    pub shift_ms: f64,
    #[serde(default)]
    pub extra_ms: f64,
}

fn two() -> usize {
    2
}
fn direct() -> String {
    "direct".into()
}

/// Everything a host needs for one player: its taps, the EQs, its reflection send.
#[derive(Debug, Clone, Serialize)]
pub struct Placement {
    pub player: String,
    pub taps: Vec<Tap>,
    /// VSS2-style air amount and brightness (dB at 16 kHz) applied to every tap.
    pub air_amount: f64,
    pub brightness_db: f64,
    /// Send into the shared reflection layer, dB (none = no layer in this space).
    pub send_db: Option<f64>,
}

impl Stage {
    pub fn read(path: &Path) -> Result<Stage> {
        toml::from_str(&std::fs::read_to_string(path)?).with_context(|| format!("{}", path.display()))
    }

    pub fn to_toml(&self) -> Result<String> {
        Ok(toml::to_string(self)?)
    }

    /// Where the player's sound comes from: (input, position) per emitter. A point is one
    /// emitter fed by both inputs; a section is its two ends.
    fn emitters(p: &Player) -> Vec<(usize, [f64; 3])> {
        if p.width_m <= 0.0 {
            return vec![(2, p.position)];
        }
        let a = p.facing_deg.to_radians();
        let across = [a.cos(), a.sin()];
        let h = p.width_m / 2.0;
        let at = |s: f64| [p.position[0] + s * h * across[0], p.position[1] + s * h * across[1], p.position[2]];
        vec![(0, at(-1.0)), (1, at(1.0))]
    }

    /// Image sources of `pos` in the room's surfaces: (surface, image position, level dB).
    fn images(&self, pos: [f64; 3]) -> Vec<(&'static str, [f64; 3], f64)> {
        let Some(r) = &self.space.room else { return vec![] };
        let (x, y, z) = (pos[0], pos[1], pos[2]);
        let back = r.front_m + r.length_m;
        [
            ("floor", [x, y, -z], r.floor_db),
            ("ceiling", [x, y, 2.0 * r.height_m - z], r.ceiling_db),
            ("left wall", [-r.width_m - x, y, z], r.left_db),
            ("right wall", [r.width_m - x, y, z], r.right_db),
            ("front wall", [x, 2.0 * r.front_m - y, z], r.front_db),
            ("back wall", [x, 2.0 * back - y, z], r.back_db),
        ]
        .into_iter()
        .filter_map(|(n, p, db)| db.map(|d| (n, p, d)))
        .collect()
    }

    /// The player's taps, by output then delay.
    pub fn taps(&self, p: &Player) -> Vec<Tap> {
        let sp = &self.space;
        let dist = |a: [f64; 3], b: [f64; 3]| (0..3).map(|k| (a[k] - b[k]).powi(2)).sum::<f64>().sqrt().max(0.01);
        let emitters = Self::emitters(p);
        let nearest = emitters.iter().flat_map(|(_, e)| sp.mics.iter().map(move |m| dist(*e, m.position))).fold(f64::MAX, f64::min) / sp.speed_of_sound;
        let shift = (1.0 - sp.depth_delay) * nearest + sp.depth_delay * sp.depth_reference_m / sp.speed_of_sound;
        let mut out = vec![];
        for (input, e) in &emitters {
            let mut sources = vec![("direct", *e, 0.0)];
            sources.extend(self.images(*e));
            for (path, src, surface_db) in sources {
                for m in &sp.mics {
                    let d = dist(src, m.position);
                    let n = (m.direction.iter().map(|x| x * x).sum::<f64>()).sqrt().max(1e-9);
                    let cos = (0..3).map(|k| m.direction[k] / n * (src[k] - m.position[k]) / d).sum::<f64>();
                    let pat = ((1.0 - m.pattern) + m.pattern * cos).abs().max(1e-6);
                    let g = sp.level_db + p.gain_db + surface_db - 20.0 * sp.distance_exponent * d.log10() + 20.0 * pat.log10();
                    let delay_ms = ((d / sp.speed_of_sound - shift) * 1000.0 + m.delay_ms).max(0.0);
                    for (o, mix) in [(0, m.left_db), (1, m.right_db)] {
                        if let Some(mix) = mix {
                            out.push(Tap { mic: m.name.clone(), output: o, input: *input, path: path.into(), delay_ms, gain_db: g + mix, distance_m: d, shift_ms: shift * 1000.0, extra_ms: m.delay_ms });
                        }
                    }
                }
            }
        }
        out.sort_by(|a, b| a.output.cmp(&b.output).then(a.delay_ms.total_cmp(&b.delay_ms)));
        out
    }

    /// Send level into the reflection layer (distance to the centre of the microphones).
    pub fn send_db(&self, p: &Player) -> Option<f64> {
        let s = self.space.reflections.as_ref()?;
        let n = self.space.mics.len().max(1) as f64;
        let c: Vec<f64> = (0..3).map(|k| self.space.mics.iter().map(|m| m.position[k]).sum::<f64>() / n).collect();
        let d = (0..3).map(|k| (p.position[k] - c[k]).powi(2)).sum::<f64>().sqrt();
        Some(s.send_db + s.per_m_db * (d - s.reference_m))
    }

    pub fn placement(&self, p: &Player) -> Placement {
        Placement { player: p.name.clone(), taps: self.taps(p), air_amount: self.air.amount_for(p.air), brightness_db: p.brightness_db, send_db: self.send_db(p) }
    }

    /// Mono-source response of each output (L, R): `len` samples, the taps placed `latency`
    /// samples in (linear-phase EQ around them, as VSS2 does).
    pub fn render(&self, p: &Player, sr: f64, latency: usize, len: usize) -> Chans {
        self.render_band(p, sr, latency, len, None)
    }

    /// [`Stage::render`] with nothing above `max_hz` (to compare with captures, which are
    /// measured up to 23 kHz).
    pub fn render_band(&self, p: &Player, sr: f64, latency: usize, len: usize, max_hz: Option<f64>) -> Chans {
        let ts = self.true_stereo_band(p, sr, latency, len, max_hz);
        let sum = |a: &Vec<f64>, b: &Vec<f64>| a.iter().zip(b).map(|(x, y)| x + y).collect::<Vec<f64>>();
        vec![sum(&ts[0], &ts[2]), sum(&ts[1], &ts[3])]
    }

    /// True-stereo IR (LL, LR, RL, RR): from each input to each output.
    pub fn true_stereo(&self, p: &Player, sr: f64, latency: usize, len: usize) -> Chans {
        self.true_stereo_band(p, sr, latency, len, None)
    }

    fn true_stereo_band(&self, p: &Player, sr: f64, latency: usize, len: usize, max_hz: Option<f64>) -> Chans {
        let taps = self.taps(p);
        let amount = self.air.amount_for(p.air);
        let n = (len * 2).next_power_of_two();
        let sp = &self.space;
        let mut out = vec![];
        for input in 0..2 {
            for o in 0..2 {
                let mine: Vec<&Tap> = taps.iter().filter(|t| t.output == o && (t.input == input || t.input == 2)).collect();
                let mut spec = vec![audio::C::default(); n];
                for (k, c) in spec.iter_mut().enumerate().take(n / 2 + 1) {
                    let f = k as f64 * sr / n as f64;
                    if max_hz.is_some_and(|m| f > m) {
                        continue;
                    }
                    let eq_db = self.air.db(f, amount) + self.air.brightness_db(f, p.brightness_db);
                    let absorb = if sp.air_absorption { absorption_db_per_m(f, sp.temperature_c, sp.humidity_pct) } else { 0.0 };
                    for t in &mine {
                        let share = if t.input == 2 { 0.5 } else { 1.0 };
                        let g = share * 10f64.powf((t.gain_db + eq_db - absorb * t.distance_m) / 20.0);
                        let mut delay = t.delay_ms / 1000.0 * sr + latency as f64;
                        if !sp.exact_delays {
                            // VSS2: each microphone's travel time in whole samples, minus the
                            // earliest one's (found 2026-11-02)
                            let whole = (t.distance_m / sp.speed_of_sound * sr).round() - (t.shift_ms / 1000.0 * sr).round() + (t.extra_ms / 1000.0 * sr).round();
                            delay = whole.max(0.0) + latency as f64;
                        }
                        let ph = -2.0 * std::f64::consts::PI * f * delay / sr;
                        c.re += g * ph.cos();
                        c.im += g * ph.sin();
                    }
                }
                for k in 1..n / 2 {
                    spec[n - k] = spec[k].conj();
                }
                audio::fft(&mut spec, true);
                out.push(spec.iter().take(len).map(|c| c.re).collect());
            }
        }
        // order: input L → (out L, out R), input R → (out L, out R) = LL, LR, RL, RR
        out
    }
}

/// Rounds to 4 decimals (VSS2 stores f32: 1.8 comes back as 1.7999999523).
fn r4(x: f64) -> f64 {
    (x * 1e4).round() / 1e4
}

/// VSS2's behaviour as numbers (`stages/vss2-compat.toml`).
#[derive(Debug, Clone, Deserialize)]
pub struct Compat {
    pub speed_of_sound: f64,
    pub centre_mix_db: f64,
    pub rooms: BTreeMap<String, CompatRoom>,
    pub air: AirEq,
}

#[derive(Debug, Clone, Deserialize)]
pub struct CompatRoom {
    pub base_db: f64,
    pub distance_exponent: f64,
    #[serde(default)]
    pub mic_max_front: Option<f64>,
    #[serde(default)]
    pub mic_max_height: Option<f64>,
}

impl Compat {
    pub fn read(path: &Path) -> Result<Compat> {
        toml::from_str(&std::fs::read_to_string(path)?).with_context(|| format!("{}", path.display()))
    }

    /// The default file next to the crate.
    pub fn default_path() -> std::path::PathBuf {
        Path::new(env!("CARGO_MANIFEST_DIR")).join("stages/vss2-compat.toml")
    }

    /// The space VSS2 builds for a room: its main microphones (inside the room's limits),
    /// mixed as VSS2 mixes them.
    pub fn space(&self, room: &vss2::Room) -> Result<Space> {
        let rc = self.rooms.get(&room.name).with_context(|| format!("no VSS2 numbers for room {:?}", room.name))?;
        let mut mic = room.mic.clone().context("room without a saved microphone setup")?;
        if let Some(f) = rc.mic_max_front {
            mic.position[1] = mic.position[1].max(-f as f32);
        }
        if let Some(h) = rc.mic_max_height {
            mic.position[2] = mic.position[2].min(h as f32);
        }
        let mics = mic
            .capsules
            .iter()
            .map(|c| {
                let (name, l, r) = match c.output {
                    1 => ("L", Some(0.0), None),
                    2 => ("R", None, Some(0.0)),
                    _ => ("C", Some(self.centre_mix_db), Some(self.centre_mix_db)),
                };
                Mic {
                    name: name.into(),
                    position: [0, 1, 2].map(|k| r4((mic.position[k] + c.position[k]) as f64)),
                    direction: c.direction.map(|v| r4(v as f64)),
                    pattern: r4(c.pattern as f64),
                    left_db: l,
                    right_db: r,
                    delay_ms: 0.0,
                }
            })
            .collect();
        Ok(Space {
            name: format!("VSS2 {}", room.describe()),
            speed_of_sound: self.speed_of_sound,
            distance_exponent: rc.distance_exponent,
            level_db: rc.base_db + room.level.unwrap_or(0.0),
            depth_delay: 0.0,
            depth_reference_m: 0.0,
            exact_delays: false,
            air_absorption: false,
            temperature_c: 20.0,
            humidity_pct: 50.0,
            room: None,
            reflections: None,
            mics,
        })
    }

    /// A player from a VSS2 state (point sources; sections are placed at their centre).
    pub fn player(state: &[u8]) -> Result<Player> {
        let v = vss2::Vss2::from_props(vss2::parse_state(state)?);
        let mut note = format!("VSS2 {}", v.preset_name());
        if v.emitters > 1 {
            note.push_str("; a section (VSS2: 2 emitters; input-to-end mapping not yet checked against VSS2)");
        }
        Ok(Player {
            name: v.name.clone(),
            position: [r4(v.x as f64), r4(v.y as f64), r4(v.z as f64)],
            gain_db: v.gain.unwrap_or(0.0) + v.direct_level.unwrap_or(0.0),
            air: v.air,
            brightness_db: 0.0,
            facing_deg: r4(v.facing as f64),
            width_m: if v.emitters > 1 { r4(v.width as f64) } else { 0.0 },
            note,
        })
    }
}

/// A space (and its EQ curve) on its own: a `[space]` + `[air]` file such as
/// `stages/film-stage-starter.toml`.
#[derive(Debug, Clone, Deserialize)]
pub struct SpaceFile {
    pub space: Space,
    pub air: AirEq,
}

impl Stage {
    /// Puts these players into another space. Each player's VSS2 Air setting becomes the same
    /// curve as `brightness_db` (dB at 16 kHz), so the tone is unchanged and the space's
    /// physical air absorption can take over the distance part.
    pub fn into_space(mut self, sf: &SpaceFile) -> Stage {
        for p in self.players.iter_mut() {
            if p.air.is_some() {
                let db16 = self.air.amount_for(p.air) * self.air.db(16000.0, 1.0);
                p.brightness_db += r4(db16);
                p.note.push_str(&format!("; VSS2 Air {} → brightness {:+.1} dB", p.air.unwrap_or(0.0), db16));
                p.air = None;
            }
        }
        self.space = sf.space.clone();
        self.air = sf.air.clone();
        self
    }

    /// A VSS2-compatible stage from VSS2 states (all from one project, so one room).
    pub fn from_vss2(compat: &Compat, states: &[Vec<u8>]) -> Result<Stage> {
        let room = states.iter().find_map(|s| vss2::room(s)).context("no VSS2 room in these states")?;
        let mut players = vec![];
        for s in states {
            players.push(Compat::player(s)?);
        }
        Ok(Stage { space: compat.space(&room)?, air: compat.air.clone(), players })
    }
}

/// How close a VSS2-compatible stage comes to the captured VSS2 direct sound of one setting.
#[derive(Debug, Serialize)]
pub struct CheckRow {
    pub id: String,
    pub name: String,
    pub room: String,
    /// Residual of the direct sound (from 4 ms before the first tap to 4 ms after the last),
    /// model vs capture, per output, dB (−30 dB ≈ 3 % of the energy left over).
    pub residual_db: (f64, f64),
    /// Level difference model − capture in the 1 kHz octave, per output, dB.
    pub level_db: (f64, f64),
    /// The residual over 200 Hz–20 kHz only, per output, dB (a few ms of response says little
    /// about low frequencies).
    pub residual_band_db: (f64, f64),
    /// Capture / model in third octaves (250 Hz–20 kHz, both outputs), dB: what the model
    /// still misses in tone.
    pub tone_db: Vec<(f64, f64)>,
    /// The setting's Air value.
    pub air: Option<f64>,
}

/// Checks every captured setting in `lib` (a library folder) that the model covers: rooms
/// with a saved mic setup, no input-balance offsets (GoLR/DoLR), not muted. Sections (two
/// emitters) are reported as their own rows ("[sections]").
pub fn check(compat: &Compat, lib: &Path) -> Result<Vec<CheckRow>> {
    let json: Vec<crate::library::Setting> = serde_json::from_str(&std::fs::read_to_string(lib.join("library.json"))?)?;
    let mut rows = vec![];
    for s in json {
        let (Some(c), Some(room)) = (&s.capture, &s.room) else { continue };
        if room.mic.is_none() || c.ir_offset_samples == 0 || !compat.rooms.contains_key(&room.name) {
            continue;
        }
        let d = lib.join(&s.id);
        let state = std::fs::read(d.join("state.bin"))?;
        let props = vss2::parse_state(&state)?;
        let nonzero = |t: &str| props.iter().any(|(k, v)| k == t && !matches!(v, vss2::Value::Double(x) if *x == 0.0));
        if nonzero("GoLR") || nonzero("DoLR") || c.seat.taps.iter().all(|t| t.db < -40.0) {
            continue;
        }
        let stage = Stage::from_vss2(compat, std::slice::from_ref(&state))?;
        let (_, h) = audio::read_wav(&d.join("ir-true-stereo.wav"))?;
        let cap: Chans = vec![h[0].iter().zip(&h[2]).map(|(a, b)| a + b).collect(), h[1].iter().zip(&h[3]).map(|(a, b)| a + b).collect()];
        let model = stage.render_band(&stage.players[0], crate::capture::SR, c.ir_offset_samples, cap[0].len(), Some(crate::capture::F2));
        let taps = stage.taps(&stage.players[0]);
        let at = |ms: f64| (c.ir_offset_samples as f64 + ms * crate::capture::SR / 1000.0).round().max(0.0) as usize;
        let mut res = [0.0; 2];
        let mut res_band = [0.0; 2];
        let mut lev = [0.0; 2];
        let nfft = 8192;
        let mut ec = [0.0f64; 20];
        let mut em = [0.0f64; 20];
        let centres: Vec<f64> = (-6..=13).map(|k| 1000.0 * 2f64.powf(k as f64 / 3.0)).collect();
        for o in 0..2 {
            let ts: Vec<f64> = taps.iter().filter(|t| t.output == o).map(|t| t.delay_ms).collect();
            let (a, b) = (at(ts.iter().cloned().fold(0.0, f64::min) - 4.0), at(ts.iter().cloned().fold(0.0, f64::max) + 4.0).min(cap[o].len()));
            res[o] = audio::residual_db(&cap[o][a..b], &model[o][a..b]);
            let k1 = |x: &[f64]| audio::octave_bands(x, crate::capture::SR).iter().find(|(f, _)| *f == 1000.0).map_or(0.0, |v| v.1);
            lev[o] = k1(&model[o][a..b]) - k1(&cap[o][a..b]);
            let (sc, sm) = (audio::spectrum(&cap[o][a..b], nfft), audio::spectrum(&model[o][a..b], nfft));
            let (lo, hi) = ((200.0 * nfft as f64 / crate::capture::SR) as usize, (20000.0 * nfft as f64 / crate::capture::SR) as usize);
            let (d, e) = (lo..=hi).fold((0.0, 0.0), |(d, e), i| (d + (sc[i].re - sm[i].re).powi(2) + (sc[i].im - sm[i].im).powi(2), e + sc[i].norm2()));
            res_band[o] = audio::db(d / e.max(1e-30));
            for (k, fc) in centres.iter().enumerate() {
                let (lo, hi) = ((fc / 1.12 * nfft as f64 / crate::capture::SR) as usize, (fc * 1.12 * nfft as f64 / crate::capture::SR) as usize);
                for i in lo..=hi.min(nfft / 2) {
                    ec[k] += sc[i].norm2();
                    em[k] += sm[i].norm2();
                }
            }
        }
        let tone_db: Vec<(f64, f64)> = centres.iter().enumerate().map(|(k, f)| (f.round(), 10.0 * (ec[k] / em[k].max(1e-30)).log10())).collect();
        rows.push(CheckRow { id: s.id.clone(), name: s.name.clone(), room: if s.placement.width > 0.0 { format!("{} [sections]", room.describe()) } else { room.describe() }, residual_db: (res[0], res[1]), residual_band_db: (res_band[0], res_band[1]), level_db: (lev[0], lev[1]), tone_db, air: s.placement.air });
    }
    Ok(rows)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn stage() -> Stage {
        let mic = |name: &str, x: f64, l: Option<f64>, r: Option<f64>| Mic { name: name.into(), position: [x, 0.0, 2.5], direction: [0.0, 1.0, 0.0], pattern: 0.0, left_db: l, right_db: r, delay_ms: 0.0 };
        Stage {
            space: Space {
                name: "test".into(),
                speed_of_sound: 343.0,
                distance_exponent: 1.0,
                level_db: 0.0,
                depth_delay: 0.0,
                depth_reference_m: 0.0,
                exact_delays: true,
                air_absorption: false,
                temperature_c: 20.0,
                humidity_pct: 50.0,
                room: None,
                reflections: None,
                mics: vec![mic("L", -1.0, Some(0.0), None), mic("C", 0.0, Some(-9.0), Some(-9.0)), mic("R", 1.0, None, Some(0.0))],
            },
            air: AirEq { shape_hz: vec![1000.0, 16000.0], shape_db: vec![0.0, -4.8], amount_air: vec![0.0, 10.0], amount: vec![0.0, 1.0], no_air_amount: 0.0 },
            players: vec![Player { name: "p".into(), position: [3.0, 6.0, 1.5], gain_db: 0.0, air: Some(0.0), brightness_db: 0.0, facing_deg: 0.0, width_m: 0.0, note: String::new() }],
        }
    }

    #[test]
    fn taps_follow_distance() {
        let s = stage();
        let t = s.taps(&s.players[0]);
        assert_eq!(t.len(), 4);
        let c = t.iter().find(|t| t.mic == "C").unwrap();
        let d = (9.0f64 + 36.0 + 1.0).sqrt();
        assert!((c.gain_db - (-20.0 * d.log10() - 9.0)).abs() < 1e-9);
        // the right mic is nearest: no delay; the left one later by the path difference
        let r = t.iter().find(|t| t.mic == "R").unwrap();
        assert_eq!(r.delay_ms, 0.0);
        let l = t.iter().find(|t| t.mic == "L").unwrap();
        let dl = (16.0f64 + 36.0 + 1.0).sqrt();
        let dr = (4.0f64 + 36.0 + 1.0).sqrt();
        assert!((l.delay_ms - (dl - dr) / 343.0 * 1000.0).abs() < 1e-9);
    }

    #[test]
    fn depth_delay_keeps_real_arrival() {
        let mut s = stage();
        s.space.depth_delay = 1.0;
        let t = s.taps(&s.players[0]);
        let dr = (4.0f64 + 36.0 + 1.0).sqrt();
        assert!((t.iter().find(|t| t.mic == "R").unwrap().delay_ms - dr / 343.0 * 1000.0).abs() < 1e-9);
    }

    #[test]
    fn render_puts_taps_with_their_gains() {
        let s = stage();
        let h = s.render(&s.players[0], 48000.0, 192, 4800);
        // flat EQ (air 0): the right output's first copy peaks at the latency with the R mic's gain
        let r = s.taps(&s.players[0]).into_iter().find(|t| t.mic == "R").unwrap();
        assert!((20.0 * h[1][192].abs().log10() - r.gain_db).abs() < 0.5, "{} vs {}", h[1][192], r.gain_db);
        assert!(h[1][..150].iter().all(|v| v.abs() < 1e-3));
    }

    /// Energy of `h` in the band around `f` (± a third of an octave), dB.
    fn band(h: &[f64], f: f64) -> f64 {
        let n = h.len().next_power_of_two() * 2;
        let sp = audio::spectrum(h, n);
        let (lo, hi) = ((f / 1.26 * n as f64 / 48000.0) as usize, (f * 1.26 * n as f64 / 48000.0) as usize);
        audio::db(sp[lo..=hi].iter().map(|c| c.norm2()).sum::<f64>())
    }

    #[test]
    fn wide_source_plays_each_input_from_its_end() {
        let mut s = stage();
        s.players[0].position = [0.0, 6.0, 1.5];
        s.players[0].width_m = 4.0;
        let t = s.taps(&s.players[0]);
        // the left input's copy reaches the left mic first, the right input's the right mic
        let first = |input: usize, mic: &str| t.iter().find(|x| x.input == input && x.mic == mic).unwrap().delay_ms;
        assert!(first(0, "L") < first(1, "L"));
        assert!(first(1, "R") < first(0, "R"));
        let ir = s.true_stereo(&s.players[0], 48000.0, 192, 2400);
        let e = |h: &[f64]| audio::energy(h);
        assert!(e(&ir[0]) > e(&ir[2]), "left input should be louder in the left output");
    }

    #[test]
    fn floor_reflection_arrives_on_time() {
        let mut s = stage();
        s.space.room = Some(Room { width_m: 30.0, length_m: 30.0, height_m: 12.0, front_m: -10.0, floor_db: Some(-3.0), ceiling_db: None, left_db: None, right_db: None, front_db: None, back_db: None });
        let t = s.taps(&s.players[0]);
        let fl = t.iter().find(|x| x.path == "floor" && x.mic == "R").unwrap();
        let dr = (4.0f64 + 36.0 + 1.0).sqrt(); // direct to R (nearest)
        let df = (4.0f64 + 36.0 + 16.0).sqrt(); // image at z −1.5 to R at z 2.5
        assert!((fl.delay_ms - (df - dr) / 343.0 * 1000.0).abs() < 1e-9);
        let direct = t.iter().find(|x| x.path == "direct" && x.mic == "R").unwrap();
        assert!((fl.gain_db - (direct.gain_db - 3.0 - 20.0 * (df / dr).log10())).abs() < 1e-9);
    }

    #[test]
    fn air_absorption_grows_with_distance() {
        // ISO 9613-1, 20 °C, 50 %: ≈ 0.1 dB/m at 8 kHz
        let a8 = absorption_db_per_m(8000.0, 20.0, 50.0);
        assert!((0.07..0.14).contains(&a8), "{a8}");
        let mut s = stage();
        s.space.air_absorption = true;
        let near = s.render(&s.players[0], 48000.0, 192, 4800);
        s.players[0].position = [3.0, 30.0, 1.5];
        let far = s.render(&s.players[0], 48000.0, 192, 4800);
        let tilt = |h: &[f64]| band(h, 12000.0) - band(h, 1000.0);
        assert!(tilt(&far[1]) < tilt(&near[1]) - 1.5, "far {} near {}", tilt(&far[1]), tilt(&near[1]));
    }

    #[test]
    fn brightness_lifts_the_top() {
        let mut s = stage();
        let flat = s.render(&s.players[0], 48000.0, 192, 4800);
        s.players[0].brightness_db = 6.0;
        let bright = s.render(&s.players[0], 48000.0, 192, 4800);
        let d16 = band(&bright[1], 16000.0) - band(&flat[1], 16000.0);
        let d1 = band(&bright[1], 1000.0) - band(&flat[1], 1000.0);
        // the band around 16 kHz averages a little above the 16 kHz point (the curve keeps rising)
        assert!((5.0..8.0).contains(&d16) && d1.abs() < 0.2, "{d16} {d1}");
    }

    #[test]
    fn sends_grow_toward_the_back() {
        let mut s = stage();
        s.space.reflections = Some(Sends { send_db: -12.0, per_m_db: 0.5, reference_m: 5.0 });
        let front = s.send_db(&s.players[0]).unwrap();
        s.players[0].position[1] += 10.0;
        assert!(s.send_db(&s.players[0]).unwrap() > front + 4.0);
    }

    #[test]
    fn starter_space_loads_and_keeps_tone() {
        let sf: SpaceFile = toml::from_str(&std::fs::read_to_string(Path::new(env!("CARGO_MANIFEST_DIR")).join("stages/film-stage-starter.toml")).unwrap()).unwrap();
        assert!(sf.space.room.is_some() && sf.space.mics.len() >= 5);
        let mut s = stage();
        s.air = sf.air.clone();
        s.players[0].air = Some(-100.0);
        let before = s.render(&s.players[0], 48000.0, 192, 4800);
        let mut moved = s.clone().into_space(&SpaceFile { space: s.space.clone(), air: s.air.clone() });
        assert_eq!(moved.players[0].air, None);
        let after = moved.render(&moved.players[0], 48000.0, 192, 4800);
        assert!(audio::residual_db(&before[1], &after[1]) < -60.0, "Air → brightness should keep the tone");
        moved.space = sf.space.clone();
        assert!(!moved.taps(&moved.players[0]).is_empty());
    }

    #[test]
    fn stage_file_round_trip() {
        let s = stage();
        let back: Stage = toml::from_str(&s.to_toml().unwrap()).unwrap();
        let (a, b) = (s.taps(&s.players[0]), back.taps(&back.players[0]));
        assert_eq!(a.len(), b.len());
        assert!(a.iter().zip(&b).all(|(x, y)| x.delay_ms == y.delay_ms && x.gain_db == y.gain_db));
    }

    #[test]
    fn compat_file_matches_the_measured_limits() {
        let c = Compat::read(&Compat::default_path()).unwrap();
        for (name, y, z) in vss2::MIC_LIMITS {
            let r = &c.rooms[name];
            assert_eq!(r.mic_max_front.map(|f| -f as f32), Some(y));
            assert_eq!(r.mic_max_height.map(|h| h as f32).unwrap_or(f32::MAX), z);
        }
    }
}
