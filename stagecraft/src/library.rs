//! E3: the capture library. Every VSS2 setting in use (all projects; settings that sound the
//! same, see [`vss2::sound_key`], are captured once) and the VSS2 preset library in chosen
//! rooms, captured as impulse responses with per-seat numbers ([`capture::Seat`]).
//!
//! Output (default `stagecraft/captures/library/`, git-ignored): one folder per setting, named
//! by its sound id, plus `library.json` (everything) and `library.md` (tables by room). A run
//! that stops can be restarted: settings already captured (same `state.bin`) are read back.

use crate::capture::{self, Capture, Rig, Source};
use crate::vss2;
use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

/// Where a setting is used: a project instance, or a preset file.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Use {
    /// Project file name without extension, or "preset" for the preset library.
    pub project: String,
    /// "Ob 1: Oboe 1, rack 22 SWAM Oboe 64bit, preset SWAM Oboe 1", or the preset's path below
    /// the preset folder.
    pub what: String,
    /// The pin name (instance name), or the preset's name.
    pub pin: String,
}

/// Placement settings as VSS2 shows them.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct Placement {
    pub x: f32,
    pub y: f32,
    pub z: f32,
    pub width: f32,
    pub facing: f32,
    pub er_level: Option<f64>,
    pub direct_level: Option<f64>,
    pub gain: Option<f64>,
    pub air: Option<f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Setting {
    /// [`vss2::sound_key`]; also the capture folder name.
    pub id: String,
    /// The most common pin name among its uses.
    pub name: String,
    pub room: Option<vss2::Room>,
    pub placement: Placement,
    pub uses: Vec<Use>,
    pub capture: Option<Capture>,
    #[serde(skip)]
    pub chunk: Vec<u8>,
}

impl Setting {
    pub fn room_name(&self) -> String {
        self.room.as_ref().map_or("no room".into(), vss2::Room::describe)
    }
}

/// `.vss2preset` files below `dir`, sorted.
pub fn preset_files(dir: &Path) -> Result<Vec<PathBuf>> {
    let mut out = vec![];
    let mut entries: Vec<_> = std::fs::read_dir(dir).with_context(|| format!("{}", dir.display()))?.flatten().map(|e| e.path()).collect();
    entries.sort();
    for p in entries {
        if p.is_dir() {
            out.extend(preset_files(&p)?);
        } else if p.extension().is_some_and(|e| e == "vss2preset") {
            out.push(p);
        }
    }
    Ok(out)
}

fn stem(p: &Path) -> String {
    p.file_stem().unwrap_or_default().to_string_lossy().into_owned()
}

struct Builder {
    by_id: BTreeMap<String, Setting>,
}

impl Builder {
    fn add(&mut self, chunk: Vec<u8>, u: Use) -> Result<()> {
        let id = vss2::sound_key(&chunk)?;
        let s = self.by_id.entry(id.clone()).or_insert_with(|| {
            let v = vss2::Vss2::from_props(vss2::parse_state(&chunk).unwrap_or_default());
            Setting {
                id,
                name: String::new(),
                room: vss2::room(&chunk),
                placement: Placement {
                    x: v.x,
                    y: v.y,
                    z: v.z,
                    width: v.width,
                    facing: v.facing,
                    er_level: v.er_level,
                    direct_level: v.direct_level,
                    gain: v.gain,
                    air: v.air,
                },
                uses: vec![],
                capture: None,
                chunk,
            }
        });
        s.uses.push(u);
        Ok(())
    }
}

