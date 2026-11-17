//! `stagecraft` command line.
use anyhow::{Context, Result};
use clap::{Parser, Subcommand};
use std::path::PathBuf;

#[derive(Parser)]
#[command(name = "stagecraft", about = "Stage placement and audio-chain profiles (PLANNED_WORK.md §7)")]
struct Cli {
    #[command(subcommand)]
    cmd: Cmd,
}

#[derive(Subcommand)]
enum Cmd {
    /// Placement inventory of Dorico projects: mixer, inserts, sends, VSS2 and Altiverb settings
    Inventory {
        projects: Vec<PathBuf>,
        /// JSON instead of Markdown
        #[arg(long)]
        json: bool,
        /// One table row per project
        #[arg(long)]
        summary: bool,
    },
    /// Capture Virtual Sound Stage 2 settings as impulse responses (sweeps through vi-render)
    Capture {
        /// Dorico project: capture its VSS2 instances (all, or --pin)
        #[arg(long)]
        project: Option<PathBuf>,
        /// Only the instance with this pin name (e.g. "Cl 2")
        #[arg(long)]
        pin: Vec<String>,
        /// .vss2preset files to capture instead
        #[arg(long)]
        preset: Vec<PathBuf>,
        /// Project whose VSS2 room (microphone setup) presets are captured in (default --project)
        #[arg(long)]
        room_from: Option<PathBuf>,
        /// Output folder (default stagecraft/captures)
        #[arg(long)]
        out: Option<PathBuf>,
        /// Also run the repeat, level and null checks
        #[arg(long)]
        checks: bool,
    },
    /// Apply a captured true-stereo IR to a WAV (e.g. a dry stem), optionally comparing the
    /// result with a reference (e.g. the same stem exported with VSS2)
    Convolve {
        /// ir-true-stereo.wav from a capture
        #[arg(long)]
        ir: PathBuf,
        #[arg(long)]
        input: PathBuf,
        #[arg(long)]
        out: Option<PathBuf>,
        /// Reference to compare with (aligned automatically, ±50 ms)
        #[arg(long)]
        compare: Option<PathBuf>,
        /// Only use this many seconds, starting at --start (for quick comparisons)
        #[arg(long)]
        seconds: Option<f64>,
        #[arg(long, default_value_t = 0.0)]
        start: f64,
    },
    /// Blind A/B listening files: stems through VSS2 vs through captured IRs
    Ab {
        /// CAPTURE_DIR=STEM.wav, repeatable (the stems are mixed)
        #[arg(long = "pair")]
        pairs: Vec<String>,
        #[arg(long, default_value_t = 0.0)]
        start: f64,
        #[arg(long, default_value_t = 30.0)]
        seconds: f64,
        #[arg(long)]
        out: PathBuf,
    },
    /// E3: capture every VSS2 setting in use (identical sounds once) and, optionally, the
    /// preset library in chosen rooms; writes library.json and library.md
    Library {
        /// Dorico projects
        projects: Vec<PathBuf>,
        /// Preset folder (searched recursively)
        #[arg(long)]
        presets: Option<PathBuf>,
        /// Project whose VSS2 room the presets are captured in (repeatable)
        #[arg(long = "preset-room")]
        preset_rooms: Vec<PathBuf>,
        /// Output folder (default stagecraft/captures/library)
        #[arg(long)]
        out: Option<PathBuf>,
        /// List what would be captured, capture nothing
        #[arg(long)]
        dry_run: bool,
        /// Recompute the seat numbers of earlier captures from their saved IRs
        #[arg(long)]
        reanalyse: bool,
    },
    /// How VSS2's reflections move over time: a click train through one setting
    Motion {
        /// A capture folder (uses its state.bin)
        capture: PathBuf,
        #[arg(long, default_value_t = 32.0)]
        seconds: f64,
        /// Seconds between clicks (longer than the reflections)
        #[arg(long, default_value_t = 0.5)]
        every: f64,
    },
    /// Stage files (stagecraft's placement engine): make one from a project's VSS2 setup,
    /// check the VSS2-compatible model against the captures, render seats as IRs
    Stage {
        #[command(subcommand)]
        cmd: StageCmd,
    },
    /// The stage editor: a local web page for a stage file (drag players and mics, change any
    /// setting, audition dry stems)
    Serve {
        stage: PathBuf,
        #[arg(long, default_value_t = 8417)]
        port: u16,
    },
    /// Table of Virtual Sound Stage 2 preset files (searched recursively)
    Presets {
        dir: PathBuf,
        #[arg(long)]
        json: bool,
    },
}

