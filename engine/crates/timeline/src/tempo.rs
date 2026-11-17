//! The tempo map of one flow: notated position (crotchets) <-> seconds from the flow start.
//!
//! A step function of tempo (crotchets per minute) over position, built the way Dorico plays
//! back. Every rule below was checked against Dorico 5's MIDI export of the reference project
//! `engine/tests/dorico-check/timeline-ref.dorico` and of the ET score (TIMELINE.md):
//!
//! - **absolute**: stated bpm × beat unit (♩. = 60 is 90 crotchets/min).
//! - **equation** (metric modulation, "old = new"): × right / left (minim = crotchet halves it).
//! - **relative** (`relativePercent`): percent of the tempo in effect. Dorico stores "meno
//!   mosso" as the Mosso preset at 110 % and plays it faster; we follow Dorico.
//! - **reset** "a tempo": back to the last absolute (or equation) tempo; "tempo primo": the
//!   flow's first tempo.
//! - **gradual** (rit./accel.): starts from Dorico's stored `initialTempo` when present (Play-mode
//!   tempo edits), else the tempo in effect; ends at `final_percent` of that. Dorico plays it in
//!   steps of a quarter crotchet: n = ⌊length / ¼⌋ steps (at least 1), step k at start + k/4 with
//!   tempo start + (end − start)·k/n; the final tempo begins at the ramp's end and stays.
//! - **fermata** at p over a note of length L, elongation E %, silence S % (play options by
//!   fermata length): [p, p+L/2) lasts L·(1+E), [p+L/2, p+L) lasts L·S.
//! - **caesura** at p after a note of length L: [p−L, p−L/2) lasts L/2 + L·S.
//! - **breath mark**: no time. Pauses inside a gradual tempo change are ignored (Dorico help).
//! - No tempo mark: 120 crotchets/min.

use dorico_format::ratio::Ratio;
use dorico_model::{Flow, PlaybackTiming};
use serde::Serialize;

/// Crotchets per minute when a flow has no tempo mark at its start (Dorico 5, reference flow 6).
pub const DEFAULT_BPM: f64 = 120.0;

/// Dorico plays gradual tempo changes in steps of this many crotchets.
pub fn ramp_step() -> Ratio {
    Ratio::new(1, 4)
}

/// A stretch of constant tempo.
#[derive(Debug, Clone, Serialize)]
pub struct Segment {
    pub start: Ratio,
    /// Seconds from the flow start at `start`.
    pub start_secs: f64,
    /// Crotchets per minute.
    pub bpm: f64,
}

#[derive(Debug, Clone, Serialize)]
pub struct TempoMap {
    pub segments: Vec<Segment>,
    /// Assumptions the map relied on (unconfirmed encodings or behaviour).
    pub caveats: Vec<String>,
}

/// A step function under construction: sorted (position, bpm) breakpoints.
struct Steps(Vec<(Ratio, f64)>);

impl Steps {
    fn set(&mut self, pos: Ratio, bpm: f64) {
        if let Some(last) = self.0.last_mut()
            && last.0 == pos
        {
            last.1 = bpm;
            return;
        }
        self.0.push((pos, bpm));
    }

    fn at(&self, pos: Ratio) -> f64 {
        let i = self.0.partition_point(|(p, _)| *p <= pos);
        self.0[i.saturating_sub(1)].1
    }
}

/// Note lengths around a position, from every voice of the flow (grace notes left out).
struct Notes(Vec<(Ratio, Ratio)>);

impl Notes {
    fn new(flow: &Flow) -> Notes {
        let mut v: Vec<(Ratio, Ratio)> = flow
            .parts
            .iter()
            .flat_map(|p| &p.voices)
            .flat_map(|v| &v.notes)
            .filter(|n| !n.grace && !n.dur.is_zero())
            .map(|n| (n.pos, n.dur))
            .collect();
        v.sort();
        Notes(v)
    }

    /// Length of the note a fermata at `p` holds: the shortest note starting there, else the
    /// gap to the next note, else a crotchet.
    fn starting(&self, p: Ratio) -> Ratio {
        self.0
            .iter()
            .filter(|(s, _)| *s == p)
            .map(|(_, d)| *d)
            .min()
            .or_else(|| self.0.iter().find(|(s, _)| *s > p).map(|(s, _)| *s - p))
            .unwrap_or(Ratio::ONE)
    }

