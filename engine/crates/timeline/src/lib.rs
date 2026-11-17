//! Time in a Dorico project (engine module "timeline", MODULE_REVIEW §4 #3; design:
//! engine/docs/TIMELINE.md).
//!
//! ```text
//! notated position (crotchets) ──tempo map──▶ notated seconds
//!          │ performed order (repeats, endings, D.C./D.S., Fine, Coda)
//!          ▼
//! performed position ──▶ performed seconds ──▶ clip time (video) ──▶ timecode (any frame rate)
//!          └──▶ MIDI ticks (480 per crotchet, performed order) + tempo events
//! ```
//!
//! One [`FlowTimeline`] per flow; [`ProjectTimeline`] puts the flows one after another with
//! Dorico's gap between flows. Anything the result relies on that isn't confirmed against
//! Dorico is listed in `caveats`.

pub mod performance;
pub mod tempo;

use dorico_format::ratio::Ratio;
use dorico_format::timecode::FrameRate;
use dorico_model::{Flow, PlaybackTiming, Score, Video};
use serde::Serialize;

pub use performance::{Performance, Span};
pub use tempo::TempoMap;

/// Crotchets -> MIDI tick as Dorico's MIDI export rounds it (halves up; checked on the ET
/// score, where tempo changes fall on half ticks). `Ratio::to_ticks` rounds halves to even.
pub fn midi_tick(crotchets: Ratio) -> i128 {
    (crotchets * Ratio::int(dorico_format::ratio::TICKS_PER_CROTCHET) + Ratio::new(1, 2)).floor()
}

/// One sounding of a notated position.
#[derive(Debug, Clone, Copy, PartialEq, Serialize)]
pub struct Occurrence {
    /// Index into `FlowTimeline::performance.spans`.
    pub span: usize,
    pub pass: u32,
    /// Seconds from the flow start, performed order.
    pub secs: f64,
    /// Crotchets from the flow start, performed order.
    pub crotchets: Ratio,
}

/// A marker checked against the timeline: Dorico's stored clip time vs ours.
#[derive(Debug, Clone, Serialize)]
pub struct MarkerCheck {
    pub name: String,
    pub pos: Ratio,
    pub dorico_secs: f64,
    pub timeline_secs: f64,
}

#[derive(Debug, Clone, Serialize)]
pub struct FlowTimeline {
    pub flow_id: String,
    pub name: String,
    pub tempo: TempoMap,
    pub performance: Performance,
    /// Performed start of each span: (crotchets, seconds) from the flow start.
    pub span_starts: Vec<(Ratio, f64)>,
    /// Performed length in seconds.
    pub duration: f64,
    pub video: Option<Video>,
    /// Timecode rate: the clip's rate if stored, else the project's.
    pub frame_rate: Option<FrameRate>,
    pub caveats: Vec<String>,
}

impl FlowTimeline {
    pub fn new(flow: &Flow, opts: &PlaybackTiming) -> FlowTimeline {
        let tempo = TempoMap::from_flow(flow, opts);
        let performance = performance::perform(flow, opts);
        let mut span_starts = Vec::new();
        let (mut x, mut t) = (Ratio::ZERO, 0.0);
        for s in &performance.spans {
            span_starts.push((x, t));
            x = x + (s.to - s.from);
            t += tempo.seconds(s.to) - tempo.seconds(s.from);
        }
        let mut caveats = tempo.caveats.clone();
        caveats.extend(performance.caveats.iter().cloned());
        let video = flow.video.clone().filter(|v| v.attached);
        let project = FrameRate::from_dorico(&opts.project_frame_rate, opts.use_drop_format);
        let frame_rate = match video.as_ref().and_then(|v| v.clip_fps).and_then(FrameRate::from_fps) {
            // the clip's own rate, with the project's drop setting where SMPTE allows it
            Some(r) if r.fps != r.base as f64 => Some(FrameRate::pulled(r.base, opts.use_drop_format)),
            Some(r) => Some(r),
            None => project,
        };
        FlowTimeline {
            flow_id: flow.id.clone(),
            name: flow.name.clone(),
            tempo,
            performance,
            span_starts,
            duration: t,
            video,
            frame_rate,
            caveats,
        }
    }

    /// Seconds from the flow start to `pos` in notated order (ignoring repeats).
    pub fn notated_seconds(&self, pos: Ratio) -> f64 {
        self.tempo.seconds(pos)
    }

