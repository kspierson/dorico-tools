//! E1 inventory: what a Dorico project's mixer does to place each instrument today.
//! Read-only. Joins the mixer (channels, inserts, sends) with the saved plug-in states and
//! decodes the ones that matter for placement (VSS2, Altiverb).

use crate::{altiverb, vss2};
use anyhow::{Context, Result};
use dorico_format::mixer::{self, Channel, Mixer, PluginState};
use serde::Serialize;
use std::collections::BTreeMap;
use std::fmt::Write;
use std::path::Path;

#[derive(Debug, Serialize)]
pub struct ChannelRow {
    pub rack_slot: Option<u32>,
    pub plugin: String,
    pub channel: String,
    pub kind: String,
    pub fader_db: Option<f64>,
    /// "name" / "name (off)" / "(empty)" per insert, in slot order.
    pub inserts: Vec<String>,
    /// "Fx Reverb +6.0 dB" / "Fx Reverb -6.0 dB (off)".
    pub sends: Vec<String>,
}

#[derive(Debug, Serialize)]
pub struct VssRow {
    pub rack_slot: Option<u32>,
    pub plugin: String,
    pub channel: String,
    pub insert_slot: u32,
    pub send: String,
    pub vss: vss2::Vss2,
}

#[derive(Debug, Serialize)]
pub struct ReverbRow {
    pub channel: String,
    pub insert_slot: u32,
    pub enabled: bool,
    pub altiverb: altiverb::Altiverb,
}

#[derive(Debug, Serialize)]
pub struct Inventory {
    pub project: String,
    pub rack: BTreeMap<String, u32>,
    pub channels: Vec<ChannelRow>,
    pub vss2: Vec<VssRow>,
    pub altiverbs: Vec<ReverbRow>,
    /// States whose insert slot is empty (Dorico shows nothing there).
    pub leftovers: Vec<String>,
    /// Further outputs of multi-output plug-ins with nothing changed (no inserts, default
    /// fader, default send).
    pub default_outputs: usize,
    /// Inserts with no saved settings (empty state record or none).
    pub no_state: Vec<String>,
    /// The fader most instrument outputs share (dB); None = not stored (0 dB).
    pub usual_fader_db: Option<f64>,
    /// The send state most instrument outputs share, e.g. "+0.0 dB (on)".
    pub usual_send: Option<String>,
}

fn sends(m: &Mixer, c: &Channel) -> Vec<String> {
    let fx: Vec<&Channel> = m.fx_channels().collect();
    c.sends
        .iter()
        .filter(|s| s.enabled || s.gain.is_some_and(|g| g != 1.0))
        .map(|s| {
            let to = fx.get(s.slot as usize - 1).map_or(format!("send {}", s.slot), |f| f.name.clone());
            let g = s.gain.map_or(String::new(), |g| format!(" {:+.1} dB", mixer::db(g)));
            format!("{to}{g}{}", if s.enabled { "" } else { " (off)" })
        })
        .collect()
}