#[derive(Subcommand)]
enum StageCmd {
    /// Write a VSS2-compatible stage file (TOML) for a project's VSS2 instances
    FromProject {
        project: PathBuf,
        #[arg(long)]
        out: Option<PathBuf>,
        /// Keep the project's seating but use this space instead of VSS2's (a [space] + [air]
        /// file, e.g. stagecraft/stages/film-stage-starter.toml)
        #[arg(long)]
        space: Option<PathBuf>,
    },
    /// Compare VSS2-compatible stages with every captured setting in the library
    Check {
        /// Library folder (default stagecraft/captures/library)
        #[arg(long)]
        library: Option<PathBuf>,
    },
    /// Render each player of a stage file: ir-true-stereo.wav (direct sound) + taps.json
    Render {
        stage: PathBuf,
        #[arg(long)]
        out: PathBuf,
        /// Samples of latency to place the taps at (VSS2: 192)
        #[arg(long, default_value_t = 192)]
        latency: usize,
    },
}

fn presets(dir: &std::path::Path, out: &mut Vec<(String, stagecraft::vss2::Preset)>) -> Result<()> {
    for p in stagecraft::library::preset_files(dir)? {
        match stagecraft::vss2::read_preset(&p) {
            Ok(pr) => out.push((p.to_string_lossy().into_owned(), pr)),
            Err(e) => eprintln!("{}: {e:#}", p.display()),
        }
    }
    Ok(())
}

