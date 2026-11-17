//! vi-render: a headless VST2 host for measuring virtual instruments (Project C,
//! PLANNED_WORK.md §5). Windows build; run from WSL through interop. Paths are Windows paths.
//!
//!   vi-render info   --plugin X.dll [--state S] [--set i=v ...]          parameters as JSON
//!   vi-render state  --plugin X.dll [--state S] --out F [--bank]        save the plug-in's chunk
//!   vi-render sweep  --plugin X.dll [--state S] --param i [--steps n]  display text across 0..1
//!   vi-render render --plugin X.dll [--state S] [--set i=v ...] [--events E.json] [--input I.wav] --out W.wav
//!
//! `--state` is a chunk to load first (for SWAM: the `<swam ...>` XML Dorico stores in a
//! project's enginedata). Events JSON: {"length": seconds?, "events": [{"t": seconds,
//! "midi": [status, d1, d2]}, ...]}. Output: 32-bit float WAV, all plug-in outputs.
//! `--input` (effects): a WAV (PCM 16/24/32-bit or float, at --sample-rate) fed into the plug-in's
//! inputs, file channel n -> input n (a mono file goes to every input); the render lasts the
//! input plus --tail. The plug-in's reported latency (initialDelay) is printed, not removed.

mod vst2;

use std::fs;
use std::io::Write;

use anyhow::{bail, Context, Result};
use clap::{Parser, Subcommand};
use serde::Deserialize;

#[derive(Parser)]
#[command(about = "Headless VST2 host: render MIDI through a virtual instrument, inspect its parameters")]
struct Cli {
    #[command(subcommand)]
    cmd: Cmd,
}

#[derive(clap::Args)]
struct Common {
    /// Plug-in DLL (Windows path)
    #[arg(long)]
    plugin: String,
    /// State chunk to load before anything else
    #[arg(long)]
    state: Option<String>,
    /// Load --state as a bank chunk instead of a program chunk
    #[arg(long)]
    bank: bool,
    /// Set parameters after loading the state: index=value (0..1), repeatable
    #[arg(long = "set")]
    set: Vec<String>,
    #[arg(long, default_value_t = 48000.0)]
    sample_rate: f64,
    #[arg(long, default_value_t = 128)]
    block: usize,
    /// Milliseconds to wait (running the message loop) after loading, before rendering
    #[arg(long, default_value_t = 3000)]
    warmup: u64,
    /// Tell the plug-in it runs in realtime (some plug-ins behave differently offline)
    #[arg(long)]
    realtime: bool,
    /// Open the plug-in's editor (hidden window) for this many ms after loading; some plug-ins
    /// only finish initialising when their editor has been open
    #[arg(long, default_value_t = 0)]
    editor: u64,
    /// Show the editor window instead of hiding it (with --editor)
    #[arg(long)]
    show_editor: bool,
    /// Save a screenshot (BMP) of the editor before closing it (with --editor)
    #[arg(long)]
    editor_shot: Option<String>,
    /// Pace rendering at real speed (sleep one block's duration per block)
    #[arg(long)]
    paced: bool,
}

#[derive(Subcommand)]
enum Cmd {
    Info {
        #[command(flatten)]
        c: Common,
    },
    State {
        #[command(flatten)]
        c: Common,
        #[arg(long)]
        out: String,
    },
    Sweep {
        #[command(flatten)]
        c: Common,
        #[arg(long)]
        param: i32,
        #[arg(long, default_value_t = 100)]
        steps: usize,
    },
    Render {
        #[command(flatten)]
        c: Common,
        /// MIDI events (JSON); optional for effects
        #[arg(long)]
        events: Option<String>,
        /// Audio fed into the plug-in's inputs (WAV)
        #[arg(long)]
        input: Option<String>,
        #[arg(long)]
        out: String,
        /// Seconds rendered after the last event / the end of --input
        #[arg(long, default_value_t = 2.0)]
        tail: f64,
        /// Write the parameters as they were at the start of the render (JSON)
        #[arg(long)]
        params_out: Option<String>,
    },
}

#[derive(Deserialize)]
struct Event {
    t: f64,
    midi: Vec<u8>,
}

#[derive(Deserialize)]
struct Events {
    length: Option<f64>,
    events: Vec<Event>,
}

fn open(c: &Common) -> Result<vst2::Plugin> {
    *vst2::PROCESS_LEVEL.lock().unwrap() = if c.realtime { 2 } else { 4 };
    let mut p = vst2::Plugin::load(&c.plugin, c.sample_rate, c.block)?;
    if let Some(s) = &c.state {
        let data = fs::read(s).with_context(|| format!("reading state {s}"))?;
        let r = p.set_chunk(!c.bank, &data);
        eprintln!("state: {} bytes loaded (setChunk returned {r})", data.len());
        p.idle(300);
    }
    if c.editor > 0 {
        let hwnd = vst2::make_window(c.show_editor);
        let r = p.open_editor(hwnd, c.editor, c.editor_shot.as_deref());
        eprintln!("editor opened in window {hwnd:#x} (effEditOpen returned {r})");
    }
    for s in &c.set {
        let (i, v) = s.split_once('=').context("--set wants index=value")?;
        p.set_param(i.trim().parse()?, v.trim().parse()?);
    }
    Ok(p)
}