    /// Length of the note a caesura at `p` follows: the shortest note ending there, else the
    /// gap from the last note start, else a crotchet.
    fn ending(&self, p: Ratio) -> Ratio {
        self.0
            .iter()
            .filter(|(s, d)| *s + *d == p)
            .map(|(_, d)| *d)
            .min()
            .or_else(|| self.0.iter().rev().find(|(s, _)| *s < p).map(|(s, _)| p - *s))
            .unwrap_or(Ratio::ONE)
    }
}

impl TempoMap {
    pub fn from_flow(flow: &Flow, opts: &PlaybackTiming) -> TempoMap {
        let mut caveats = Vec::new();
        let mut tempos: Vec<&dorico_model::Tempo> = flow.tempos.iter().collect();
        tempos.sort_by_key(|t| (t.pos, t.gradual));
        let mut bpm = DEFAULT_BPM;
        let (mut base, mut primo) = (DEFAULT_BPM, None::<f64>);
        let mut steps = Steps(vec![(Ratio::ZERO, DEFAULT_BPM)]);
        let mut ramps: Vec<(Ratio, Ratio)> = Vec::new();
        for (i, t) in tempos.iter().enumerate() {
            // the next change cuts a ramp short
            let next = tempos[i + 1..].iter().map(|n| n.pos).find(|p| *p > t.pos);
            if t.gradual {
                let full = t.end.unwrap_or(t.pos) - t.pos;
                let end = match next {
                    Some(n) if n < t.pos + full => n,
                    _ => t.pos + full,
                };
                let b0 = t.crotchet_bpm.unwrap_or(bpm);
                let b1 = b0 * t.final_percent.unwrap_or(100.0) / 100.0;
                let n = ((full / ramp_step()).floor()).max(1);
                for k in 0..n {
                    let p = t.pos + ramp_step() * Ratio::int(k);
                    if p >= end {
                        break;
                    }
                    steps.set(p, b0 + (b1 - b0) * k as f64 / n as f64);
                }
                if end == t.pos + full {
                    steps.set(end, b1);
                    bpm = b1;
                } else {
                    bpm = steps.at(end);
                }
                ramps.push((t.pos, t.pos + full));
                continue;
            }
            let new = match t.kind.as_str() {
                "equation" => t.equation.filter(|(o, _)| !o.is_zero()).map(|(o, n)| bpm * n.to_f64() / o.to_f64()),
                "relative" => t.percent.map(|p| bpm * p / 100.0),
                "reset" => match t.reset.as_str() {
                    "kTempoPrimo" => primo.or(Some(base)),
                    _ => Some(base),
                },
                _ => t.crotchet_bpm,
            };
            let Some(new) = new.filter(|b| *b > 0.0) else {
                caveats.push(format!("tempo at {} ({}) has no value; ignored", t.pos, t.kind));
                continue;
            };
            match t.kind.as_str() {
                "relative" => {}
                "reset" if t.reset == "kTempoPrimo" => base = new,
                _ => {
                    base = new;
                    primo.get_or_insert(new);
                }
            }
            bpm = new;
            steps.set(t.pos, new);
        }
        if !tempos.iter().any(|t| !t.gradual && t.pos.is_zero()) {
            caveats.push(format!("no tempo mark at the flow start: Dorico plays {DEFAULT_BPM} crotchets/min"));
        }

        // pauses: tempo overrides over intervals
        let mut overrides: Vec<(Ratio, Ratio, f64)> = Vec::new();
        if opts.play_pauses {
            let notes = Notes::new(flow);
            let in_ramp = |p: Ratio| ramps.iter().any(|(a, b)| *a <= p && p < *b);
            let mut pauses: Vec<(Ratio, String, String)> =
                flow.pauses.iter().map(|p| (p.pos, p.pause.kind.clone(), p.pause.fermata_duration.clone())).collect();
            let stave_pauses: Vec<(Ratio, String, String)> = flow
                .parts
                .iter()
                .flat_map(|p| &p.staves)
                .flat_map(|s| &s.marks)
                .filter(|m| m.kind == "pause")
                .map(|m| {
                    let d = |k: &str| m.detail.get(k).cloned().unwrap_or_default();
                    (m.pos, d("type"), d("duration"))
                })
                .collect();
            if stave_pauses.iter().any(|s| !pauses.contains(s)) {
                caveats.push("pauses on single staves timed like whole-flow pauses (unconfirmed)".into());
            }
            pauses.extend(stave_pauses);
            pauses.sort_by(|a, b| a.0.cmp(&b.0).then(a.1.cmp(&b.1)));
            pauses.dedup();
            for (p, kind, length) in pauses {
                if in_ramp(p) {
                    continue;
                }
                match kind.as_str() {
                    "kFermata" => {
                        let key = if length.is_empty() { "kNormal" } else { length.as_str() };
                        let Some(&(e, s)) = opts.fermata_percent.get(key) else {
                            caveats.push(format!("fermata length {key} at {p} unknown; not timed"));
                            continue;
                        };
                        let l = notes.starting(p);
                        let b = steps.at(p);
                        let half = l / Ratio::int(2);
                        if s > 0.0 {
                            overrides.push((p, p + half, b / (2.0 * (1.0 + e / 100.0))));
                            overrides.push((p + half, p + l, b / (2.0 * s / 100.0)));
                        } else {
                            overrides.push((p, p + l, b / (1.0 + e / 100.0)));
                        }
                        if l != Ratio::ONE && !caveats.iter().any(|c| c.starts_with("pause timing")) {
                            caveats.push("pause timing scaled by the note's length (confirmed for crotchets)".into());
                        }
                    }
                    "kCaesura" => {
                        let l = notes.ending(p);
                        let b = steps.at(p - l);
                        let s = opts.caesura_silence_percent / 100.0;
                        overrides.push((p - l, p - l / Ratio::int(2), b / (1.0 + 2.0 * s)));
                    }
                    "kBreathMark" => {}
                    other => {
                        if !caveats.iter().any(|c| c.contains(other)) {
                            caveats.push(format!("pause {other} not timed (no reference yet)"));
                        }
                    }
                }
            }
        }

        // apply overrides to the step function
        let mut points: Vec<Ratio> = steps.0.iter().map(|(p, _)| *p).collect();
        for (a, b, _) in &overrides {
            points.push(*a);
            points.push(*b);
        }
        points.sort();
        points.dedup();
        let value = |x: Ratio| overrides.iter().find(|(a, b, _)| *a <= x && x < *b).map(|o| o.2).unwrap_or_else(|| steps.at(x));
        let mut segments: Vec<Segment> = Vec::new();
        for x in points {
            let v = value(x);
            match segments.last() {
                Some(last) if (last.bpm - v).abs() < 1e-12 => {}
                Some(last) => {
                    let start_secs = last.start_secs + 60.0 * (x - last.start).to_f64() / last.bpm;
                    segments.push(Segment { start: x, start_secs, bpm: v });
                }
                None => segments.push(Segment { start: x, start_secs: 0.0, bpm: v }),
            }
        }
        TempoMap { segments, caveats }
    }

    fn index_at(&self, pos: Ratio) -> usize {
        self.segments.partition_point(|s| s.start <= pos).saturating_sub(1)
    }

    /// Seconds from the flow start to `pos` (notated order).
    pub fn seconds(&self, pos: Ratio) -> f64 {
        let s = &self.segments[self.index_at(pos)];
        s.start_secs + 60.0 * (pos - s.start).to_f64() / s.bpm
    }

    /// Position (crotchets, float) reached after `secs` seconds (notated order).
    pub fn crotchets(&self, secs: f64) -> f64 {
        let i = self.segments.partition_point(|s| s.start_secs <= secs).saturating_sub(1);
        let s = &self.segments[i];
        s.start.to_f64() + (secs - s.start_secs) * s.bpm / 60.0
    }

    /// Crotchets per minute at `pos`.
    pub fn bpm_at(&self, pos: Ratio) -> f64 {
        self.segments[self.index_at(pos)].bpm
    }
}
