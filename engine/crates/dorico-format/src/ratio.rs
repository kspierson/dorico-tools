//! Exact fractions, as Dorico stores positions and durations ("81/4").
//! Formatting matches Python's `fractions.Fraction` (used by the prototype).

use serde::{Serialize, Serializer};
use std::cmp::Ordering;
use std::fmt;
use std::ops::{Add, Div, Mul, Sub};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct Ratio {
    n: i128,
    d: i128, // always > 0
}

fn gcd(mut a: i128, mut b: i128) -> i128 {
    a = a.abs();
    b = b.abs();
    while b != 0 {
        (a, b) = (b, a % b);
    }
    a.max(1)
}

/// Ticks per crotchet in Dorico's played offsets (`kEventPlayStartOffset` etc., confirmed by
/// dorico-hp test H) and in the MIDI dorico-hp renders.
pub const TICKS_PER_CROTCHET: i128 = 480;

impl Ratio {
    /// Crotchets -> ticks, rounded to the nearest tick; halves go to the even tick, like
    /// Python's `round()` (which dorico-hp uses), so ported code gives the same numbers.
    pub fn to_ticks(&self) -> i128 {
        let n = self.n * TICKS_PER_CROTCHET;
        let q = n.div_euclid(self.d);
        let r = n.rem_euclid(self.d);
        if 2 * r > self.d || (2 * r == self.d && q % 2 != 0) { q + 1 } else { q }
    }

    pub fn from_ticks(t: i128) -> Ratio {
        Ratio::new(t, TICKS_PER_CROTCHET)
    }

    pub const ZERO: Ratio = Ratio { n: 0, d: 1 };
    pub const ONE: Ratio = Ratio { n: 1, d: 1 };

    pub fn new(n: i128, d: i128) -> Ratio {
        assert!(d != 0, "zero denominator");
        let s = if d < 0 { -1 } else { 1 };
        let g = gcd(n, d);
        Ratio { n: s * n / g, d: s * d / g }
    }

    pub fn int(n: i128) -> Ratio {
        Ratio { n, d: 1 }
    }

    /// Parse "3", "-1/2", "81/4" or a decimal like "1.5". Invalid -> 0
    /// (matches the prototype's lenient `frac()`).
    pub fn parse(s: &str) -> Ratio {
        Self::try_parse(s).unwrap_or(Ratio::ZERO)
    }

    pub fn try_parse(s: &str) -> Option<Ratio> {
        let s = s.trim();
        if s.is_empty() {
            return Some(Ratio::ZERO);
        }
        if let Some((a, b)) = s.split_once('/') {
            let d: i128 = b.trim().parse().ok()?;
            if d == 0 {
                return None;
            }
            return Some(Ratio::new(a.trim().parse().ok()?, d));
        }
        if let Some((whole, frac)) = s.split_once('.') {
            if frac.len() > 18 || !frac.chars().all(|c| c.is_ascii_digit()) {
                return None;
            }
            let neg = whole.starts_with('-');
            let w: i128 = if whole.is_empty() || whole == "-" { 0 } else { whole.parse().ok()? };
            let scale = 10i128.pow(frac.len() as u32);
            let f: i128 = if frac.is_empty() { 0 } else { frac.parse().ok()? };
            let n = w.abs() * scale + f;
            return Some(Ratio::new(if neg { -n } else { n }, scale));
        }
        Some(Ratio::int(s.parse().ok()?))
    }

    pub fn numer(&self) -> i128 {
        self.n
    }

    pub fn denom(&self) -> i128 {
        self.d
    }

    pub fn is_zero(&self) -> bool {
        self.n == 0
    }

    pub fn floor(&self) -> i128 {
        self.n.div_euclid(self.d)
    }

    pub fn ceil(&self) -> i128 {
        -(-*self).floor()
    }

    /// Integer part, truncated toward zero (Python `int(fraction)`).
    pub fn trunc(&self) -> i128 {
        self.n / self.d
    }

    pub fn to_f64(&self) -> f64 {
        self.n as f64 / self.d as f64
    }
}

impl std::ops::Neg for Ratio {
    type Output = Ratio;
    fn neg(self) -> Ratio {
        Ratio { n: -self.n, d: self.d }
    }
}

impl Add for Ratio {
    type Output = Ratio;
    fn add(self, o: Ratio) -> Ratio {
        Ratio::new(self.n * o.d + o.n * self.d, self.d * o.d)
    }
}

impl Sub for Ratio {
    type Output = Ratio;
    fn sub(self, o: Ratio) -> Ratio {
        Ratio::new(self.n * o.d - o.n * self.d, self.d * o.d)
    }
}

impl Mul for Ratio {
    type Output = Ratio;
    fn mul(self, o: Ratio) -> Ratio {
        Ratio::new(self.n * o.n, self.d * o.d)
    }
}

impl Div for Ratio {
    type Output = Ratio;
    fn div(self, o: Ratio) -> Ratio {
        Ratio::new(self.n * o.d, self.d * o.n)
    }
}

impl PartialOrd for Ratio {
    fn partial_cmp(&self, o: &Ratio) -> Option<Ordering> {
        Some(self.cmp(o))
    }
}

impl Ord for Ratio {
    fn cmp(&self, o: &Ratio) -> Ordering {
        (self.n * o.d).cmp(&(o.n * self.d))
    }
}

impl fmt::Display for Ratio {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        if self.d == 1 { write!(f, "{}", self.n) } else { write!(f, "{}/{}", self.n, self.d) }
    }
}

impl Serialize for Ratio {
    fn serialize<S: Serializer>(&self, s: S) -> Result<S::Ok, S::Error> {
        s.collect_str(self)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_and_ops() {
        assert_eq!(Ratio::parse("81/4"), Ratio::new(81, 4));
        assert_eq!(Ratio::parse("1.5"), Ratio::new(3, 2));
        assert_eq!(Ratio::parse("-1/2").to_string(), "-1/2");
        assert_eq!(Ratio::parse("6/3").to_string(), "2");
        assert_eq!((Ratio::parse("7/2") - Ratio::int(4)).floor(), -1);
        assert_eq!(Ratio::parse("7/2").ceil(), 4);
        assert!(Ratio::parse("1/3") < Ratio::parse("1/2"));
        assert_eq!(Ratio::parse("3/2").to_ticks(), 720);
        assert_eq!(Ratio::new(1, 7).to_ticks(), 69); // 68.57 -> 69
        assert_eq!(Ratio::new(-1, 960).to_ticks(), 0); // round(-0.5) == 0 in Python
        assert_eq!(Ratio::new(3, 960).to_ticks(), 2); // round(1.5) == 2
        assert_eq!(Ratio::new(5, 960).to_ticks(), 2); // round(2.5) == 2
        assert_eq!(Ratio::from_ticks(240), Ratio::new(1, 2));
    }
}