fn params_json(p: &mut vst2::Plugin) -> serde_json::Value {
    // Some plug-ins (SWAM) only refresh a parameter's display text when it is set, not when a
    // state chunk is loaded: set every parameter to its own value first.
    for i in 0..p.num_params() {
        let v = p.get_param(i);
        p.set_param(i, v);
    }
    let ps: Vec<_> = p
        .params()
        .into_iter()
        .map(|x| serde_json::json!({"index": x.index, "name": x.name, "label": x.label,
                                    "display": x.display, "value": x.value}))
        .collect();
    serde_json::json!({"info": p.info(), "params": ps})
}

fn write_wav(path: &str, chans: &[Vec<f32>], sr: u32) -> Result<()> {
    let n = chans.first().map_or(0, |c| c.len());
    let nc = chans.len() as u16;
    let data_len = (n * chans.len() * 4) as u32;
    let mut f = std::io::BufWriter::new(fs::File::create(path).with_context(|| format!("creating {path}"))?);
    f.write_all(b"RIFF")?;
    f.write_all(&(36 + data_len).to_le_bytes())?;
    f.write_all(b"WAVEfmt ")?;
    f.write_all(&16u32.to_le_bytes())?;
    f.write_all(&3u16.to_le_bytes())?; // IEEE float
    f.write_all(&nc.to_le_bytes())?;
    f.write_all(&sr.to_le_bytes())?;
    f.write_all(&(sr * nc as u32 * 4).to_le_bytes())?;
    f.write_all(&(nc * 4).to_le_bytes())?;
    f.write_all(&32u16.to_le_bytes())?;
    f.write_all(b"data")?;
    f.write_all(&data_len.to_le_bytes())?;
    for i in 0..n {
        for c in chans {
            f.write_all(&c[i].to_le_bytes())?;
        }
    }
    Ok(())
}

/// A WAV file as one Vec<f32> per channel (PCM 16/24/32-bit or 32-bit float).
fn read_wav(path: &str) -> Result<(u32, Vec<Vec<f32>>)> {
    let b = fs::read(path).with_context(|| format!("reading {path}"))?;
    if b.len() < 12 || &b[..4] != b"RIFF" || &b[8..12] != b"WAVE" {
        bail!("{path}: not a WAV file");
    }
    let u16_at = |p: usize| u16::from_le_bytes([b[p], b[p + 1]]);
    let u32_at = |p: usize| u32::from_le_bytes([b[p], b[p + 1], b[p + 2], b[p + 3]]);
    let (mut fmt, mut data) = (None, None);
    let mut p = 12;
    while p + 8 <= b.len() {
        let (id, len) = (&b[p..p + 4], u32_at(p + 4) as usize);
        let body = p + 8..(p + 8 + len).min(b.len());
        if id == b"fmt " {
            fmt = Some(body.clone());
        } else if id == b"data" {
            data = Some(body.clone());
        }
        p += 8 + len + (len & 1);
    }
    let (f, d) = (fmt.context("no fmt chunk")?, data.context("no data chunk")?);
    let mut format = u16_at(f.start);
    let (nc, sr, bits) = (u16_at(f.start + 2) as usize, u32_at(f.start + 4), u16_at(f.start + 14));
    if format == 0xFFFE && f.len() >= 26 {
        format = u16_at(f.start + 24); // WAVE_FORMAT_EXTENSIBLE: sub-format
    }
    let width = bits as usize / 8;
    if nc == 0 || !matches!((format, bits), (1, 16) | (1, 24) | (1, 32) | (3, 32)) {
        bail!("{path}: unsupported WAV format {format}, {bits} bits");
    }
    let frames = d.len() / (width * nc);
    let mut out = vec![Vec::with_capacity(frames); nc];
    for i in 0..frames {
        for (ch, o) in out.iter_mut().enumerate() {
            let q = d.start + (i * nc + ch) * width;
            o.push(match (format, bits) {
                (3, _) => f32::from_le_bytes([b[q], b[q + 1], b[q + 2], b[q + 3]]),
                (_, 16) => i16::from_le_bytes([b[q], b[q + 1]]) as f32 / 32768.0,
                (_, 24) => (i32::from_le_bytes([0, b[q], b[q + 1], b[q + 2]]) >> 8) as f32 / 8_388_608.0,
                _ => i32::from_le_bytes([b[q], b[q + 1], b[q + 2], b[q + 3]]) as f32 / 2_147_483_648.0,
            });
        }
    }
    Ok((sr, out))
}