pub fn inventory(path: &Path) -> Result<Inventory> {
    let p = dorico_format::Project::read(path)?;
    let e = p.get(dorico_format::container::ENGINE_DATA).context("no playback data (enginedata)")?;
    let m = mixer::read_mixer(&e.data).context("unrecognised enginedata layout")?;
    let states: Vec<PluginState> = mixer::plugin_states(&e.data);
    let by_owner: BTreeMap<u64, &PluginState> = states.iter().map(|s| (s.owner, s)).collect();

    let mut inv = Inventory {
        project: path.file_name().map_or(String::new(), |f| f.to_string_lossy().into_owned()),
        rack: BTreeMap::new(),
        channels: vec![],
        vss2: vec![],
        altiverbs: vec![],
        leftovers: vec![],
        default_outputs: 0,
        no_state: vec![],
        usual_fader_db: None,
        usual_send: None,
    };
    // the fader value most instrument outputs share is this project's default (new projects
    // store -6 dB on every channel; older ones store nothing)
    let mut counts: BTreeMap<Option<i64>, usize> = BTreeMap::new();
    for c in m.channels.iter().filter(|c| c.kind == "instrument-return") {
        *counts.entry(c.gain.map(|g| (g * 1e6).round() as i64)).or_default() += 1;
    }
    let usual = counts.into_iter().max_by_key(|(_, n)| *n).and_then(|(g, _)| g).map(|g| g as f64 / 1e6);
    inv.usual_fader_db = usual.map(mixer::db);
    // same for sends: older projects store untouched sends as on at 0 dB, newer ones as off
    let mut sc: BTreeMap<(bool, Option<i64>), usize> = BTreeMap::new();
    for c in m.channels.iter().filter(|c| c.kind == "instrument-return") {
        for x in &c.sends {
            *sc.entry((x.enabled, x.gain.map(|g| (g * 1e6).round() as i64))).or_default() += 1;
        }
    }
    let usual_send = sc.into_iter().max_by_key(|(_, n)| *n).map(|(k, _)| k);
    inv.usual_send = usual_send.map(|(on, g)| {
        format!("{}{}", g.map_or("0 dB".into(), |g| format!("{:+.1} dB", mixer::db(g as f64 / 1e6))), if on { " (on)" } else { " (off)" })
    });
    let mut seen_slots = std::collections::HashSet::new();
    for r in &m.rack {
        *inv.rack.entry(r.name.clone()).or_default() += 1;
    }
    for c in &m.channels {
        let rack = c.instrument_id.and_then(|i| m.rack_slot(i));
        let (slot, plugin) = rack.map_or((None, String::new()), |r| (Some(r.slot), r.name.clone()));
        let send_list = sends(&m, c);
        for i in &c.inserts {
            let st = by_owner.get(&i.id).and_then(|s| s.vst2.as_ref());
            match (&i.name, st) {
                (None, Some(v)) => inv.leftovers.push(format!(
                    "{} / {}: empty slot {} holds an old {} state{}",
                    plugin_label(slot, &plugin),
                    c.name,
                    i.slot,
                    v.fx_id,
                    if v.fx_id == "Para" { vss2::parse_state(&v.chunk).map(|p| format!(" (VSS2 pin \"{}\")", vss2::Vss2::from_props(p).name)).unwrap_or_default() } else { String::new() }
                )),
                (Some(_), Some(v)) if v.fx_id == "Para" => {
                    if let Ok(p) = vss2::parse_state(&v.chunk) {
                        inv.vss2.push(VssRow {
                            rack_slot: slot,
                            plugin: plugin.clone(),
                            channel: c.name.clone(),
                            insert_slot: i.slot,
                            send: send_list.join("; "),
                            vss: vss2::Vss2::from_props(p),
                        });
                    }
                }
                (Some(_), Some(v)) if v.fx_id == "AVr5" => inv.altiverbs.push(ReverbRow {
                    channel: c.name.clone(),
                    insert_slot: i.slot,
                    enabled: i.enabled,
                    altiverb: altiverb::parse(&v.chunk),
                }),
                (Some(n), None) if by_owner.get(&i.id).is_none_or(|s| s.data.is_empty()) => {
                    inv.no_state.push(format!("{} / {}: slot {} {n}", plugin_label(slot, &plugin), c.name, i.slot))
                }
                _ => {}
            }
        }
        let named = c.inserts.iter().any(|i| i.name.is_some());
        // a send Dorico created and nobody touched: on, gain 1.0, no `enabled` attribute
        let default_sends = c.sends.iter().all(|x| Some((x.enabled, x.gain.map(|g| (g * 1e6).round() as i64))) == usual_send);
        let main_output = rack.is_some_and(|r| seen_slots.insert(r.id));
        let moved = c.gain.map(|g| (g * 1e6).round()) != usual.map(|g| (g * 1e6).round());
        if c.kind != "instrument-return" || named || !default_sends || moved || main_output {
            let mut ins: Vec<_> = c.inserts.iter().collect();
            ins.sort_by_key(|i| (i.post_fader, i.slot));
            inv.channels.push(ChannelRow {
                rack_slot: slot,
                plugin,
                channel: c.name.clone(),
                kind: c.kind.clone(),
                fader_db: c.gain.map(mixer::db),
                inserts: ins
                    .iter()
                    .map(|i| match &i.name {
                        None => format!("{}: (empty)", i.slot),
                        Some(n) => format!("{}{}: {n}{}", if i.post_fader { "post " } else { "" }, i.slot, if i.enabled { "" } else { " (off)" }),
                    })
                    .collect(),
                sends: send_list,
            });
        } else {
            inv.default_outputs += 1;
        }
    }
    inv.vss2.sort_by(|a, b| a.vss.y.total_cmp(&b.vss.y).then(a.vss.x.total_cmp(&b.vss.x)));
    Ok(inv)
}

