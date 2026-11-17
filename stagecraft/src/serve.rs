//! `stagecraft serve`: the stage editor. A local web page (`editor/index.html`, built into the
//! binary) over a small JSON interface to the stage engine. The calls are the ones the
//! Playback app (PLANNED_WORK §2.11) will make as Tauri commands later:
//!
//! | Call | What |
//! |---|---|
//! | `GET /` | the editor page |
//! | `GET /api/stage` | `{file, stage, placements}` |
//! | `POST /api/stage` (stage JSON) | replace the stage being edited (not saved); returns `placements` |
//! | `POST /api/save` | write the stage to its file (TOML) |
//! | `GET /api/ir/<player>` | that player's true-stereo IR: 4 × n little-endian f32 (LL, LR, RL, RR), 48 kHz, `LATENCY` samples in |
//!
//! Local only (127.0.0.1); one request at a time.

use crate::stage::{Placement, Stage};
use anyhow::{Context, Result, bail};
use std::io::{BufRead, BufReader, Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::{Path, PathBuf};

const PAGE: &str = include_str!("../editor/index.html");
/// Samples before the earliest tap in auditioned IRs (room for the linear-phase EQs).
pub const LATENCY: usize = 192;
/// Audition IR length after the latency, seconds (direct sound + first reflections).
const IR_SECS: f64 = 0.4;

struct Editor {
    file: PathBuf,
    stage: Stage,
}

impl Editor {
    fn placements(&self) -> Vec<Placement> {
        self.stage.players.iter().map(|p| self.stage.placement(p)).collect()
    }

    fn state(&self) -> serde_json::Value {
        serde_json::json!({ "file": self.file.display().to_string(), "stage": self.stage, "placements": self.placements(), "latency": LATENCY })
    }
}

pub fn serve(file: &Path, port: u16) -> Result<()> {
    let stage = Stage::read(file)?;
    let mut ed = Editor { file: file.to_path_buf(), stage };
    let listener = TcpListener::bind(("127.0.0.1", port)).with_context(|| format!("port {port}"))?;
    println!("Stage editor for {}: http://localhost:{port}/  (Ctrl+C to stop)", file.display());
    for conn in listener.incoming() {
        let Ok(mut s) = conn else { continue };
        if let Err(e) = handle(&mut s, &mut ed) {
            let msg = format!("{e:#}");
            eprintln!("{msg}");
            let _ = respond(&mut s, "400 Bad Request", "text/plain; charset=utf-8", msg.as_bytes());
        }
    }
    Ok(())
}

fn respond(s: &mut TcpStream, status: &str, ctype: &str, body: &[u8]) -> Result<()> {
    write!(s, "HTTP/1.1 {status}\r\nContent-Type: {ctype}\r\nContent-Length: {}\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n", body.len())?;
    s.write_all(body)?;
    Ok(())
}

fn json(s: &mut TcpStream, v: &serde_json::Value) -> Result<()> {
    respond(s, "200 OK", "application/json", serde_json::to_string(v)?.as_bytes())
}

fn handle(s: &mut TcpStream, ed: &mut Editor) -> Result<()> {
    let mut r = BufReader::new(s.try_clone()?);
    let mut line = String::new();
    r.read_line(&mut line)?;
    let mut parts = line.split_whitespace();
    let (method, path) = (parts.next().unwrap_or("").to_string(), parts.next().unwrap_or("").to_string());
    let mut len = 0usize;
    loop {
        let mut h = String::new();
        r.read_line(&mut h)?;
        let h = h.trim_end();
        if h.is_empty() {
            break;
        }
        if let Some((k, v)) = h.split_once(':')
            && k.eq_ignore_ascii_case("content-length")
        {
            len = v.trim().parse()?;
        }
    }
    let mut body = vec![0u8; len];
    r.read_exact(&mut body)?;
    match (method.as_str(), path.as_str()) {
        ("GET", "/") | ("GET", "/index.html") => respond(s, "200 OK", "text/html; charset=utf-8", PAGE.as_bytes()),
        ("GET", "/api/stage") => json(s, &ed.state()),
        ("POST", "/api/stage") => {
            ed.stage = serde_json::from_slice(&body).context("stage JSON")?;
            json(s, &serde_json::json!({ "placements": ed.placements() }))
        }
        ("POST", "/api/save") => {
            let text = format!("# Stage edited with `stagecraft serve` (stagecraft/docs/STAGES.md)\n\n{}", ed.stage.to_toml()?);
            std::fs::write(&ed.file, text)?;
            json(s, &serde_json::json!({ "saved": ed.file.display().to_string() }))
        }
        ("GET", p) if p.starts_with("/api/ir/") => {
            let i: usize = p["/api/ir/".len()..].parse()?;
            let Some(pl) = ed.stage.players.get(i) else { bail!("no player {i}") };
            let n = LATENCY + (IR_SECS * crate::capture::SR) as usize;
            let ir = ed.stage.true_stereo(pl, crate::capture::SR, LATENCY, n);
            let mut out = Vec::with_capacity(ir.len() * n * 4);
            for c in &ir {
                for v in c {
                    out.extend((*v as f32).to_le_bytes());
                }
            }
            respond(s, "200 OK", "application/octet-stream", &out)
        }
        _ => respond(s, "404 Not Found", "text/plain", b"not found"),
    }
}
