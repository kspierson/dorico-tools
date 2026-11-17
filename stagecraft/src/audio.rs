//! Audio helpers for capturing and measuring: WAV I/O, FFT, exponential sine sweeps,
//! deconvolution, convolution and impulse-response measurements. Standard library only.

use anyhow::{Context, Result, bail};
use std::f64::consts::PI;
use std::io::Write;
use std::path::Path;

/// Channels of samples (one Vec per channel).
pub type Chans = Vec<Vec<f64>>;

// ---------------------------------------------------------------- WAV

/// Read a WAV (PCM 16/24/32-bit or 32/64-bit float). Returns (sample rate, channels).
pub fn read_wav(path: &Path) -> Result<(u32, Chans)> {
    let b = std::fs::read(path).with_context(|| format!("reading {}", path.display()))?;
    if b.len() < 12 || &b[..4] != b"RIFF" || &b[8..12] != b"WAVE" {
        bail!("{}: not a WAV file", path.display());
    }
    let u16_at = |p: usize| u16::from_le_bytes([b[p], b[p + 1]]);
    let u32_at = |p: usize| u32::from_le_bytes(b[p..p + 4].try_into().unwrap());
    let (mut fmt, mut data) = (None, None);
    let mut p = 12;
    while p + 8 <= b.len() {
        let len = u32_at(p + 4) as usize;
        let body = p + 8..(p + 8 + len).min(b.len());
        match &b[p..p + 4] {
            b"fmt " => fmt = Some(body),
            b"data" => data = Some(body),
            _ => {}
        }
        p += 8 + len + (len & 1);
    }
    let (f, d) = (fmt.context("no fmt chunk")?, data.context("no data chunk")?);
    let mut format = u16_at(f.start);
    let (nc, sr, bits) = (u16_at(f.start + 2) as usize, u32_at(f.start + 4), u16_at(f.start + 14));
    if format == 0xFFFE && f.len() >= 26 {
        format = u16_at(f.start + 24);
    }
    let w = bits as usize / 8;
    if nc == 0 || !matches!((format, bits), (1, 16) | (1, 24) | (1, 32) | (3, 32) | (3, 64)) {
        bail!("{}: unsupported WAV format {format}/{bits} bits", path.display());
    }
    let frames = d.len() / (w * nc);
    let mut out = vec![Vec::with_capacity(frames); nc];
    for i in 0..frames {
        for (c, o) in out.iter_mut().enumerate() {
            let q = d.start + (i * nc + c) * w;
            o.push(match (format, bits) {
                (3, 32) => f32::from_le_bytes(b[q..q + 4].try_into().unwrap()) as f64,
                (3, _) => f64::from_le_bytes(b[q..q + 8].try_into().unwrap()),
                (_, 16) => i16::from_le_bytes([b[q], b[q + 1]]) as f64 / 32768.0,
                (_, 24) => (i32::from_le_bytes([0, b[q], b[q + 1], b[q + 2]]) >> 8) as f64 / 8_388_608.0,
                _ => i32::from_le_bytes(b[q..q + 4].try_into().unwrap()) as f64 / 2_147_483_648.0,
            });
        }
    }
    Ok((sr, out))
}

/// Write 32-bit float WAV.
pub fn write_wav(path: &Path, chans: &[Vec<f64>], sr: u32) -> Result<()> {
    let n = chans.iter().map(Vec::len).max().unwrap_or(0);
    let nc = chans.len() as u16;
    let data_len = (n * chans.len() * 4) as u32;
    let mut f = std::io::BufWriter::new(std::fs::File::create(path).with_context(|| format!("creating {}", path.display()))?);
    f.write_all(b"RIFF")?;
    f.write_all(&(36 + data_len).to_le_bytes())?;
    f.write_all(b"WAVEfmt ")?;
    f.write_all(&16u32.to_le_bytes())?;
    f.write_all(&3u16.to_le_bytes())?;
    f.write_all(&nc.to_le_bytes())?;
    f.write_all(&sr.to_le_bytes())?;
    f.write_all(&(sr * nc as u32 * 4).to_le_bytes())?;
    f.write_all(&(nc * 4).to_le_bytes())?;
    f.write_all(&32u16.to_le_bytes())?;
    f.write_all(b"data")?;
    f.write_all(&data_len.to_le_bytes())?;
    for i in 0..n {
        for c in chans {
            f.write_all(&(c.get(i).copied().unwrap_or(0.0) as f32).to_le_bytes())?;
        }
    }
    Ok(())
}

// ---------------------------------------------------------------- FFT

#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct C {
    pub re: f64,
    pub im: f64,
}