    /// Every time `pos` sounds, in performed order.
    pub fn occurrences(&self, pos: Ratio) -> Vec<Occurrence> {
        let mut out = Vec::new();
        let n = self.performance.spans.len();
        for (k, s) in self.performance.spans.iter().enumerate() {
            // a span's end belongs to it only if nothing follows (the flow's last moment)
            let inside = s.from <= pos && (pos < s.to || (pos == s.to && k + 1 == n));
            if inside {
                let (x0, t0) = self.span_starts[k];
                out.push(Occurrence {
                    span: k,
                    pass: s.pass,
                    secs: t0 + self.tempo.seconds(pos) - self.tempo.seconds(s.from),
                    crotchets: x0 + (pos - s.from),
                });
            }
        }
        out
    }

    /// First performed time of `pos` (seconds from the flow start).
    pub fn seconds(&self, pos: Ratio) -> Option<f64> {
        self.occurrences(pos).first().map(|o| o.secs)
    }

    /// Performed seconds -> (span index, notated position in crotchets as a float).
    pub fn at_seconds(&self, secs: f64) -> Option<(usize, f64)> {
        let k = self.span_starts.partition_point(|(_, t)| *t <= secs).checked_sub(1)?;
        let s = &self.performance.spans[k];
        let t_from = self.tempo.seconds(s.from);
        let x = self.tempo.crotchets(t_from + secs - self.span_starts[k].1);
        (x <= s.to.to_f64() + 1e-9 || k + 1 == self.performance.spans.len()).then_some((k, x.min(s.to.to_f64())))
    }

    /// Performed seconds -> clip time of the attached video (`None` without video).
    pub fn clip_time(&self, secs: f64) -> Option<f64> {
        let v = self.video.as_ref()?;
        Some(secs - self.seconds(v.start)? + v.offset)
    }

    /// Performed seconds -> timecode: with video, the clip's timecode (timecode start + clip
    /// time, as Dorico shows markers); without, time from the flow start.
    pub fn timecode(&self, secs: f64) -> Option<String> {
        let rate = self.frame_rate?;
        let t = match &self.video {
            Some(v) => v.timecode_start + self.clip_time(secs)?,
            None => secs,
        };
        Some(rate.format(t))
    }

    /// Tempo for a MIDI file in performed order: (tick, crotchets per minute) at every change,
    /// as Dorico's own MIDI export writes them (rit./accel. in quarter-crotchet steps, fermatas
    /// as slower stretches; the tempo restated after a jump).
    pub fn tempo_events(&self) -> Vec<(i128, f64)> {
        let mut out: Vec<(i128, f64)> = Vec::new();
        for (k, s) in self.performance.spans.iter().enumerate() {
            let x0 = self.span_starts[k].0;
            let at = |p: Ratio| midi_tick(x0 + (p - s.from));
            let mut push = |tick: i128, bpm: f64| {
                if out.last().is_some_and(|l| l.0 == tick) {
                    out.pop();
                }
                if out.last().is_none_or(|l| (l.1 - bpm).abs() > 1e-9) {
                    out.push((tick, bpm));
                }
            };
            push(at(s.from), self.tempo.bpm_at(s.from));
            for seg in self.tempo.segments.iter().filter(|g| g.start > s.from && g.start < s.to) {
                push(at(seg.start), seg.bpm);
            }
        }
        out
    }

    /// Markers: Dorico's stored clip time against the timeline's (film projects).
    pub fn check_markers(&self, flow: &Flow) -> Vec<MarkerCheck> {
        flow.markers
            .iter()
            .filter_map(|m| {
                Some(MarkerCheck {
                    name: m.marker.name.clone(),
                    pos: m.pos,
                    dorico_secs: m.marker.time,
                    timeline_secs: self.clip_time(self.seconds(m.pos)?)?,
                })
            })
            .collect()
    }
}

/// All flows, played one after another.
#[derive(Debug, Clone, Serialize)]
pub struct ProjectTimeline {
    pub flows: Vec<FlowTimeline>,
    /// Seconds from the start of playback to each flow's start (pre-roll, then each flow
    /// followed by `gapBetweenFlowsSeconds`).
    pub flow_starts: Vec<f64>,
    pub playback: PlaybackTiming,
}

