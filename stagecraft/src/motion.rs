//! How VSS2's reflections move over time (the user's question 2026-11-01: what would adding
//! that motion back to a captured, static replacement cost, and what would it add?).
//!
//! A click every `every` seconds (mono, into both inputs) runs through VSS2 for `secs`; each
//! click's response is cut out. The direct sound is fixed, so it is left out: the comparison
//! is of the reflections (from `REFL_FROM_MS` after the click). For each time gap the mean
//! correlation between click responses that far apart says how much of the reflection
//! pattern survives (1 = unchanged, 0 = unrelated); per octave at the shortest gap it says
//! whether the motion is a re-randomisation (all bands alike) or a pitch/delay modulation
//! (high bands decorrelate first). A second load of VSS2 gives the "unrelated" baseline.

use crate::audio::{self, Chans};
use crate::capture::{Rig, SR};
use anyhow::Result;
use serde::Serialize;
use std::path::Path;

/// Reflections compared from here (ms after the click, after the latency): past the direct
/// sound and its filters (≤ ~10 ms).
const REFL_FROM_MS: f64 = 12.0;
const REFL_TO_MS: f64 = 300.0;

#[derive(Debug, Serialize)]
pub struct Motion {
    pub clicks: usize,
    pub every_s: f64,
    /// (gap s, mean correlation of the reflections, mean residual dB) for growing gaps.
    pub by_gap: Vec<(f64, f64, f64)>,
    /// Correlation per octave (centre Hz) at the shortest gap.
    pub by_band: Vec<(f64, f64)>,
    /// Correlation per octave at the longest gap.
    pub by_band_long: Vec<(f64, f64)>,
    /// Each click of this load vs the same click of a second load: mean correlation.
    pub between_loads: f64,
    /// Reflection energy click to click: standard deviation, dB.
    pub energy_sd_db: f64,
    /// Direct sound click to click: worst residual, dB (fixed if very low).
    pub direct_residual_db: f64,
    /// Steady tones through VSS2, tracked in 10 ms blocks: per tone, how much the output wobbles.
    pub tones: Vec<Wobble>,
}

/// A steady tone through VSS2: its output as a complex amplitude per 10 ms block. The direct
/// sound adds a constant; the moving reflections make it wobble.
#[derive(Debug, Serialize)]
pub struct Wobble {
    pub hz: f64,
    /// Wobble energy relative to the steady part, dB.
    pub wobble_db: f64,
    /// Peak-to-peak level change of the output, dB.
    pub level_pp_db: f64,
    /// Strongest wobble rates (Hz) with their level relative to the steady part (dB).
    pub rates: Vec<(f64, f64)>,
}

/// VSS2 fades in after loading (the first click comes out at half level): skip this much.
const SETTLE_S: f64 = 1.0;

fn corr(a: &[f64], b: &[f64]) -> f64 {
    let (ab, aa, bb) = a.iter().zip(b).fold((0.0, 0.0, 0.0), |(x, y, z), (p, q)| (x + p * q, y + p * p, z + q * q));
    ab / (aa * bb).sqrt().max(1e-30)
}

fn band_corr(a: &[f64], b: &[f64]) -> Vec<(f64, f64)> {
    let n = a.len().next_power_of_two();
    let (sa, sb) = (audio::spectrum(a, n), audio::spectrum(b, n));
    [125.0, 250.0, 500.0, 1000.0, 2000.0, 4000.0, 8000.0, 16000.0]
        .iter()
        .map(|&fc: &f64| {
            let (lo, hi) = ((fc / 2f64.sqrt() * n as f64 / SR) as usize, ((fc * 2f64.sqrt()).min(SR / 2.0) * n as f64 / SR) as usize);
            let (mut x, mut ea, mut eb) = (0.0, 0.0, 0.0);
            for k in lo.max(1)..=hi.min(n / 2) {
                x += sa[k].re * sb[k].re + sa[k].im * sb[k].im;
                ea += sa[k].norm2();
                eb += sb[k].norm2();
            }
            (fc, x / (ea * eb).sqrt().max(1e-30))
        })
        .collect()
}