impl C {
    fn mul(self, o: C) -> C {
        C { re: self.re * o.re - self.im * o.im, im: self.re * o.im + self.im * o.re }
    }
    pub fn conj(self) -> C {
        C { re: self.re, im: -self.im }
    }
    pub fn norm2(self) -> f64 {
        self.re * self.re + self.im * self.im
    }
}

/// In-place radix-2 FFT; `inverse` also scales by 1/n. `a.len()` must be a power of two.
pub fn fft(a: &mut [C], inverse: bool) {
    let n = a.len();
    assert!(n.is_power_of_two());
    let mut j = 0;
    for i in 1..n {
        let mut bit = n >> 1;
        while j & bit != 0 {
            j ^= bit;
            bit >>= 1;
        }
        j |= bit;
        if i < j {
            a.swap(i, j);
        }
    }
    let mut len = 2;
    while len <= n {
        let ang = 2.0 * PI / len as f64 * if inverse { 1.0 } else { -1.0 };
        let wl = C { re: ang.cos(), im: ang.sin() };
        for start in (0..n).step_by(len) {
            let mut w = C { re: 1.0, im: 0.0 };
            for k in 0..len / 2 {
                let u = a[start + k];
                let v = a[start + k + len / 2].mul(w);
                a[start + k] = C { re: u.re + v.re, im: u.im + v.im };
                a[start + k + len / 2] = C { re: u.re - v.re, im: u.im - v.im };
                w = w.mul(wl);
            }
        }
        len <<= 1;
    }
    if inverse {
        for x in a.iter_mut() {
            x.re /= n as f64;
            x.im /= n as f64;
        }
    }
}

pub fn spectrum(x: &[f64], n: usize) -> Vec<C> {
    let mut a = vec![C::default(); n];
    for (o, &v) in a.iter_mut().zip(x) {
        o.re = v;
    }
    fft(&mut a, false);
    a
}

fn real_ifft(mut a: Vec<C>, len: usize) -> Vec<f64> {
    fft(&mut a, true);
    a.into_iter().take(len).map(|c| c.re).collect()
}

/// Linear convolution via FFT.
pub fn convolve(x: &[f64], h: &[f64]) -> Vec<f64> {
    if x.is_empty() || h.is_empty() {
        return vec![];
    }
    let len = x.len() + h.len() - 1;
    let n = len.next_power_of_two();
    let (a, b) = (spectrum(x, n), spectrum(h, n));
    real_ifft(a.iter().zip(&b).map(|(p, q)| p.mul(*q)).collect(), len)
}

// ---------------------------------------------------------------- sweeps

/// Exponential sine sweep (Farina) from f1 to f2 Hz over `secs`, peak `amp`, with short
/// half-Hann fades (50 ms in, 10 ms out).
pub fn sweep(sr: f64, secs: f64, f1: f64, f2: f64, amp: f64) -> Vec<f64> {
    let n = (secs * sr) as usize;
    let k = (f2 / f1).ln();
    let (fi, fo) = ((0.05 * sr) as usize, (0.01 * sr) as usize);
    (0..n)
        .map(|i| {
            let t = i as f64 / sr;
            let mut v = amp * (2.0 * PI * f1 * secs / k * ((t * k / secs).exp() - 1.0)).sin();
            if i < fi {
                v *= 0.5 - 0.5 * (PI * i as f64 / fi as f64).cos();
            }
            if n - i <= fo {
                v *= 0.5 - 0.5 * (PI * (n - i) as f64 / fo as f64).cos();
            }
            v
        })
        .collect()
}

/// Impulse response from excitation `x` and response `y` by regularised spectral division,
/// band-limited to [f1, f2]. Index 0 = no delay. Returns `len` samples.
pub fn deconvolve(x: &[f64], y: &[f64], sr: f64, f1: f64, f2: f64, len: usize) -> Vec<f64> {
    let n = (x.len() + y.len()).next_power_of_two();
    let (xs, ys) = (spectrum(x, n), spectrum(y, n));
    let peak = xs.iter().map(|c| c.norm2()).fold(0.0, f64::max);
    let h: Vec<C> = (0..n)
        .map(|i| {
            let f = i.min(n - i) as f64 * sr / n as f64;
            // full inside the sweep band, gentle roll-off over half an octave outside it
            let w = if f < f1 / 2f64.sqrt() || f > f2 * 2f64.sqrt() {
                0.0
            } else if f < f1 {
                ((f / (f1 / 2f64.sqrt())).log2() * 2.0).clamp(0.0, 1.0)
            } else if f > f2 {
                (1.0 - (f / f2).log2() * 2.0).clamp(0.0, 1.0)
            } else {
                1.0
            };
            let d = xs[i].norm2() + 1e-8 * peak;
            let q = ys[i].mul(xs[i].conj());
            C { re: q.re / d * w, im: q.im / d * w }
        })
        .collect();
    real_ifft(h, len)
}

