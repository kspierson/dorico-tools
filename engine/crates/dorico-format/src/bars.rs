//! Bars of a flow and their displayed numbers, from its bar divisions (time signatures,
//! barlines, pick-ups, bar-number changes). Shared by dorigit's listing and the read model.
//!
//! Where bars start (union of the three old readers, checked against Dorico files):
//! - The flow starts in 4/4 until the first time signature.
//! - A bar division in the global stream (time signature or barline) always starts a new
//!   bar, even mid-bar.
//! - `irregularBarLength` on a division makes the bar starting there that long (pick-up).
//! - Bars continue until the end of the music; a flow has at least one bar.
//!
//! Displayed numbers (checked against the user's reference file,
//! finale2dorico/experiments/round7/ref-start.dorico, 2026-10-29):
//! - A pick-up bar at the very start is bar 0; the first full bar is bar 1.
//! - `barNumberChangeIfAny` on a bar division changes the number of the bar starting there.
//!   Dorico stored the user's two changes as hidden bar divisions in a *stave* stream (the
//!   top player's), so changes are read from every stream; they never start a bar.
//!   - primary sequence (`kUsePrimarySequence`): the bar is numbered `index`, then counting
//!     continues from it.
//!   - subordinate sequence (`kUseSubordinateSequence`): the bar keeps the previous bar's
//!     number and gets a letter suffix from `index` (1 = a), counting up per bar ("35a",
//!     "35b", ...) until the next change. Confirmed by the user in Dorico 2026-10-30 (bars
//!     8, 9 = "35a", "35b"; the coda starts at "35h").
//! - Repeats don't change bar numbers (Dorico numbers written bars).

use crate::dtn::Node;
use crate::ratio::Ratio;
use serde::Serialize;

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Bar {
    /// 1-based count of bars from the start of the flow (a pick-up is bar 1 here).
    pub index: u32,
    pub start: Ratio,
    pub length: Ratio,
    pub num: i64,
    pub den: i64,
    /// Shorter (or longer) than the time signature says: a pick-up, or a bar cut short by a
    /// barline/time signature in the middle.
    pub irregular: bool,
    /// Displayed (primary) bar number: 0 for an opening pick-up, changed by bar-number changes.
    pub number: i64,
    /// Subordinate number (1 = "a") when a subordinate sequence is running.
    pub sub: Option<i64>,
    /// What Dorico shows: "12", "0", "35a".
    pub label: String,
}

/// One bar division event in the global stream: its position, the time signature it sets
/// (if any) and an irregular length for the bar it starts.
#[derive(Debug, Clone, Copy)]
pub struct Division {
    pub pos: Ratio,
    pub time_signature: Option<(i64, i64)>,
    pub pickup: Option<Ratio>,
}

/// A bar-number change (`barNumberChangeIfAny`), from any stream.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct NumberChange {
    pub pos: Ratio,
    /// `kRestartSequence` (the only type seen so far).
    pub kind: String,
    /// true: subordinate sequence ("35a"); false: primary ("30").
    pub subordinate: bool,
    pub index: i64,
    pub hide_primary: bool,
}

/// Time signature, pick-up length and bar-number change of a `BarDivisionElementDefinition`.
pub fn read_division(pos: Ratio, element: Option<&Node>) -> (Division, Option<NumberChange>) {
    let bd = element.and_then(|e| e.child("barDivisionData"));
    let pickup = bd.map(|b| b.text("irregularBarLength")).filter(|s| !s.is_empty()).map(Ratio::parse);
    let time_signature = bd
        .and_then(|b| b.find("timeSignature/timeSignaturesAndDivisions"))
        .and_then(|a| a.items().first())
        .and_then(|t| t.child("timeSignature"))
        .map(|s| (s.text("numerator").parse().unwrap_or(4), s.text("denominator").parse().unwrap_or(4)));
    let change =
        bd.and_then(|b| b.child("barNumberChangeIfAny")).filter(|c| !c.children.is_empty()).map(|c| NumberChange {
            pos,
            kind: c.text("type").to_owned(),
            subordinate: c.text("sequence") == "kUseSubordinateSequence",
            index: c.text("index").parse().unwrap_or(1),
            hide_primary: c.text("hidePrimaryNumbers") == "true",
        });
    (Division { pos, time_signature, pickup }, change)
}

/// "a", "b", ..., "z", "aa", ... for subordinate numbers 1, 2, ...
pub fn letters(mut n: i64) -> String {
    let mut out = Vec::new();
    while n > 0 {
        n -= 1;
        out.push(b'a' + (n % 26) as u8);
        n /= 26;
    }
    out.reverse();
    String::from_utf8(out).unwrap_or_default()
}

const MAX_BARS: usize = 100_000;