fn render(c: &Common, events: Option<&str>, input: Option<&str>, out: &str, tail: f64, params_out: Option<&String>) -> Result<()> {
    let ev: Events = match events {
        Some(e) => serde_json::from_str(&fs::read_to_string(e).with_context(|| format!("reading {e}"))?)?,
        None => Events { length: None, events: vec![] },
    };
    let audio = match input {
        Some(path) => {
            let (sr, chans) = read_wav(path)?;
            if sr as f64 != c.sample_rate {
                bail!("{path} is {sr} Hz; render runs at {} Hz (--sample-rate)", c.sample_rate);
            }
            Some(chans)
        }
        None => None,
    };
    if events.is_none() && audio.is_none() {
        bail!("render needs --events and/or --input");
    }
    let input_secs = audio.as_ref().map_or(0.0, |a| a[0].len() as f64 / c.sample_rate);
    let mut list: Vec<(usize, [u8; 3])> = Vec::new();
    for e in &ev.events {
        if e.midi.is_empty() || e.midi.len() > 3 {
            bail!("event at {} s: midi must have 1-3 bytes", e.t);
        }
        let mut b = [0u8; 3];
        b[..e.midi.len()].copy_from_slice(&e.midi);
        list.push(((e.t.max(0.0) * c.sample_rate).round() as usize, b));
    }
    list.sort_by_key(|x| x.0); // stable: same-time events keep file order
    let last = list.last().map_or(0.0, |x| x.0 as f64 / c.sample_rate);
    let secs = ev.length.unwrap_or(0.0).max(last + tail).max(if audio.is_some() { input_secs + tail } else { 0.0 });
    let total = (secs * c.sample_rate).ceil() as usize;

    let mut p = open(c)?;
    if let Some(po) = params_out {
        fs::write(po, serde_json::to_string_pretty(&params_json(&mut p))?)?;
    }
    let (ni, no) = p.io();
    if no == 0 {
        bail!("plug-in has no audio outputs");
    }
    p.resume();
    p.idle(c.warmup);
    let mut inputs = vec![vec![0f32; c.block]; ni];
    let mut block = vec![vec![0f32; c.block]; no];
    let mut outs: Vec<Vec<f32>> = vec![Vec::with_capacity(total); no];
    let mut k = 0;
    let mut pos = 0;
    while pos < total {
        let n = c.block.min(total - pos);
        let mut now = Vec::new();
        while k < list.len() && list[k].0 < pos + n {
            now.push((list[k].0.saturating_sub(pos), list[k].1));
            k += 1;
        }
        p.send_midi(&now);
        for b in block.iter_mut() {
            b.iter_mut().for_each(|x| *x = 0.0);
        }
        if let Some(a) = &audio {
            for (i, inp) in inputs.iter_mut().enumerate() {
                let src = if a.len() == 1 { &a[0] } else { a.get(i).unwrap_or(&a[0]) };
                let silent = a.len() > 1 && i >= a.len();
                for (j, x) in inp.iter_mut().enumerate() {
                    *x = if silent { 0.0 } else { src.get(pos + j).copied().unwrap_or(0.0) };
                }
            }
        }
        p.process(&inputs, &mut block, n, pos as f64)?;
        for (o, b) in outs.iter_mut().zip(&block) {
            o.extend_from_slice(&b[..n]);
        }
        pos += n;
        if c.paced {
            std::thread::sleep(std::time::Duration::from_secs_f64(n as f64 / c.sample_rate));
        }
        if (pos / c.block) % 64 == 0 {
            vst2::pump(0);
        }
    }
    if std::env::var_os("VI_RENDER_DEBUG").is_some() {
        let n = p.num_params();
        let shown: Vec<String> = (0..n.min(12)).map(|i| format!("{i}={:.3}", p.get_param(i))).collect();
        eprintln!("after render: flags {:#x}; params {}", p.flags(), shown.join(" "));
    }
    p.suspend();
    write_wav(out, &outs, c.sample_rate as u32)?;
    let peak = outs.iter().flatten().fold(0f32, |m, x| m.max(x.abs()));
    eprintln!("rendered {secs:.2} s, {} events, {no} channels, peak {:.1} dBFS -> {out}",
              list.len(), 20.0 * (peak.max(1e-9)).log10());
    if audio.is_some() {
        eprintln!("input: {input_secs:.2} s into {ni} inputs; plug-in latency {} samples (not removed)",
                  p.info()["initial_delay_samples"]);
    }
    Ok(())
}

fn main() -> Result<()> {
    match Cli::parse().cmd {
        Cmd::Info { c } => {
            let mut p = open(&c)?;
            println!("{}", serde_json::to_string_pretty(&params_json(&mut p))?);
        }
        Cmd::State { c, out } => {
            let mut p = open(&c)?;
            let data = p.get_chunk(!c.bank);
            fs::write(&out, &data)?;
            eprintln!("{} bytes -> {out}", data.len());
        }
        Cmd::Sweep { c, param, steps } => {
            let mut p = open(&c)?;
            let before = p.get_param(param);
            let mut last = String::new();
            for i in 0..=steps {
                let v = i as f32 / steps as f32;
                p.set_param(param, v);
                let d = p.param_display(param);
                if d != last {
                    println!("{v:.4}\t{d}");
                    last = d;
                }
            }
            p.set_param(param, before);
        }
        Cmd::Render { c, events, input, out, tail, params_out } => {
            render(&c, events.as_deref(), input.as_deref(), &out, tail, params_out.as_ref())?
        }
    }
    Ok(())
}