/// Runs the click train through VSS2 (`state`), twice (two loads), in folder `d`.
pub fn motion(rig: &Rig, state: &Path, d: &Path, secs: f64, every: f64) -> Result<Motion> {
    std::fs::create_dir_all(d)?;
    let (step, pre) = ((every * SR) as usize, (0.1 * SR) as usize);
    let clicks = (secs / every) as usize;
    let n = pre + clicks * step;
    let mut x = vec![0.0; n];
    for k in 0..clicks {
        x[pre + k * step] = 0.5;
    }
    let input = d.join("clicks.wav");
    audio::write_wav(&input, &[x.clone(), x], SR as u32)?;
    let (y, lat) = rig.run(state, &input, &d.join("clicks-vss2.wav"))?;
    let (y2, lat2) = rig.run(state, &input, &d.join("clicks-vss2-again.wav"))?;
    let at = |ms: f64| (ms * SR / 1000.0) as usize;
    let cut = |y: &Chans, lat: usize, k: usize, from: f64, to: f64| -> Vec<f64> {
        let s = pre + k * step + lat;
        y.iter().flat_map(|c| c[(s + at(from)).min(c.len())..(s + at(to)).min(c.len())].to_vec()).collect()
    };
    let k0 = (SETTLE_S / every).ceil() as usize;
    let refl: Vec<Vec<f64>> = (0..clicks).map(|k| cut(&y, lat, k, REFL_FROM_MS, REFL_TO_MS.min(every * 1000.0 - 5.0))).collect();
    let direct: Vec<Vec<f64>> = (0..clicks).map(|k| cut(&y, lat, k, -4.0, REFL_FROM_MS)).collect();
    let (refl, direct) = (refl[k0..].to_vec(), direct[k0..].to_vec());
    let other: Vec<Vec<f64>> = (k0..clicks).map(|k| cut(&y2, lat2, k, REFL_FROM_MS, REFL_TO_MS.min(every * 1000.0 - 5.0))).collect();
    let clicks = clicks - k0;
    let mut gaps = vec![];
    let mut g = 1;
    while g < clicks {
        gaps.push(g);
        g *= 2;
    }
    let by_gap = gaps
        .iter()
        .map(|&g| {
            let pairs: Vec<(f64, f64)> = (0..clicks - g).map(|k| (corr(&refl[k], &refl[k + g]), audio::residual_db(&refl[k], &refl[k + g]))).collect();
            let m = pairs.len() as f64;
            (g as f64 * every, pairs.iter().map(|p| p.0).sum::<f64>() / m, pairs.iter().map(|p| p.1).sum::<f64>() / m)
        })
        .collect();
    let mean_bands = |g: usize| -> Vec<(f64, f64)> {
        let all: Vec<Vec<(f64, f64)>> = (0..clicks - g).map(|k| band_corr(&refl[k], &refl[k + g])).collect();
        (0..all[0].len()).map(|i| (all[0][i].0, all.iter().map(|b| b[i].1).sum::<f64>() / all.len() as f64)).collect()
    };
    let energies: Vec<f64> = refl.iter().map(|r| audio::db(audio::energy(r))).collect();
    let mean = energies.iter().sum::<f64>() / energies.len() as f64;
    let sd = (energies.iter().map(|e| (e - mean).powi(2)).sum::<f64>() / energies.len() as f64).sqrt();
    let tones = tones(rig, state, d, secs)?;
    Ok(Motion {
        clicks,
        every_s: every,
        by_gap,
        by_band: mean_bands(1),
        by_band_long: mean_bands(*gaps.last().unwrap_or(&1)),
        between_loads: refl.iter().zip(&other).map(|(a, b)| corr(a, b)).sum::<f64>() / clicks as f64,
        energy_sd_db: sd,
        direct_residual_db: (1..clicks).map(|k| audio::residual_db(&direct[0], &direct[k])).fold(f64::MIN, f64::max),
        tones,
    })
}