/// Collects the settings of `projects` and of `presets` placed in the room of each project in
/// `preset_rooms`.
pub fn collect(projects: &[PathBuf], presets: &[PathBuf], preset_dir: Option<&Path>, preset_rooms: &[PathBuf]) -> Result<Vec<Setting>> {
    let mut b = Builder { by_id: BTreeMap::new() };
    for p in projects {
        let list = match capture::instances(p) {
            Ok(l) => l,
            Err(e) => {
                eprintln!("{}: {e:#}", p.display());
                continue;
            }
        };
        for i in list {
            let what = format!("{}: {}, {}, preset {}", i.pin, i.channel, if i.rack.is_empty() { "no rack" } else { &i.rack }, i.preset);
            b.add(i.chunk, Use { project: stem(p), what, pin: i.pin })?;
        }
    }
    for rp in preset_rooms {
        let room = capture::project_room(rp)?;
        for p in presets {
            let src = match capture::from_preset(p, &room) {
                Ok(s) => s,
                Err(e) => {
                    eprintln!("{}: {e:#}", p.display());
                    continue;
                }
            };
            let rel = preset_dir.and_then(|d| p.strip_prefix(d).ok()).unwrap_or(p);
            let what = format!("{} (in the room of {})", rel.with_extension("").display(), stem(rp));
            b.add(src.chunk, Use { project: "preset".into(), what, pin: stem(p) })?;
        }
    }
    let mut out: Vec<Setting> = b.by_id.into_values().collect();
    for s in out.iter_mut() {
        let mut n: BTreeMap<&str, usize> = BTreeMap::new();
        for u in &s.uses {
            *n.entry(u.pin.as_str()).or_default() += 1;
        }
        s.name = n.iter().max_by_key(|(k, c)| (**c, std::cmp::Reverse(**k))).map(|(k, _)| k.to_string()).unwrap_or_default();
    }
    Ok(out)
}

/// Captures every setting (or reads back an earlier capture of the same state) into
/// `out/<id>/`. Progress goes to stderr.
/// With `reanalyse`, earlier captures get their seat numbers recomputed ([`capture::reseat`]).
pub fn run(rig: &Rig, settings: &mut [Setting], out: &Path, reanalyse: bool) -> Result<()> {
    let n = settings.len();
    for (k, s) in settings.iter_mut().enumerate() {
        let d = out.join(&s.id);
        let old = std::fs::read(d.join("state.bin")).ok().filter(|b| *b == s.chunk).and_then(|_| std::fs::read_to_string(d.join("capture.json")).ok()).and_then(|j| serde_json::from_str::<Capture>(&j).ok());
        if let Some(c) = old {
            s.capture = Some(if reanalyse { capture::reseat(&d, &s.chunk)? } else { c });
            continue;
        }
        let t = std::time::Instant::now();
        let src = Source { name: s.name.clone(), from: s.uses.first().map_or(String::new(), |u| format!("{} / {}", u.project, u.what)), chunk: s.chunk.clone() };
        match capture::capture(rig, &src, &d, false) {
            Ok(c) => {
                s.capture = Some(c);
                eprintln!("[{}/{n}] {} ({}) {:.1} s", k + 1, s.name, s.id, t.elapsed().as_secs_f64());
            }
            Err(e) => eprintln!("[{}/{n}] {} ({}): {e:#}", k + 1, s.name, s.id),
        }
    }
    Ok(())
}

fn short(names: &[String], max: usize) -> String {
    let mut v: Vec<&String> = names.iter().collect();
    v.dedup();
    if v.len() <= max {
        v.iter().map(|s| s.as_str()).collect::<Vec<_>>().join(", ")
    } else {
        format!("{} + {} more", v[..max].iter().map(|s| s.as_str()).collect::<Vec<_>>().join(", "), v.len() - max)
    }
}