pub fn compute_bars(divisions: &[Division], changes: &[NumberChange], end: Ratio) -> Vec<Bar> {
    let mut ds: Vec<Division> = divisions.to_vec();
    ds.sort_by_key(|d| d.pos);
    let mut cs: Vec<&NumberChange> = changes.iter().collect();
    cs.sort_by_key(|c| c.pos);
    let (mut num, mut den) = (4i64, 4i64);
    let mut bars: Vec<Bar> = Vec::new();
    let mut at = Ratio::ZERO;
    let (mut i, mut ci) = (0, 0);
    let (mut number, mut sub): (i64, Option<i64>) = (0, None);
    while (at < end || bars.is_empty()) && bars.len() < MAX_BARS {
        let mut pickup = None;
        while i < ds.len() && ds[i].pos <= at {
            if let Some((n, d)) = ds[i].time_signature {
                (num, den) = (n.max(1), d.max(1));
            }
            if ds[i].pos == at {
                pickup = ds[i].pickup.filter(|p| *p > Ratio::ZERO);
            }
            i += 1;
        }
        let regular = Ratio::new(4 * num as i128, den as i128);
        let mut length = pickup.unwrap_or(regular);
        // the next division starts a new bar, even in the middle of this one
        if let Some(next) = ds.get(i)
            && next.pos < at + length
        {
            length = next.pos - at;
        }
        // displayed number: count on, then apply a change that falls in this bar
        if bars.is_empty() {
            number = if pickup.is_some() && length < regular { 0 } else { 1 };
        } else if let Some(s) = sub {
            sub = Some(s + 1);
        } else {
            number += 1;
        }
        while ci < cs.len() && cs[ci].pos < at + length {
            let c = cs[ci];
            if c.subordinate {
                if sub.is_none() && !bars.is_empty() {
                    number -= 1; // the subordinate run keeps the previous bar's number
                }
                sub = Some(c.index);
            } else {
                number = c.index;
                sub = None;
            }
            ci += 1;
        }
        let label = format!("{number}{}", sub.map(letters).unwrap_or_default());
        bars.push(Bar {
            index: bars.len() as u32 + 1,
            start: at,
            length,
            num,
            den,
            irregular: length != regular,
            number,
            sub,
            label,
        });
        at = at + length;
    }
    bars
}

/// The bar containing `pos` (the last bar for positions past the end).
pub fn bar_at(bars: &[Bar], pos: Ratio) -> Option<&Bar> {
    let i = bars.partition_point(|b| b.start <= pos);
    bars.get(i.checked_sub(1)?)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn d(pos: Ratio, ts: Option<(i64, i64)>, pickup: Option<Ratio>) -> Division {
        Division { pos, time_signature: ts, pickup }
    }

    fn change(pos: i128, subordinate: bool, index: i64) -> NumberChange {
        NumberChange { pos: Ratio::int(pos), kind: "kRestartSequence".into(), subordinate, index, hide_primary: false }
    }

    #[test]
    fn plain_and_changes() {
        let b = compute_bars(
            &[d(Ratio::ZERO, Some((3, 4)), None), d(Ratio::int(6), Some((6, 8)), None)],
            &[],
            Ratio::int(12),
        );
        let starts: Vec<String> = b.iter().map(|b| b.start.to_string()).collect();
        assert_eq!(starts, ["0", "3", "6", "9"]);
        assert_eq!((b[2].num, b[2].den), (6, 8));
        assert!(b.iter().all(|b| !b.irregular));
        let labels: Vec<&str> = b.iter().map(|b| b.label.as_str()).collect();
        assert_eq!(labels, ["1", "2", "3", "4"]);
    }

    #[test]
    fn pickup_bar_is_bar_0() {
        let b = compute_bars(&[d(Ratio::ZERO, Some((4, 4)), Some(Ratio::int(1)))], &[], Ratio::int(9));
        assert_eq!(b[0].length, Ratio::int(1));
        assert!(b[0].irregular);
        assert_eq!(b[1].start, Ratio::int(1));
        assert_eq!(b.len(), 3);
        let labels: Vec<&str> = b.iter().map(|b| b.label.as_str()).collect();
        assert_eq!(labels, ["0", "1", "2"]);
    }

    #[test]
    fn division_mid_bar_starts_a_new_bar() {
        let b = compute_bars(&[d(Ratio::ZERO, Some((4, 4)), None), d(Ratio::int(6), None, None)], &[], Ratio::int(10));
        let starts: Vec<String> = b.iter().map(|b| b.start.to_string()).collect();
        assert_eq!(starts, ["0", "4", "6"]);
        assert!(b[1].irregular, "a shortened bar is irregular");
        assert_eq!(b[2].number, 3);
    }

    #[test]
    fn number_changes_like_the_reference_file() {
        // ref-start.dorico: 1-beat pick-up, primary restart at 30 on bar 2 (pos 5),
        // subordinate from 1 on bar 8 (pos 29), 65 crotchets long (the flow's
        // minimumNotatedLength; notes run to 65). The coda starts at 57 = "35h".
        let b = compute_bars(
            &[d(Ratio::ZERO, Some((4, 4)), Some(Ratio::int(1)))],
            &[change(5, false, 30), change(29, true, 1)],
            Ratio::int(65),
        );
        let labels: Vec<&str> = b.iter().map(|b| b.label.as_str()).collect();
        assert_eq!(
            labels,
            [
                "0", "1", "30", "31", "32", "33", "34", "35", "35a", "35b", "35c", "35d", "35e", "35f", "35g", "35h",
                "35i"
            ]
        );
    }

    #[test]
    fn subordinate_letters() {
        assert_eq!(letters(1), "a");
        assert_eq!(letters(26), "z");
        assert_eq!(letters(27), "aa");
    }

    #[test]
    fn empty_flow_has_one_bar() {
        assert_eq!(compute_bars(&[], &[], Ratio::ZERO).len(), 1);
    }
}
