//! Frame rates and SMPTE timecode (the one implementation; dorigit's listing and the timeline
//! crate both use it).
//!
//! Dorico Pro supports project frame rates from 23.976 to 60 fps and labels non-drop rates
//! "fps" and drop-frame rates "dfps" (Dorico help, "Frame rates" / "Timecodes"). The project
//! rate is the play option `timeDisplayPlaybackOptions/projectFrameRate` (`k24`, `k25` seen in
//! the user's files) plus `useDropFormat`; a video clip's own rate is `kVideoClipFrameRate`.
//!
//! - **Pull-down rates** (23.976, 29.97, 47.952, 59.94) run at exactly nominal × 1000/1001
//!   frames per second; their timecode counts frames on the nominal base (24, 30, 48, 60).
//! - **Drop frame** exists only for 29.97 (2 frame numbers skipped each minute except every
//!   tenth) and 59.94 (4 skipped). A drop request for any other rate gives non-drop, because
//!   SMPTE defines no drop form there.
//!
//! Supported: every rate in [`FrameRate::STANDARD`] and any other whole or pulled-down rate.
//! Which of these Dorico's dialog offers, and its option names beyond `k24`/`k25`, is still to
//! confirm with a reference file (engine/docs/TIMELINE.md).

use serde::Serialize;
use std::fmt;

/// A frame rate: the timecode base (frames counted per timecode second), the real rate, and
/// whether frame numbers are dropped.
#[derive(Debug, Clone, Copy, PartialEq, Serialize)]
pub struct FrameRate {
    /// Frames per timecode second (24, 25, 30, 48, 50, 60 …).
    pub base: u32,
    /// Real frames per second (29.97002997… for 30 pulled down).
    pub fps: f64,
    /// Drop-frame numbering (only ever true for 29.97 and 59.94).
    pub drop: bool,
}

impl FrameRate {
    /// The rates film and broadcast use (Dorico: "23.976 to 60 fps").
    pub const STANDARD: [FrameRate; 12] = [
        FrameRate::pulled(24, false),
        FrameRate::whole(24),
        FrameRate::whole(25),
        FrameRate::pulled(30, false),
        FrameRate::pulled(30, true),
        FrameRate::whole(30),
        FrameRate::pulled(48, false),
        FrameRate::whole(48),
        FrameRate::whole(50),
        FrameRate::pulled(60, false),
        FrameRate::pulled(60, true),
        FrameRate::whole(60),
    ];

    /// A whole rate such as 25 fps (non-drop).
    pub const fn whole(base: u32) -> FrameRate {
        FrameRate { base, fps: base as f64, drop: false }
    }

    /// A pulled-down rate (`base` × 1000/1001), drop frame if asked and SMPTE defines it.
    pub const fn pulled(base: u32, drop: bool) -> FrameRate {
        FrameRate { base, fps: base as f64 * 1000.0 / 1001.0, drop: drop && (base == 30 || base == 60) }
    }

    /// From a measured rate such as a clip's `kVideoClipFrameRate` (23.976023…): rates within
    /// 0.01 of a pull-down rate become that exact rate; anything else counts on its rounded base.
    pub fn from_fps(fps: f64) -> Option<FrameRate> {
        if !(fps.is_finite() && fps > 0.0) {
            return None;
        }
        for base in [24, 30, 48, 60, 120] {
            let p = FrameRate::pulled(base, false);
            if (fps - p.fps).abs() < 0.01 {
                return Some(p);
            }
        }
        Some(FrameRate { base: fps.round().max(1.0) as u32, fps, drop: false })
    }

    /// From Dorico's play options: `projectFrameRate` (`k24`, `k25`, `k2997`, `k23976` …) and
    /// `useDropFormat`. Digits after the `k` are read as a rate between 20 and 130 fps
    /// (`2997` -> 29.97, `23976` -> 23.976); a name containing "Drop"/"DF" also means drop frame.
    pub fn from_dorico(option: &str, use_drop: bool) -> Option<FrameRate> {
        let digits: String = option.chars().filter(char::is_ascii_digit).collect();
        let mut x: f64 = digits.parse().ok()?;
        while x >= 130.0 {
            x /= 10.0;
        }
        let lower = option.to_ascii_lowercase();
        let drop = use_drop || lower.contains("drop") || lower.ends_with("df");
        let r = FrameRate::from_fps(x)?;
        Some(if r.fps != r.base as f64 { FrameRate::pulled(r.base, drop) } else { r })
    }

    /// Dorico's label: "25 fps", "29.97 dfps", "23.976 fps".
    pub fn label(&self) -> String {
        let n = if self.fps == self.base as f64 {
            self.base.to_string()
        } else {
            let s = format!("{:.3}", self.fps);
            s.trim_end_matches('0').trim_end_matches('.').to_owned()
        };
        format!("{n} {}", if self.drop { "dfps" } else { "fps" })
    }

    fn dropped_per_minute(&self) -> i64 {
        if self.drop { (self.base / 15) as i64 } else { 0 }
    }

    /// Seconds -> frame count from zero (nearest frame).
    pub fn frames(&self, secs: f64) -> i64 {
        (secs * self.fps).round() as i64
    }

    /// Frame count -> seconds.
    pub fn seconds(&self, frames: i64) -> f64 {
        frames as f64 / self.fps
    }