/// Apply a true-stereo IR set (LL, LR, RL, RR) to a stereo (or mono) signal.
pub fn apply_true_stereo(x: &Chans, ir: &Chans) -> Chans {
    let (l, r) = (&x[0], x.get(1).unwrap_or(&x[0]));
    let add = |a: Vec<f64>, b: Vec<f64>| -> Vec<f64> { a.iter().zip(&b).map(|(p, q)| p + q).collect() };
    vec![add(convolve(l, &ir[0]), convolve(r, &ir[2])), add(convolve(l, &ir[1]), convolve(r, &ir[3]))]
}

/// Lag (samples) that best aligns `b` to `a` (b delayed by the lag), within ±max_lag.
pub fn best_lag(a: &[f64], b: &[f64], max_lag: usize) -> i64 {
    let n = (a.len() + b.len()).next_power_of_two();
    let (sa, sb) = (spectrum(a, n), spectrum(b, n));
    let mut x: Vec<C> = sa.iter().zip(&sb).map(|(p, q)| q.mul(p.conj())).collect();
    fft(&mut x, true);
    let at = |lag: i64| x[(lag.rem_euclid(n as i64)) as usize].re;
    (-(max_lag as i64)..=max_lag as i64).max_by(|p, q| at(*p).total_cmp(&at(*q))).unwrap_or(0)
}

// ---------------------------------------------------------------- measurements

pub fn db(x: f64) -> f64 {
    10.0 * x.max(1e-30).log10()
}

pub fn energy(x: &[f64]) -> f64 {
    x.iter().map(|v| v * v).sum()
}

/// Residual of `b` against `a`, dB relative to `a`'s energy (−∞ = identical).
pub fn residual_db(a: &[f64], b: &[f64]) -> f64 {
    let n = a.len().min(b.len());
    db(a[..n].iter().zip(&b[..n]).map(|(p, q)| (p - q) * (p - q)).sum::<f64>() / energy(&a[..n]).max(1e-30))
}

/// First sample at or above `frac` of the peak magnitude.
pub fn arrival(h: &[f64], frac: f64) -> usize {
    let pk = h.iter().fold(0.0f64, |m, v| m.max(v.abs()));
    h.iter().position(|v| v.abs() >= frac * pk).unwrap_or(0)
}

/// Energy per octave band (dB), centres 63 Hz … 16 kHz.
pub fn octave_bands(h: &[f64], sr: f64) -> Vec<(f64, f64)> {
    let n = h.len().next_power_of_two().max(8192);
    let s = spectrum(h, n);
    [63.0, 125.0, 250.0, 500.0, 1000.0, 2000.0, 4000.0, 8000.0, 16000.0]
        .iter()
        .map(|&fc: &f64| {
            let (lo, hi) = (fc / 2f64.sqrt(), (fc * 2f64.sqrt()).min(sr / 2.0));
            let (a, b) = ((lo * n as f64 / sr) as usize, (hi * n as f64 / sr) as usize);
            let e: f64 = s[a.max(1)..=b.min(n / 2)].iter().map(|c| c.norm2()).sum::<f64>() / (b - a).max(1) as f64;
            (fc, db(e))
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fft_round_trip_and_convolution() {
        let x: Vec<f64> = (0..100).map(|i| (i as f64 * 0.37).sin()).collect();
        let y = convolve(&x, &[0.0, 0.0, 0.5]);
        assert!((y[2] - 0.5 * x[0]).abs() < 1e-12 && (y[50] - 0.5 * x[48]).abs() < 1e-12);
    }

    #[test]
    fn deconvolve_recovers_a_delayed_filter() {
        let sr = 48000.0;
        let x = sweep(sr, 1.0, 20.0, 23000.0, 0.25);
        let h0 = [0.0, 0.0, 0.0, 0.8, 0.0, -0.3, 0.1];
        let y = convolve(&x, &h0);
        let h = deconvolve(&x, &y, sr, 20.0, 23000.0, 64);
        // in band the recovered filter reproduces the response
        assert!(residual_db(&y, &convolve(&x, &h)) < -30.0);
        assert_eq!(arrival(&h, 0.5), 3);
        assert!((h[3] - 0.8).abs() < 0.05 && (h[5] + 0.3).abs() < 0.05, "{:?}", &h[..8]);
    }

    #[test]
    fn wav_round_trip() {
        let p = std::env::temp_dir().join("stagecraft-wav-test.wav");
        write_wav(&p, &[vec![0.5, -0.25], vec![0.0, 1.0]], 48000).unwrap();
        let (sr, c) = read_wav(&p).unwrap();
        assert_eq!((sr, c.len(), c[0][0], c[1][1]), (48000, 2, 0.5, 1.0));
    }
}