/// Tables by room: placement as set in VSS2 and as measured.
pub fn markdown(settings: &[Setting]) -> String {
    let mut rooms: BTreeMap<String, Vec<&Setting>> = BTreeMap::new();
    for s in settings {
        rooms.entry(s.room_name()).or_default().push(s);
    }
    let mut md = String::from(
        "# VSS2 capture library\n\nGenerated by `stagecraft library` (PLANNED_WORK.md §7, E3). One row per distinct sound\n\
         (settings differing only in name, colour, pin id or preset path are one row). Measured on a\n\
         mono source (same signal into both inputs):\n\n\
         - **Mic taps**: VSS2 simulates its main microphones: each output gets the direct sound\n  from its own capsule and from the centre capsule (Decca tree). Per output: capsule, ms after\n  VSS2's 4 ms latency, peak level in dB. **Fit**: largest difference between measured and\n  geometric (speed of sound) arrival, ms.\n\
         - **Level L / R**: direct sound (all its taps), 1 kHz octave, dB.\n\
         - **Tone**: direct sound at 4 / 8 / 16 kHz relative to 1 kHz (air absorption; a point source\n  with no air setting is ≈ 0).\n\
         - **Early / late**: reflection energy up to 80 ms / after 80 ms, relative to the direct sound\n  (1 kHz octave).\n\
         - **Reflections**: the strongest early reflections, ms after the direct sound and dB\n  relative to its peak.\n\n",
    );
    for (room, list) in &mut rooms {
        let mut projects: Vec<String> = list.iter().flat_map(|s| s.uses.iter().map(|u| u.project.clone())).collect();
        projects.sort();
        projects.dedup();
        md += &format!("## {room}\n\nUsed by: {}\n\n", projects.join(", "));
        md += "| Setting | Used | x / y (m) | Width | ER / Air | Mic taps L ‖ R (ms dB) | Fit | Level L / R (dB) | Tone 4k / 8k / 16k | Early / late | Reflections | Id |\n|---|---|---|---|---|---|---|---|---|---|---|---|\n";
        list.sort_by(|a, b| a.placement.y.total_cmp(&b.placement.y).then(a.placement.x.total_cmp(&b.placement.x)));
        for s in list.iter() {
            let p = &s.placement;
            let o = |x: Option<f64>| x.map_or("–".into(), |v| format!("{v}"));
            let mut proj: Vec<String> = s.uses.iter().map(|u| u.project.clone()).collect();
            proj.sort();
            let used = format!("{}× ({})", s.uses.len(), short(&proj, 2));
            let m = match &s.capture {
                Some(c) => {
                    let t = &c.seat;
                    let tone = |f: f64| t.direct_tone_db.iter().find(|(x, _)| *x == f).map_or("–".into(), |(_, v)| format!("{v:+.0}"));
                    let refl: Vec<String> = t.reflections.iter().take(3).map(|(ms, db, side)| format!("{ms:.1}{side} {db:.0}")).collect();
                    let taps = |side: char| t.taps.iter().filter(|x| x.output == side).map(|x| format!("{}{:.2} {:.0}", x.mic, (x.ms * 100.0).round() / 100.0 + 0.0, x.db)).collect::<Vec<_>>().join(", ");
                    let fit = t.taps.iter().filter_map(|x| x.predicted_ms.map(|p| (x.ms - p).abs())).fold(None, |m: Option<f64>, v| Some(m.map_or(v, |m| m.max(v))));
                    format!(
                        "{} ‖ {} | {} | {:.1} / {:.1} | {} / {} / {} | {:.0} / {:.0} dB | {} |",
                        taps('L'),
                        taps('R'),
                        fit.map_or("–".into(), |f| format!("{f:.2}")),
                        t.direct_db.0,
                        t.direct_db.1,
                        tone(4000.0),
                        tone(8000.0),
                        tone(16000.0),
                        t.early_db,
                        t.late_db,
                        refl.join(", ")
                    )
                }
                None => "not captured | | | | | |".into(),
            };
            md += &format!(
                "| {} | {used} | {:.1} / {:.1} | {} | {} / {} | {m} {} |\n",
                s.name,
                p.x,
                p.y,
                if p.width > 0.0 { format!("{:.1}", p.width) } else { "point".into() },
                o(p.er_level),
                o(p.air),
                s.id
            );
        }
        md.push('\n');
    }
    md
}