fn plugin_label(slot: Option<u32>, plugin: &str) -> String {
    slot.map_or(plugin.to_string(), |s| format!("{plugin} (rack {s})"))
}

fn opt(v: Option<f64>) -> String {
    v.map_or("–".into(), |x| format!("{x:.4}").trim_end_matches('0').trim_end_matches('.').to_string())
}

/// Markdown report.
pub fn markdown(inv: &Inventory) -> String {
    let mut s = String::new();
    let _ = writeln!(s, "## {}\n", inv.project);
    let rack: Vec<String> = inv.rack.iter().map(|(n, c)| format!("{n} ×{c}")).collect();
    let _ = writeln!(s, "**Rack:** {}\n", rack.join(", "));

    let _ = writeln!(
        s,
        "**Channels**: buses, each rack slot's main output, and any output with inserts, a changed send or a moved fader. \
         {} further outputs are untouched (no inserts, usual fader, usual send). Usual fader: {}; usual send: {} \
         (\"on\" = stored without `enabled=\"0\"`, confirmed in Dorico). \
         No pan is stored anywhere.\n",
        inv.default_outputs,
        inv.usual_fader_db.map_or("0 dB (not stored)".into(), |d| format!("{d:+.1} dB")),
        inv.usual_send.as_deref().unwrap_or("none")
    );
    let _ = writeln!(s, "| Rack | Plug-in | Channel | Kind | Fader | Inserts | Sends |\n|---|---|---|---|---|---|---|");
    for c in &inv.channels {
        let _ = writeln!(
            s,
            "| {} | {} | {} | {} | {} | {} | {} |",
            c.rack_slot.map_or(String::new(), |x| x.to_string()),
            c.plugin,
            c.channel,
            c.kind,
            c.fader_db.map_or("0 dB".into(), |d| format!("{d:+.1} dB")),
            c.inserts.join("<br>"),
            c.sends.join("<br>")
        );
    }

    if !inv.altiverbs.is_empty() {
        let _ = writeln!(s, "\n**Altiverb**\n\n| Channel | Slot | Settings |\n|---|---|---|");
        for a in &inv.altiverbs {
            let _ = writeln!(s, "| {} | {}{} | {} |", a.channel, a.insert_slot, if a.enabled { "" } else { " (off)" }, a.altiverb.summary());
        }
    }

    if !inv.vss2.is_empty() {
        let rooms: std::collections::BTreeSet<String> =
            inv.vss2.iter().filter(|r| r.vss.room_id.is_some()).map(|r| format!("room id {}, level {}, dry/wet {}, seat {}", r.vss.room_id.unwrap_or(0), opt(r.vss.room_level), opt(r.vss.room_dry_wet), r.vss.room_seat.map_or("–".into(), |x| x.to_string()))).collect();
        let _ = writeln!(s, "\n**Virtual Sound Stage 2** ({} instances, front to back; x < 0 = left, y = metres back, facing 0 = toward the listener)\n", inv.vss2.len());
        let _ = writeln!(s, "Shared room settings: {}\n", rooms.into_iter().collect::<Vec<_>>().join(" | "));
        let _ = writeln!(s, "| Rack | Plug-in | Output | Pin | Preset | x | y | h | Width | Facing | ER | Direct | Gain | Air | Send |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|");
        for r in &inv.vss2 {
            let v = &r.vss;
            let _ = writeln!(
                s,
                "| {} | {} | {} | {}{} | {} | {:.2} | {:.2} | {:.1} | {} | {:.0}° | {} | {} | {} | {} | {} |",
                r.rack_slot.map_or(String::new(), |x| x.to_string()),
                r.plugin,
                r.channel,
                v.name,
                if v.bypass { " (bypassed)" } else if v.mute { " (muted)" } else { "" },
                v.preset.split("Presets\\").last().unwrap_or(&v.preset).trim_end_matches(".vss2preset"),
                v.x,
                v.y,
                v.z,
                if v.emitters > 1 { format!("{:.2}", v.width) } else { "point".into() },
                v.facing,
                opt(v.er_level),
                opt(v.direct_level),
                opt(v.gain),
                opt(v.air),
                r.send
            );
        }
    }
    if !inv.no_state.is_empty() {
        let _ = writeln!(s, "\n**Inserts with no saved settings** ({}; Dorico saved an empty state)\n", inv.no_state.len());
        for l in &inv.no_state {
            let _ = writeln!(s, "- {l}");
        }
    }
    if !inv.leftovers.is_empty() {
        let _ = writeln!(s, "\n**Leftover states** (slot empty in Dorico)\n");
        for l in &inv.leftovers {
            let _ = writeln!(s, "- {l}");
        }
    }
    s
}

