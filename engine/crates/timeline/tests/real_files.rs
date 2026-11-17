//! The timeline against Dorico's own numbers in the user's files (opt-in, personal corpus):
//!   DORICO_REAL_FILES=1 cargo test -p dorico-timeline --release --test real_files -- --nocapture
//!
//! - every marker: Dorico stores its clip time and recomputes its beat position when tempo or
//!   picture changes, so position -> seconds must give back the stored time (to within the
//!   position's rounding: Dorico stores marker positions on a 1/480-crotchet grid);
//! - every project: a timeline builds and the performed order ends.
//!
//! Film projects live in the projects' backup folders, so those are scanned too.

use dorico_format::Project;
use dorico_paths::corpus::Corpus;
use dorico_timeline::ProjectTimeline;

#[test]
fn markers_match_dorico() {
    if std::env::var("DORICO_REAL_FILES").is_err() {
        eprintln!("DORICO_REAL_FILES not set; skipping");
        return;
    }
    let c = Corpus::load().unwrap();
    let mut files = c.dorico_files("projects");
    files.extend(c.dorico_files("test_files"));
    fn walk(dir: &std::path::Path, out: &mut Vec<std::path::PathBuf>) {
        for e in std::fs::read_dir(dir).into_iter().flatten().flatten() {
            let p = e.path();
            if p.is_dir() {
                walk(&p, out);
            } else if p.extension().is_some_and(|x| x == "dorico") {
                out.push(p);
            }
        }
    }
    if let Some(dir) = c.available("projects") {
        walk(&dir.join("Backup Projects"), &mut files);
    }
    walk(&dorico_paths::corpus::repo_root().join("dorigit/research/refs"), &mut files);
    let (mut checked, mut worst, mut projects, mut gradual, mut gradual_off) = (0, 0f64, 0, 0, 0);
    for f in &files {
        let Ok(p) = Project::read(f) else { continue };
        let score = dorico_model::read_project(&p).unwrap();
        let t = ProjectTimeline::new(&score);
        projects += 1;
        for (flow, ft) in score.flows.iter().zip(&t.flows) {
            assert!(ft.duration.is_finite() && ft.duration >= 0.0, "{}", f.display());
            for m in ft.check_markers(flow) {
                // error in ticks (1/480 crotchet) at the local tempo: Dorico rounds the stored
                // marker position, so a few ticks are expected
                let tick_secs = 60.0 / ft.tempo.bpm_at(m.pos) / 480.0;
                let d = (m.timeline_secs - m.dorico_secs).abs() / tick_secs;
                assert!(d <= 3.0, "{}: marker {:?} at {}: Dorico {} s, timeline {} s", f.display(), m.name, m.pos, m.dorico_secs, m.timeline_secs);
                worst = worst.max(d);
                checked += 1;
            }
            // Dorico's stored starting tempo of each rit./accel. vs the tempo in effect there
            for g in flow.tempos.iter().filter(|t| t.gradual) {
                if let Some(stored) = g.crotchet_bpm {
                    gradual += 1;
                    if (stored - ft.tempo.bpm_at(g.pos)).abs() > 0.05 {
                        gradual_off += 1;
                    }
                }
            }
        }
    }
    eprintln!(
        "{projects} projects; {checked} markers within 3 ticks (worst {worst:.2} ticks); \
         {gradual} gradual tempos, {gradual_off} whose stored start tempo differs from the map"
    );
}