fn main() -> Result<()> {
    match Cli::parse().cmd {
        Cmd::Inventory { projects, json, summary } => {
            let mut all = vec![];
            if summary {
                println!("{}", stagecraft::inventory::summary_header());
            }
            for p in &projects {
                match stagecraft::inventory::inventory(p) {
                    Ok(inv) if json => all.push(inv),
                    Ok(inv) if summary => println!("{}", stagecraft::inventory::summary_row(&inv)),
                    Ok(inv) => println!("{}", stagecraft::inventory::markdown(&inv)),
                    Err(e) => eprintln!("{}: {e:#}", p.display()),
                }
            }
            if json {
                println!("{}", serde_json::to_string_pretty(&all)?);
            }
        }
        Cmd::Capture { project, pin, preset, room_from, out, checks } => {
            use stagecraft::capture;
            let repo = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..");
            let out = out.unwrap_or_else(|| repo.join("stagecraft/captures"));
            let rig = capture::Rig::find(&repo)?;
            let mut sources = vec![];
            if let Some(p) = &project {
                if pin.is_empty() {
                    sources.extend(capture::from_project(p, None)?);
                }
                for n in &pin {
                    sources.extend(capture::from_project(p, Some(n))?);
                }
            }
            if !preset.is_empty() {
                let rp = room_from.as_ref().or(project.as_ref()).context("presets need --room-from PROJECT (or --project): VSS2's microphone setup lives in the project")?;
                let room = capture::project_room(rp)?;
                for p in &preset {
                    sources.push(capture::from_preset(p, &room)?);
                }
            }
            if sources.is_empty() {
                anyhow::bail!("nothing to capture: give --project and/or --preset");
            }
            println!("{}", capture::table_header());
            for s in &sources {
                match capture::capture(&rig, s, &capture::folder(&out, &s.name), checks) {
                    Ok(c) => println!("{}", capture::table_row(&c)),
                    Err(e) => eprintln!("{}: {e:#}", s.name),
                }
            }
        }
        Cmd::Convolve { ir, input, out, compare, seconds, start } => {
            use stagecraft::audio;
            let (_, h) = audio::read_wav(&ir)?;
            anyhow::ensure!(h.len() == 4, "{} is not a 4-channel true-stereo IR", ir.display());
            let cut = |x: Vec<Vec<f64>>, sr: u32| -> Vec<Vec<f64>> {
                let a = (start * sr as f64) as usize;
                let b = seconds.map_or(usize::MAX, |s| a + (s * sr as f64) as usize);
                x.into_iter().map(|c| c[a.min(c.len())..b.min(c.len())].to_vec()).collect()
            };
            let (sr, x) = audio::read_wav(&input)?;
            let x = cut(x, sr);
            let y = audio::apply_true_stereo(&x, &h);
            if let Some(o) = &out {
                audio::write_wav(o, &y, sr)?;
            }
            if let Some(r) = &compare {
                let (_, rf) = audio::read_wav(r)?;
                let rf = cut(rf, sr);
                let mono = |c: &Vec<Vec<f64>>| -> Vec<f64> { (0..c[0].len()).map(|i| c.iter().map(|ch| ch[i]).sum::<f64>()).collect() };
                let lag = audio::best_lag(&mono(&y), &mono(&rf), (0.05 * sr as f64) as usize);
                println!("reference is {lag} samples ({:+.2} ms) later than the convolution", lag as f64 / sr as f64 * 1000.0);
                let name = ["L", "R"];
                for ch in 0..2 {
                    let (a, b): (Vec<f64>, Vec<f64>) = if lag >= 0 {
                        (rf[ch][lag as usize..].to_vec(), y[ch].clone())
                    } else {
                        (rf[ch].clone(), y[ch][(-lag) as usize..].to_vec())
                    };
                    let n = a.len().min(b.len());
                    let (a, b) = (&a[..n], &b[..n]);
                    let diff: Vec<f64> = a.iter().zip(b).map(|(p, q)| p - q).collect();
                    let (bd, br) = (audio::octave_bands(&diff, sr as f64), audio::octave_bands(a, sr as f64));
                    println!(
                        "{}: level conv − ref {:+.2} dB; residual {:.1} dB; by octave {}",
                        name[ch],
                        audio::db(audio::energy(b) / audio::energy(a).max(1e-30)),
                        audio::residual_db(a, b),
                        bd.iter().zip(&br).map(|((f, d), (_, r))| format!("{}:{:.0}", *f as u32, d - r)).collect::<Vec<_>>().join(" ")
                    );
                }
                let (dl, dr) = (audio::residual_db(&rf[0], &x[0]), audio::residual_db(&rf[1], &x[1]));
                println!("(for scale: reference vs the unprocessed input: residual {dl:.1} / {dr:.1} dB)");
                // tone and image, which don't need sample-identical renders
                let tone = |c: &Vec<Vec<f64>>| audio::octave_bands(&mono(c), sr as f64);
                let (tc, tr) = (tone(&y), tone(&rf));
                println!(
                    "tone, conv − ref per octave (dB): {}",
                    tc.iter().zip(&tr).map(|((f, a), (_, b))| format!("{}:{:+.1}", *f as u32, a - b)).collect::<Vec<_>>().join(" ")
                );
                let image = |c: &Vec<Vec<f64>>| {
                    let lag = audio::best_lag(&c[0], &c[1], (0.002 * sr as f64) as usize);
                    (audio::db(audio::energy(&c[0]) / audio::energy(&c[1]).max(1e-30)), lag as f64 / sr as f64 * 1000.0)
                };
                let ((lc, tcd), (lr_, trd), (li, tid)) = (image(&y), image(&rf), image(&x));
                println!("image L−R level / right later by: conv {lc:+.1} dB / {tcd:+.2} ms; ref {lr_:+.1} dB / {trd:+.2} ms; input {li:+.1} dB / {tid:+.2} ms");
            }
        }
        Cmd::Ab { pairs, start, seconds, out } => {
            let repo = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..");
            let rig = stagecraft::capture::Rig::find(&repo)?;
            let pairs: Vec<(PathBuf, PathBuf)> = pairs
                .iter()
                .map(|p| p.split_once('=').map(|(a, b)| (PathBuf::from(a), PathBuf::from(b))).context("--pair wants CAPTURE_DIR=STEM.wav"))
                .collect::<Result<_>>()?;
            println!("{}", stagecraft::capture::ab(&rig, &pairs, start, seconds, &out)?);
        }
        Cmd::Library { projects, presets, preset_rooms, out, dry_run, reanalyse } => {
            use stagecraft::library;
            let repo = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..");
            let out = out.unwrap_or_else(|| repo.join("stagecraft/captures/library"));
            let files = match &presets {
                Some(d) => library::preset_files(d)?,
                None => vec![],
            };
            anyhow::ensure!(files.is_empty() || !preset_rooms.is_empty(), "--presets needs --preset-room PROJECT: VSS2's microphone setup lives in the project");
            let mut set = library::collect(&projects, &files, presets.as_deref(), &preset_rooms)?;
            let uses: usize = set.iter().map(|s| s.uses.len()).sum();
            let mut rooms: Vec<String> = set.iter().map(|s| s.room_name()).collect();
            rooms.sort();
            rooms.dedup();
            eprintln!("{uses} instances/presets -> {} distinct settings in {} rooms", set.len(), rooms.len());
            if dry_run {
                for r in &rooms {
                    println!("{r}: {} settings", set.iter().filter(|s| &s.room_name() == r).count());
                }
                return Ok(());
            }
            std::fs::create_dir_all(&out)?;
            let rig = stagecraft::capture::Rig::find(&repo)?;
            library::run(&rig, &mut set, &out, reanalyse)?;
            std::fs::write(out.join("library.json"), serde_json::to_string_pretty(&set)?)?;
            std::fs::write(out.join("library.md"), library::markdown(&set))?;
            println!("{} settings; index in {}", set.len(), out.join("library.md").display());
        }
        Cmd::Motion { capture, seconds, every } => {
            let repo = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..");
            let rig = stagecraft::capture::Rig::find(&repo)?;
            let m = stagecraft::motion::motion(&rig, &capture.join("state.bin"), &capture.join("motion"), seconds, every)?;
            std::fs::write(capture.join("motion/motion.json"), serde_json::to_string_pretty(&m)?)?;
            println!("{} clicks, one every {} s. Direct sound click to click: worst residual {:.0} dB", m.clicks, m.every_s, m.direct_residual_db);
            println!("reflections: energy click to click ±{:.2} dB; second load vs first: correlation {:.2}", m.energy_sd_db, m.between_loads);
            println!("| Gap (s) | Correlation | Residual (dB) |\n|---|---|---|");
            for (g, c, r) in &m.by_gap {
                println!("| {g} | {c:.2} | {r:.1} |");
            }
            let b = |v: &Vec<(f64, f64)>| v.iter().map(|(f, c)| format!("{}:{:.2}", *f as u32, c)).collect::<Vec<_>>().join(" ");
            println!("by octave, gap {} s: {}", m.every_s, b(&m.by_band));
            println!("by octave, longest gap: {}", b(&m.by_band_long));
            for t in &m.tones {
                println!(
                    "steady {} Hz: wobble {:.0} dB re the steady part, level moves {:.2} dB peak to peak; strongest rates {}",
                    t.hz,
                    t.wobble_db,
                    t.level_pp_db,
                    t.rates.iter().map(|(r, d)| format!("{r:.2} Hz ({d:.0} dB)")).collect::<Vec<_>>().join(", ")
                );
            }
        }
        Cmd::Stage { cmd } => {
            use stagecraft::stage::{self, Compat, Stage};
            let compat = Compat::read(&Compat::default_path())?;
            match cmd {
                StageCmd::FromProject { project, out, space } => {
                    let states: Vec<Vec<u8>> = stagecraft::capture::instances(&project)?.into_iter().map(|i| i.chunk).collect();
                    let mut st = Stage::from_vss2(&compat, &states)?;
                    let what = match &space {
                        Some(f) => {
                            let sf: stage::SpaceFile = toml::from_str(&std::fs::read_to_string(f)?).with_context(|| format!("{}", f.display()))?;
                            st = st.into_space(&sf);
                            format!("seating from VSS2, space from {}", f.display())
                        }
                        None => "VSS2-compatible".to_string(),
                    };
                    let text = format!("# Stage made by `stagecraft stage from-project` from {}\n# {what}: change anything (see stagecraft/docs/STAGES.md)\n\n{}", project.display(), st.to_toml()?);
                    match out {
                        Some(o) => std::fs::write(&o, text)?,
                        None => print!("{text}"),
                    }
                }
                StageCmd::Check { library } => {
                    let repo = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..");
                    let lib = library.unwrap_or_else(|| repo.join("stagecraft/captures/library"));
                    let rows = stage::check(&compat, &lib)?;
                    let mut by: std::collections::BTreeMap<String, Vec<&stage::CheckRow>> = Default::default();
                    for r in &rows {
                        by.entry(r.room.clone()).or_default().push(r);
                    }
                    println!("| Room | Settings | Residual 200 Hz–20 kHz median / worst (dB) | Level 1 kHz median / worst (dB) | Worst |\n|---|---|---|---|---|");
                    for (room, v) in &by {
                        let mut res: Vec<f64> = v.iter().map(|r| r.residual_band_db.0.max(r.residual_band_db.1)).collect();
                        let mut lev: Vec<f64> = v.iter().map(|r| r.level_db.0.abs().max(r.level_db.1.abs())).collect();
                        res.sort_by(f64::total_cmp);
                        lev.sort_by(f64::total_cmp);
                        let w = v.iter().max_by(|a, b| a.residual_band_db.0.max(a.residual_band_db.1).total_cmp(&b.residual_band_db.0.max(b.residual_band_db.1))).unwrap();
                        println!("| {room} | {} | {:.0} / {:.0} | {:.2} / {:.2} | {} ({}) |", v.len(), res[res.len() / 2], res[res.len() - 1], lev[lev.len() / 2], lev[lev.len() - 1], w.name, w.id);
                    }
                    std::fs::write(lib.join("stage-check.json"), serde_json::to_string_pretty(&rows)?)?;
                }
                StageCmd::Render { stage: path, out, latency } => {
                    let st = Stage::read(&path)?;
                    std::fs::create_dir_all(&out)?;
                    for p in &st.players {
                        let d = stagecraft::capture::folder(&out, &p.name);
                        std::fs::create_dir_all(&d)?;
                        let ir = st.true_stereo(p, stagecraft::capture::SR, latency, (0.05 * stagecraft::capture::SR) as usize + latency);
                        stagecraft::audio::write_wav(&d.join("ir-true-stereo.wav"), &ir, stagecraft::capture::SR as u32)?;
                        std::fs::write(d.join("taps.json"), serde_json::to_string_pretty(&st.taps(p))?)?;
                    }
                    println!("{} players rendered into {}", st.players.len(), out.display());
                }
            }
        }
        Cmd::Serve { stage, port } => stagecraft::serve::serve(&stage, port)?,
        Cmd::Presets { dir, json } => {
            let mut out = vec![];
            presets(&dir, &mut out)?;
            if json {
                let rows: Vec<_> = out.iter().map(|(path, p)| serde_json::json!({ "path": path, "preset": p })).collect();
                println!("{}", serde_json::to_string_pretty(&rows)?);
                return Ok(());
            }
            let base = dir.to_string_lossy().into_owned();
            println!("| Folder | Preset | Instrument | Library | Mic | x | y | Width | Facing | ER | Direct | Gain | Air |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|");
            for (path, p) in &out {
                let rel = path.strip_prefix(&base).unwrap_or(path).trim_start_matches('/');
                let (folder, file) = rel.rsplit_once('/').unwrap_or(("", rel));
                let v = &p.vss;
                let o = |x: Option<f64>| x.map_or("–".into(), |x| format!("{x}"));
                println!(
                    "| {folder} | {} | {} | {} | {} | {:.2} | {:.2} | {} | {:.0}° | {} | {} | {} | {} |",
                    file.trim_end_matches(".vss2preset"), p.instrument, p.library, p.mic_position, v.x, v.y,
                    if v.emitters > 1 { format!("{:.2}", v.width) } else { "point".into() }, v.facing,
                    o(v.er_level), o(v.direct_level), o(v.gain), o(v.air)
                );
            }
        }
    }
    Ok(())
}