impl ProjectTimeline {
    pub fn new(score: &Score) -> ProjectTimeline {
        let flows: Vec<FlowTimeline> = score.flows.iter().map(|f| FlowTimeline::new(f, &score.playback)).collect();
        let mut flow_starts = Vec::new();
        let mut t = score.playback.pre_roll;
        for f in &flows {
            flow_starts.push(t);
            t += f.duration + score.playback.gap_between_flows;
        }
        ProjectTimeline { flows, flow_starts, playback: score.playback.clone() }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use dorico_model::{Barline, Ending, Mark, Tempo};
    use std::collections::BTreeMap;

    fn r(n: i128) -> Ratio {
        Ratio::int(n)
    }

    fn opts() -> PlaybackTiming {
        let root = dorico_format::Node::element("score", vec![]);
        dorico_format::vocab::playback_timing(&root)
    }

    /// A flow of `n` 4/4 bars at `bpm` crotchets per minute.
    fn flow(n: i128, bpm: f64) -> Flow {
        let divisions = vec![dorico_format::bars::Division { pos: Ratio::ZERO, time_signature: Some((4, 4)), pickup: None }];
        Flow {
            id: "0".into(),
            name: "test".into(),
            length: r(4 * n),
            bars: dorico_format::bars::compute_bars(&divisions, &[], r(4 * n)),
            time_signatures: vec![],
            barlines: vec![],
            key_changes: vec![],
            keys: vec![],
            tempos: vec![tempo(0, bpm)],
            rehearsal_marks: vec![],
            bar_number_changes: vec![],
            repeats: vec![],
            endings: vec![],
            pauses: vec![],
            video: None,
            markers: vec![],
            parts: vec![],
        }
    }

    fn tempo(pos: i128, bpm: f64) -> Tempo {
        Tempo {
            pos: r(pos),
            bpm: Some(bpm),
            text: String::new(),
            gradual: false,
            end: None,
            final_percent: None,
            event_id: String::new(),
            kind: "absolute".into(),
            unit: Ratio::ONE,
            crotchet_bpm: Some(bpm),
            bpm_max: None,
            equation: None,
            percent: None,
            reset: String::new(),
            preset: String::new(),
        }
    }

    fn jump(id: &str, pos: i128, jump: &str, q: &str) -> Mark {
        let mut d = BTreeMap::new();
        d.insert("jump".to_owned(), jump.to_owned());
        d.insert("qualification".to_owned(), q.to_owned());
        Mark::plain("jump".into(), id, r(pos), None, d)
    }

    fn spans(t: &FlowTimeline) -> Vec<(i128, i128, u32)> {
        t.performance.spans.iter().map(|s| (s.from.floor(), s.to.floor(), s.pass)).collect()
    }

    #[test]
    fn plain_flow() {
        let t = FlowTimeline::new(&flow(4, 120.0), &opts());
        assert_eq!(spans(&t), [(0, 16, 1)]);
        assert!((t.duration - 8.0).abs() < 1e-12);
        assert_eq!(t.seconds(r(6)), Some(3.0));
    }

    #[test]
    fn simple_repeat_and_endings() {
        // bars 1-4, repeat bars 2-3 with 1st ending = bar 3, 2nd ending = bar 4
        let mut f = flow(5, 60.0);
        f.barlines = vec![Barline { pos: r(4), kind: "kStartRepeat".into() }, Barline { pos: r(12), kind: "kEndRepeat".into() }];
        f.endings = vec![Ending { event_id: "e".into(), pos: r(8), end: r(16), segments: vec![r(4), r(4)], times_played: None }];
        let t = FlowTimeline::new(&f, &opts());
        // after the 2nd ending (bar 4) the music is pass 1 again
        assert_eq!(spans(&t), [(0, 12, 1), (4, 8, 2), (12, 16, 2), (16, 20, 1)]);
        let occ = t.occurrences(r(5));
        assert_eq!(occ.iter().map(|o| o.secs).collect::<Vec<_>>(), [5.0, 13.0]);
        // "repeat 3 times" (4 passes): 1st ending on passes 1-3, 2nd on pass 4
        let mut f4 = f.clone();
        f4.endings[0].times_played = Some(4);
        let t4 = FlowTimeline::new(&f4, &opts());
        assert_eq!(spans(&t4), [(0, 12, 1), (4, 12, 2), (4, 12, 3), (4, 8, 4), (12, 16, 4), (16, 20, 1)]);
        // repeats off: straight through, last ending only
        let mut o = opts();
        o.play_repeats = false;
        let t = FlowTimeline::new(&f, &o);
        assert_eq!(spans(&t), [(0, 8, 1), (12, 20, 1)]);
    }

    #[test]
    fn ds_al_coda() {
        // 6 bars: segno at bar 2, To Coda in bar 3, D.S. al Coda in bar 4, coda at bar 5
        let mut f = flow(6, 60.0);
        f.repeats = vec![
            Mark::plain("segno".into(), "s", r(4), None, BTreeMap::new()),
            jump("tc", 11, "kToCoda", "kEndOfFlow"),
            jump("ds", 15, "kDalSegno", "kAlCoda"),
            Mark::plain("coda".into(), "c", r(16), None, BTreeMap::new()),
        ];
        let t = FlowTimeline::new(&f, &opts());
        let s: Vec<(i128, i128)> = spans(&t).iter().map(|s| (s.0, s.1)).collect();
        // jumps happen at the marks' positions (Dorico): D.S. at 15, To Coda at 11
        assert_eq!(s, [(0, 15), (4, 11), (16, 24)]);
    }

    #[test]
    fn dc_al_fine() {
        let mut f = flow(4, 60.0);
        f.repeats = vec![
            Mark::plain("fine".into(), "f", r(8), None, BTreeMap::new()),
            jump("dc", 15, "kDaCapo", "kAlFine"),
        ];
        let t = FlowTimeline::new(&f, &opts());
        let s: Vec<(i128, i128)> = spans(&t).iter().map(|s| (s.0, s.1)).collect();
        assert_eq!(s, [(0, 15), (0, 8)]);
    }

    #[test]
    fn dotted_beat_and_metric_modulation() {
        let mut f = flow(4, 60.0);
        f.tempos = vec![Tempo { unit: Ratio::new(3, 2), bpm: Some(60.0), crotchet_bpm: Some(90.0), ..tempo(0, 90.0) }];
        // minim = crotchet at bar 3: 90 -> 45 crotchets/min
        f.tempos.push(Tempo {
            kind: "equation".into(),
            bpm: None,
            crotchet_bpm: None,
            equation: Some((r(2), r(1))),
            ..tempo(8, 0.0)
        });
        let t = FlowTimeline::new(&f, &opts());
        assert!((t.seconds(r(8)).unwrap() - 8.0 * 60.0 / 90.0).abs() < 1e-12);
        assert!((t.tempo.bpm_at(r(9)) - 45.0).abs() < 1e-12);
    }

    #[test]
    fn rit_and_tempo_events() {
        let mut f = flow(4, 120.0);
        f.tempos.push(Tempo {
            gradual: true,
            kind: "gradual".into(),
            end: Some(r(8)),
            final_percent: Some(50.0),
            bpm: None,
            crotchet_bpm: None,
            ..tempo(4, 0.0)
        });
        let t = FlowTimeline::new(&f, &opts());
        assert!((t.tempo.bpm_at(r(6)) - 90.0).abs() < 1e-12);
        assert!((t.tempo.bpm_at(r(12)) - 60.0).abs() < 1e-12);
        // Dorico: quarter-crotchet steps, step k = 120 - 60k/16, final tempo at the end
        let ev = t.tempo_events();
        assert_eq!(ev.first(), Some(&(0, 120.0)));
        assert_eq!(ev[1], (1920 + 120, 120.0 - 60.0 / 16.0));
        assert_eq!(ev.last().map(|e| (e.0, e.1)), Some((3840, 60.0)));
        assert_eq!(ev.len(), 17);
        assert!(t.caveats.is_empty(), "{:?}", t.caveats);
    }

    #[test]
    fn timecode_with_video() {
        let mut f = flow(4, 60.0);
        f.video = Some(Video { attached: true, file: "x.mov".into(), start: r(4), offset: 6.0, timecode_start: 3600.0, clip_fps: Some(25.0) });
        let t = FlowTimeline::new(&f, &opts());
        // bar 2 = clip time 6 s = 01:00:06:00
        assert_eq!(t.timecode(4.0).as_deref(), Some("01:00:06:00"));
        assert_eq!(t.clip_time(5.5), Some(7.5));
    }
}