/// One Markdown table row per project (use after [`summary_header`]).
pub fn summary_row(inv: &Inventory) -> String {
    let mut sets: BTreeMap<String, usize> = BTreeMap::new();
    for r in &inv.vss2 {
        let rel = r.vss.preset.split("Presets\\").last().unwrap_or("");
        let set = rel.rsplit_once('\\').map_or(rel, |(d, _)| d).to_string();
        *sets.entry(if set.is_empty() { "(none)".into() } else { set }).or_default() += 1;
    }
    let sets: Vec<String> = sets.iter().map(|(k, v)| format!("{k} ×{v}")).collect();
    let av: Vec<String> = inv
        .altiverbs
        .iter()
        .map(|a| {
            let on = |n: &str| a.altiverb.get(n).is_some_and(|v| v != 0.0);
            let parts: Vec<&str> = [("direct", "Direct On"), ("ER", "Early Reflections On"), ("tail", "Tail On")].iter().filter(|(_, n)| on(n)).map(|(l, _)| *l).collect();
            format!(
                "{}{}: {} ({}; wet {})",
                a.channel,
                if a.enabled { "" } else { " (off)" },
                a.altiverb.ir.rsplit('/').take(2).collect::<Vec<_>>().into_iter().rev().collect::<Vec<_>>().join(" "),
                parts.join("+"),
                opt(a.altiverb.get("Dry/Wet Mix"))
            )
        })
        .collect();
    let mut other: BTreeMap<String, usize> = BTreeMap::new();
    for c in &inv.channels {
        for i in &c.inserts {
            let n = i.split_once(": ").map_or(i.as_str(), |x| x.1);
            if !n.starts_with("VirtualSoundStage2") && !n.starts_with("Altiverb") && n != "(empty)" {
                *other.entry(format!("{n} on {}", c.channel)).or_default() += 1;
            }
        }
    }
    let other: Vec<String> = other.iter().map(|(k, v)| if *v > 1 { format!("{k} ×{v}") } else { k.clone() }).collect();
    format!(
        "| {} | {} | {} | {} | {} |",
        inv.project.trim_end_matches(".dorico"),
        if inv.vss2.is_empty() && inv.no_state.is_empty() { "–".into() } else { format!("{} ({})", inv.vss2.len() + inv.no_state.iter().filter(|x| x.contains("VirtualSoundStage")).count(), sets.join(", ")) },
        av.join("<br>"),
        other.join("<br>"),
        inv.rack.iter().filter(|(k, _)| *k != "DoricoBeep").map(|(k, v)| format!("{k} ×{v}")).collect::<Vec<_>>().join(", ")
    )
}

pub fn summary_header() -> &'static str {
    "| Project | VSS2 instances (preset sets) | Altiverb (channel: IR (parts on; wet)) | Other inserts | Rack |\n|---|---|---|---|---|"
}