/// Tempo events of a MIDI file's first track: (tick, crotchets per minute).
fn midi_tempos(path: &std::path::Path) -> Vec<(i128, f64)> {
    let d = std::fs::read(path).unwrap();
    let vlq = |p: &mut usize| {
        let mut v = 0u64;
        loop {
            let b = d[*p];
            *p += 1;
            v = (v << 7) | u64::from(b & 0x7F);
            if b < 0x80 {
                return v;
            }
        }
    };
    assert_eq!(&d[..4], b"MThd");
    let mut p = 14;
    assert_eq!(&d[p..p + 4], b"MTrk");
    let len = u32::from_be_bytes(d[p + 4..p + 8].try_into().unwrap()) as usize;
    p += 8;
    let end = p + len;
    let (mut t, mut run, mut out) = (0i128, 0u8, Vec::new());
    while p < end {
        t += vlq(&mut p) as i128;
        let s = d[p];
        if s == 0xFF {
            let typ = d[p + 1];
            p += 2;
            let n = vlq(&mut p) as usize;
            if typ == 0x51 {
                let us = u32::from_be_bytes([0, d[p], d[p + 1], d[p + 2]]);
                out.push((t, 60e6 / us as f64));
            }
            p += n;
        } else if s == 0xF0 || s == 0xF7 {
            p += 1;
            p += vlq(&mut p) as usize;
        } else {
            if s & 0x80 != 0 {
                run = s;
                p += 1;
            }
            p += if matches!(run & 0xF0, 0xC0 | 0xD0) { 1 } else { 2 };
        }
    }
    out
}

/// Same tempo twice in a row, or two events on one tick: keep the last meaningful one.
fn dedupe(ev: &[(i128, f64)]) -> Vec<(i128, f64)> {
    let mut out: Vec<(i128, f64)> = Vec::new();
    for &(t, v) in ev {
        if out.last().is_some_and(|l| l.0 == t) {
            out.pop();
        }
        if out.last().is_none_or(|l| (l.1 - v).abs() > 0.01) {
            out.push((t, v));
        }
    }
    out
}

/// The timeline's MIDI tempo events against Dorico 5's own MIDI export of the same flow
/// (engine/tests/dorico-check/timeline-ref-midi, made by the user 2026-11-01; skipped when
/// absent). Ticks exact, tempo within 0.01 crotchets/min.
#[test]
fn tempo_events_match_dorico_midi_export() {
    let root = dorico_paths::corpus::repo_root();
    let midi = root.join("engine/tests/dorico-check/timeline-ref-midi");
    if !midi.is_dir() {
        eprintln!("{} missing; skipping", midi.display());
        return;
    }
    let projects = [
        root.join("engine/tests/dorico-check/timeline-ref.dorico"),
        root.join("engine/tests/dorico-files/reference/bars-numbers-repeats.dorico"),
        root.join("engine/tests/dorico-files/ET The Flying Theme mASTER A-rebuilt.dorico"),
    ];
    let mut checked = 0;
    for path in projects.iter().filter(|p| p.is_file()) {
        let score = dorico_model::read_project(&Project::read(path).unwrap()).unwrap();
        let t = ProjectTimeline::new(&score);
        let stem = path.file_stem().unwrap().to_string_lossy().to_string();
        for (flow, ft) in score.flows.iter().zip(&t.flows) {
            // Dorico names exports "<project> - Full score - <flow>.mid" (a final "." dropped)
            let Some(file) = std::fs::read_dir(&midi).unwrap().flatten().map(|e| e.path()).find(|m| {
                let n = m.file_stem().unwrap().to_string_lossy().to_string();
                n.starts_with(&format!("{stem} - Full score - "))
                    && (n.ends_with(flow.name.trim_end_matches('.')) || score.flows.len() == 1)
            }) else {
                continue;
            };
            let dorico = dedupe(&midi_tempos(&file));
            let last = dorico.last().map(|e| e.0).unwrap_or(0);
            let ours: Vec<_> = dedupe(&ft.tempo_events()).into_iter().filter(|e| e.0 <= last).collect();
            assert_eq!(dorico.len(), ours.len(), "{}: {} events, timeline {}", file.display(), dorico.len(), ours.len());
            for (a, b) in dorico.iter().zip(&ours) {
                assert!(a.0 == b.0 && (a.1 - b.1).abs() <= 0.01, "{}: Dorico {a:?}, timeline {b:?}", file.display());
            }
            checked += 1;
        }
    }
    eprintln!("{checked} flows match Dorico's MIDI export");
}