/// Two steady tones (4 and 8 kHz, both inputs) through VSS2 for `secs`, demodulated in 10 ms
/// blocks (whole cycles of both tones, so they don't leak into each other).
fn tones(rig: &Rig, state: &Path, d: &Path, secs: f64) -> Result<Vec<Wobble>> {
    let hz = [4000.0, 8000.0];
    let n = (secs * SR) as usize;
    let x: Vec<f64> = (0..n).map(|i| hz.iter().map(|f| 0.1 * (2.0 * std::f64::consts::PI * f * i as f64 / SR).sin()).sum()).collect();
    let input = d.join("tones.wav");
    audio::write_wav(&input, &[x.clone(), x], SR as u32)?;
    let (y, lat) = rig.run(state, &input, &d.join("tones-vss2.wav"))?;
    let blk = (0.01 * SR) as usize;
    let skip = lat + (SETTLE_S * SR) as usize;
    let nb = (n.saturating_sub(skip)) / blk;
    let mut out = vec![];
    for f in hz {
        let w = 2.0 * std::f64::consts::PI * f / SR;
        let z: Vec<(f64, f64)> = (0..nb)
            .map(|b| {
                let (mut re, mut im) = (0.0, 0.0);
                for i in 0..blk {
                    let t = skip + b * blk + i;
                    re += y[0][t] * (w * t as f64).cos();
                    im -= y[0][t] * (w * t as f64).sin();
                }
                (re / blk as f64, im / blk as f64)
            })
            .collect();
        let m = z.iter().fold((0.0, 0.0), |a, v| (a.0 + v.0, a.1 + v.1));
        let m = (m.0 / nb as f64, m.1 / nb as f64);
        let steady = m.0 * m.0 + m.1 * m.1;
        let var = z.iter().map(|v| (v.0 - m.0).powi(2) + (v.1 - m.1).powi(2)).sum::<f64>() / nb as f64;
        let lv: Vec<f64> = z.iter().map(|v| audio::db(v.0 * v.0 + v.1 * v.1)).collect();
        let (lo, hi) = (lv.iter().cloned().fold(f64::MAX, f64::min), lv.iter().cloned().fold(f64::MIN, f64::max));
        // wobble spectrum: block rate 100 Hz
        let nf = nb.next_power_of_two() * 2;
        let mut a = vec![audio::C::default(); nf];
        for (o, v) in a.iter_mut().zip(&z) {
            *o = audio::C { re: v.0 - m.0, im: v.1 - m.1 };
        }
        audio::fft(&mut a, false);
        let rate = |k: usize| if k <= nf / 2 { k as f64 } else { k as f64 - nf as f64 } * 100.0 / nf as f64;
        let pw: Vec<f64> = a.iter().map(|c| c.norm2() / (nb as f64 * nb as f64)).collect();
        let mut idx: Vec<usize> = (1..nf).filter(|&k| rate(k).abs() >= 0.05).filter(|&k| pw[k] >= pw[(k + nf - 1) % nf] && pw[k] >= pw[(k + 1) % nf]).collect();
        idx.sort_by(|p, q| pw[*q].total_cmp(&pw[*p]));
        let mut rates: Vec<(f64, f64)> = vec![];
        for k in idx {
            let r = rate(k).abs();
            if rates.iter().all(|(x, _)| (x - r).abs() > 0.1) {
                rates.push((r, audio::db(pw[k] / steady.max(1e-30))));
            }
            if rates.len() == 5 {
                break;
            }
        }
        out.push(Wobble { hz: f, wobble_db: audio::db(var / steady.max(1e-30)), level_pp_db: hi - lo, rates });
    }
    Ok(out)
}