    /// Frame count -> "HH:MM:SS:FF" (drop frame: "HH:MM:SS;FF"); negative counts get a "-".
    pub fn format_frames(&self, frames: i64) -> String {
        let sign = if frames < 0 { "-" } else { "" };
        let mut n = frames.abs();
        let base = self.base as i64;
        let drop = self.dropped_per_minute();
        if drop > 0 {
            let per_10min = base * 600 - drop * 9;
            let per_min = base * 60 - drop;
            let (d, m) = (n / per_10min, n % per_10min);
            n += drop * 9 * d + if m > drop { drop * ((m - drop) / per_min) } else { 0 };
        }
        let (secs, ff) = (n / base, n % base);
        let sep = if self.drop { ';' } else { ':' };
        format!("{sign}{:02}:{:02}:{:02}{sep}{:02}", secs / 3600, secs / 60 % 60, secs % 60, ff)
    }

    /// Seconds -> timecode text at this rate.
    pub fn format(&self, secs: f64) -> String {
        self.format_frames(self.frames(secs))
    }

    /// "HH:MM:SS:FF" or "HH:MM:SS;FF" (also "." or "," before the frames) -> frame count.
    /// `None` if the text is malformed or names a frame number drop frame skips.
    pub fn parse(&self, text: &str) -> Option<i64> {
        let t = text.trim();
        let (neg, t) = match t.strip_prefix('-') {
            Some(r) => (true, r),
            None => (false, t),
        };
        let parts: Vec<i64> =
            t.split([':', ';', '.', ',']).map(|p| p.parse().ok()).collect::<Option<Vec<i64>>>()?;
        let [hh, mm, ss, ff] = parts[..] else { return None };
        let base = self.base as i64;
        if mm >= 60 || ss >= 60 || ff >= base || hh < 0 || mm < 0 || ss < 0 || ff < 0 {
            return None;
        }
        let drop = self.dropped_per_minute();
        if drop > 0 && ss == 0 && ff < drop && mm % 10 != 0 {
            return None;
        }
        let minutes = hh * 60 + mm;
        let n = ((hh * 3600 + mm * 60 + ss) * base + ff) - drop * (minutes - minutes / 10);
        Some(if neg { -n } else { n })
    }
}

impl fmt::Display for FrameRate {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.label())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn whole_rates() {
        let r = FrameRate::whole(25);
        assert_eq!(r.format(3661.5), "01:01:01:13");
        assert_eq!(r.parse("01:01:01:13"), Some(r.frames(3661.5)));
        assert_eq!(r.format(-1.0), "-00:00:01:00");
        assert_eq!(r.label(), "25 fps");
    }

    #[test]
    fn pulled_down_rates_count_on_their_base() {
        let r = FrameRate::pulled(24, false);
        assert_eq!(r.label(), "23.976 fps");
        // one hour of real time is 86,314 frames at 23.976: 59:56:13 counted at 24
        assert_eq!(r.frames(3600.0), 86314);
        assert_eq!(r.format(3600.0), "00:59:56:10");
        let n = FrameRate::pulled(30, false);
        assert_eq!(n.format(3600.0), "00:59:56:12");
    }

    #[test]
    fn drop_frame_2997() {
        let r = FrameRate::pulled(30, true);
        assert_eq!(r.label(), "29.97 dfps");
        // one real hour of 29.97 DF reads 01:00:00;00 (the point of drop frame)
        assert_eq!(r.format_frames(107892), "01:00:00;00");
        assert_eq!(r.format_frames(1799), "00:00:59;29");
        assert_eq!(r.format_frames(1800), "00:01:00;02"); // ;00 and ;01 skipped
        assert_eq!(r.format_frames(17982), "00:10:00;00"); // tenth minute keeps them
        assert_eq!(r.parse("00:01:00;02"), Some(1800));
        assert_eq!(r.parse("00:01:00;00"), None);
        assert_eq!(r.parse("00:10:00;00"), Some(17982));
        for n in [0, 1, 1799, 1800, 1801, 17981, 17982, 17983, 107891, 107892, 250_000] {
            assert_eq!(r.parse(&r.format_frames(n)), Some(n), "{n}");
        }
    }

    #[test]
    fn drop_frame_5994() {
        let r = FrameRate::pulled(60, true);
        assert_eq!(r.format_frames(3599), "00:00:59;59");
        assert_eq!(r.format_frames(3600), "00:01:00;04");
        assert_eq!(r.format_frames(215784), "01:00:00;00");
        for n in [0, 3599, 3600, 35964, 35965, 215784] {
            assert_eq!(r.parse(&r.format_frames(n)), Some(n), "{n}");
        }
    }

    #[test]
    fn drop_only_where_smpte_defines_it() {
        assert!(!FrameRate::pulled(24, true).drop);
        assert!(!FrameRate::from_dorico("k25", true).unwrap().drop);
        assert!(FrameRate::from_dorico("k2997", true).unwrap().drop);
    }

    #[test]
    fn dorico_option_names() {
        assert_eq!(FrameRate::from_dorico("k24", false), Some(FrameRate::whole(24)));
        assert_eq!(FrameRate::from_dorico("k25", false), Some(FrameRate::whole(25)));
        assert_eq!(FrameRate::from_dorico("k2997", false), Some(FrameRate::pulled(30, false)));
        assert_eq!(FrameRate::from_dorico("k23976", false), Some(FrameRate::pulled(24, false)));
        assert_eq!(FrameRate::from_dorico("k2398", false), Some(FrameRate::pulled(24, false)));
        assert_eq!(FrameRate::from_dorico("k5994Drop", false), Some(FrameRate::pulled(60, true)));
        assert_eq!(FrameRate::from_dorico("", false), None);
        for r in FrameRate::STANDARD {
            assert_eq!(FrameRate::from_fps(r.fps).map(|x| (x.base, x.fps)), Some((r.base, r.fps)));
        }
    }
}
