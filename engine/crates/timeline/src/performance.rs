//! Performed order of a flow: the notated music as it is played, with repeats, 1st/2nd-time
//! endings and jumps (D.C., D.S., al Fine, al Coda, To Coda) unrolled.
//!
//! Checked against Dorico 5's MIDI export (TIMELINE.md):
//! - a repeat goes back to the flow start including a pick-up bar (the user's
//!   bars-numbers-repeats file);
//! - **a jump happens at the jump mark's own position**, not at the end of its bar (a D.S. on
//!   beat 4 leaves out the rest of that bar; D.C. in reference flow 5 likewise);
//! - after a jump, playback restates the tempo in effect at the jump target.
//!
//! Rules (standard practice, not contradicted by the exports):
//! - an end-repeat barline sends playback back to the last start-repeat barline (or the flow
//!   start / the bar after the previous end repeat);
//! - a section with endings plays `kRepeatEndingLineNumTimesPlayed` times (Dorico's "repeat 3
//!   times" = 4), else once per ending segment: the first segment on every pass but the last
//!   ones, each later segment on one pass ("1.-3.", "4."); without endings [`DEFAULT_PLAYS`]
//!   (Dorico's count for plain repeats: encoding not seen yet);
//! - a jump is taken once; after it, repeats play again only with `playRepeatsAfterDS`,
//!   otherwise each section plays once and takes its last ending;
//! - after "al Fine", playback stops at Fine; after "al Coda", To Coda (at its position) jumps
//!   to the Coda; `playRepeats` off: no repeats (jumps still taken).

use dorico_format::ratio::Ratio;
use dorico_model::{Bar, Flow, Mark, PlaybackTiming};
use serde::Serialize;

/// Times a repeated section without endings plays.
pub const DEFAULT_PLAYS: u32 = 2;

/// A stretch of notated music played in one go.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Span {
    pub from: Ratio,
    pub to: Ratio,
    /// Pass through the repeated section this music belongs to (1 = first time).
    pub pass: u32,
    /// True once a D.C./D.S. has been taken.
    pub after_jump: bool,
}

#[derive(Debug, Clone, Serialize)]
pub struct Performance {
    pub spans: Vec<Span>,
    pub caveats: Vec<String>,
}

fn barline_at(flow: &Flow, pos: Ratio, kinds: &[&str]) -> bool {
    flow.barlines.iter().any(|b| b.pos == pos && kinds.contains(&b.kind.as_str()))
}

fn marks<'a>(flow: &'a Flow, kind: &'a str) -> impl Iterator<Item = &'a Mark> + 'a {
    flow.repeats.iter().filter(move |m| m.kind == kind)
}

fn jump_kind(m: &Mark) -> &str {
    m.detail.get("jump").map(String::as_str).unwrap_or("")
}

/// Which ending segment plays on `pass` of `plays` passes, with `n` segments.
fn segment_for(pass: u32, plays: u32, n: usize) -> usize {
    let first_until = plays.saturating_sub(n as u32 - 1).max(1);
    if pass <= first_until { 0 } else { ((pass - first_until) as usize).min(n - 1) }
}

fn push(spans: &mut Vec<Span>, from: Ratio, to: Ratio, pass: u32, after_jump: bool) {
    if to <= from {
        return;
    }
    match spans.last_mut() {
        Some(s) if s.to == from && s.pass == pass && s.after_jump == after_jump => s.to = to,
        _ => spans.push(Span { from, to, pass, after_jump }),
    }
}

pub fn perform(flow: &Flow, opts: &PlaybackTiming) -> Performance {
    let bars: &[Bar] = &flow.bars;
    let mut caveats = Vec::new();
    let mut spans: Vec<Span> = Vec::new();
    if bars.is_empty() {
        return Performance { spans, caveats };
    }
    let bar_of = |pos: Ratio| bars.iter().position(|b| b.start <= pos && pos < b.start + b.length);
    let starts_repeat = |i: usize| barline_at(flow, bars[i].start, &["kStartRepeat", "kEndAndStartRepeat"]);
    let ends_repeat = |i: usize| barline_at(flow, bars[i].start + bars[i].length, &["kEndRepeat", "kEndAndStartRepeat"]);
    // bar index -> (segment index, number of segments, passes of the section)
    let mut segment_of: Vec<Option<(usize, usize, u32)>> = vec![None; bars.len()];
    for e in &flow.endings {
        let n = e.segments.len();
        let plays = e.times_played.unwrap_or(n as u32).max(1);
        let mut at = e.pos;
        for (k, len) in e.segments.iter().enumerate() {
            for (i, b) in bars.iter().enumerate() {
                if b.start >= at && b.start < at + *len {
                    segment_of[i] = Some((k, n, plays));
                }
            }
            at = at + *len;
        }
    }
    let segno = marks(flow, "segno").next().map(|m| m.pos);
    let coda = marks(flow, "coda").next().map(|m| m.pos);
    let fine = marks(flow, "fine").next().map(|m| m.pos);
    if (0..bars.len()).any(|i| ends_repeat(i) && segment_of[i].is_none()) {
        caveats.push(format!("repeats without endings play {DEFAULT_PLAYS} times (Dorico's count for them not read yet)"));
    }

    let (mut i, mut pass, mut section_start) = (0usize, 1u32, 0usize);
    // bar whose end-repeat sent playback back: past it (and past its endings) is pass 1 again
    let mut repeat_end: Option<usize> = None;
    let mut after_jump = false;
    let mut qualification = String::new();
    let mut taken: Vec<&str> = Vec::new();
    // where to continue inside the next bar (after a jump to a mid-bar target)
    let mut resume: Option<Ratio> = None;
    let mut steps = 0;
    while i < bars.len() {
        steps += 1;
        if steps > 100_000 {
            caveats.push("repeat structure did not terminate; stopped".into());
            break;
        }
        let repeats_on = opts.play_repeats && (!after_jump || opts.play_repeats_after_ds);
        let b = &bars[i];
        let start = resume.take().filter(|r| *r > b.start).unwrap_or(b.start);
        let end = b.start + b.length;
        if repeat_end.is_some_and(|e| i > e) && segment_of[i].is_none() {
            pass = 1;
            repeat_end = None;
            section_start = i;
        }
        // al Fine: a Fine at the start of this bar ends the piece
        if after_jump && qualification == "kAlFine" && i > 0 && fine == Some(start) {
            break;
        }
        // endings: play only the segment for this pass
        if let Some((k, n, plays)) = segment_of[i] {
            let want = if repeats_on { segment_for(pass, plays, n) } else { n - 1 };
            if k != want {
                i += 1;
                continue;
            }
        }
        // jumps inside this bar happen at the mark's position
        let in_bar = |m: &&Mark| m.pos >= start && m.pos < end;
        if after_jump
            && qualification == "kAlFine"
            && let Some(f) = fine.filter(|f| *f > start && *f <= end)
        {
            push(&mut spans, start, f, pass, after_jump);
            break;
        }
        if after_jump
            && qualification == "kAlCoda"
            && let Some(m) = marks(flow, "jump").filter(in_bar).find(|m| jump_kind(m) == "kToCoda")
            && let Some(c) = coda.filter(|c| *c > m.pos)
            && let Some(ci) = bar_of(c)
        {
            push(&mut spans, start, m.pos, pass, after_jump);
            i = ci;
            resume = Some(c);
            pass = 1;
            section_start = ci;
            continue;
        }
        let jump = marks(flow, "jump")
            .filter(in_bar)
            .find(|m| matches!(jump_kind(m), "kDaCapo" | "kDalSegno") && !taken.contains(&m.event_id.as_str()));
        if let Some(m) = jump {
            push(&mut spans, start, m.pos, pass, after_jump);
            taken.push(&m.event_id);
            let target = if jump_kind(m) == "kDalSegno" { segno.unwrap_or(Ratio::ZERO) } else { Ratio::ZERO };
            after_jump = true;
            qualification = m.detail.get("qualification").cloned().unwrap_or_default();
            i = bar_of(target).unwrap_or(0);
            resume = Some(target);
            pass = 1;
            section_start = i;
            continue;
        }
        push(&mut spans, start, end, pass, after_jump);
        // repeat back
        let plays = segment_of[i].map(|s| s.2).unwrap_or(DEFAULT_PLAYS);
        if ends_repeat(i) && repeats_on && pass < plays {
            pass += 1;
            repeat_end = Some(i);
            i = section_start;
            continue;
        }
        if ends_repeat(i) && segment_of[i].is_none() {
            pass = 1;
            repeat_end = None;
            section_start = i + 1;
        }
        i += 1;
        if i < bars.len() && starts_repeat(i) {
            section_start = i;
            pass = 1;
        }
    }
    Performance { spans, caveats }
}

#[cfg(test)]
mod tests {
    use super::segment_for;

    #[test]
    fn ending_segments_by_pass() {
        // two endings, "repeat 3 times" (4 passes): 1.-3. and 4.
        assert_eq!((1..=4).map(|p| segment_for(p, 4, 2)).collect::<Vec<_>>(), [0, 0, 0, 1]);
        // plain 1st/2nd ending
        assert_eq!((1..=2).map(|p| segment_for(p, 2, 2)).collect::<Vec<_>>(), [0, 1]);
        // three endings, three passes
        assert_eq!((1..=3).map(|p| segment_for(p, 3, 3)).collect::<Vec<_>>(), [0, 1, 2]);
    }
}
