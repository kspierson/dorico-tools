//! A musician-readable model of a Dorico score.
//!
//! Dorico's data model (score.dtn / score.xml):
//!
//! ```text
//! flows[] ─ flowPlayers[]    player -> event streams (player stream, one per stave, one per voice)
//!         ─ eventStreams[]   type + block instances
//!         ─ blockInstances[] place a block on a stream at a position
//!         ─ blocks[]         hold events (NoteEventDefinition, ...)
//!         ─ elementTables[]  shared definitions events point to (time sigs, dynamics, ...)
//! ```
//!
//! Positions/durations are exact fractions in crotchets; pitch is MIDI (concert).
//! Ported from dorigit's Python prototype (`model.py`, retired 2026-10-30; listings were
//! identical on 32 real projects). Listings are now pinned by the golden tests.

use crate::bars::{self, Bar};
use crate::dtn::Node;
use crate::ratio::Ratio;
use crate::tree::{ElementTables as Tables, element_tables};
use serde::Serialize;
use std::collections::HashMap;

// Decoders that used to live here; they moved to `vocab` and `dynamics` (2026-10-31) and are
// re-exported so existing callers keep working. New code: use `vocab::…` / `dynamics::…`.
pub use crate::dynamics::decode_intensity;
pub use crate::vocab::{clean_value, duration_name, pitch_name};

const STANDARD_EVENT_FIELDS: &[&str] = &[
    "eventID",
    "position",
    "secondaryPosition",
    "duration",
    "secondaryEndOffset",
    "propertyTable",
    "logicalStaveIDOverride",
];
const QUIET_PROPERTIES: &[&str] = &["kNoteSpelling"];

/// Ordered string map with Python-dict semantics (re-insert keeps position).
#[derive(Debug, Clone, Default, Serialize)]
pub struct OrderedMap {
    entries: Vec<(String, String)>,
    #[serde(skip)]
    index: HashMap<String, usize>,
}

impl OrderedMap {
    pub fn insert(&mut self, k: String, v: String) {
        match self.index.get(&k) {
            Some(&i) => self.entries[i].1 = v,
            None => {
                self.index.insert(k.clone(), self.entries.len());
                self.entries.push((k, v));
            }
        }
    }
    pub fn get(&self, k: &str) -> Option<&str> {
        self.index.get(k).map(|&i| self.entries[i].1.as_str())
    }
    pub fn contains(&self, k: &str) -> bool {
        self.index.contains_key(k)
    }
    pub fn iter(&self) -> impl Iterator<Item = (&str, &str)> {
        self.entries.iter().map(|(k, v)| (k.as_str(), v.as_str()))
    }
    pub fn keys(&self) -> impl Iterator<Item = &str> {
        self.entries.iter().map(|(k, _)| k.as_str())
    }
    pub fn len(&self) -> usize {
        self.entries.len()
    }
    pub fn is_empty(&self) -> bool {
        self.entries.is_empty()
    }
}

fn leaf_summary(n: &Node, skip: &[&str], limit: usize) -> String {
    let mut parts = Vec::new();
    fn walk(x: &Node, skip: &[&str], parts: &mut Vec<String>) {
        for c in &x.children {
            if skip.contains(&&*c.tag) || &*c.tag == "propertyTable" {
                continue;
            }
            match c.value.as_deref() {
                Some(v) => {
                    if !v.is_empty() {
                        parts.push(format!("{}={}", c.tag, clean_value(v)));
                    }
                }
                None => walk(c, skip, parts),
            }
        }
    }
    walk(n, skip, &mut parts);
    if parts.len() > limit {
        parts.truncate(limit);
        parts.push("...".into());
    }
    parts.join(", ")
}

fn property_entries(n: &Node) -> &[Node] {
    n.find("propertyTable/entries").map(Node::items).unwrap_or(&[])
}

fn properties(n: &Node) -> Vec<String> {
    let mut out = Vec::new();
    for e in property_entries(n) {
        let ptype = e.text("propertyType");
        if QUIET_PROPERTIES.contains(&ptype) {
            continue;
        }
        let val = clean_value(e.text("value"));
        let scope = match e.find("context/layoutIDWithFrameChainID").and_then(|s| s.value.as_deref()) {
            Some(v) if !v.starts_with("steamVariantList:list: {int: -1}") => " (layout-specific)",
            _ => "",
        };
        out.push(format!("{}={val}{scope}", ptype.strip_prefix('k').unwrap_or(ptype)));
    }
    out.sort();
    out
}

#[derive(Debug, Clone, Serialize)]
pub struct Meter {
    pub start: Ratio,
    pub bar: i128,
    pub length: Ratio,
    pub beat: Ratio,
    pub label: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct Event {
    pub flow: String,
    pub owner: String,
    pub lane: String,
    pub kind: String,
    pub position: Ratio,
    #[serde(rename = "where")]
    pub where_: String,
    pub bar: Option<i128>,
    pub text: String,
    pub props: Vec<String>,
    pub event_id: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct Flow {
    pub flow_id: String,
    pub name: String,
    pub meters: Vec<Meter>,
    /// Attached video, as text ("clip.mov at bar 2 beat 1, clip from 00:00:06:00 …"); see `film`.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub video: Option<String>,
    pub events: Vec<Event>,
    /// Bars with Dorico's displayed numbers (pick-up = 0, bar-number changes); see `bars`.
    #[serde(skip)]
    pub bars: Vec<Bar>,
}

impl Flow {
    fn meter_at(&self, pos: Ratio) -> Option<&Meter> {
        let mut m = None;
        for cand in &self.meters {
            if cand.start <= pos {
                m = Some(cand);
            } else {
                break;
            }
        }
        m.filter(|m| m.length > Ratio::ZERO)
    }

    /// (bar number, "bar 12 beat 3+1/2") for a position. Bar numbers are the ones Dorico
    /// shows (pick-up = bar 0, bar-number changes such as "35a"); beats count from the start
    /// of the bar in the meter's beat unit.
    pub fn locate(&self, pos: Ratio) -> (Option<i128>, String) {
        let Some(m) = self.meter_at(pos) else {
            return (None, format!("pos {pos}"));
        };
        let Some(bar) = bars::bar_at(&self.bars, pos) else {
            return (None, format!("pos {pos}"));
        };
        let (mut number, mut label, mut start) = (bar.number as i128, bar.label.clone(), bar.start);
        let end = bar.start + bar.length;
        if pos >= end && m.length > Ratio::ZERO {
            // past the last bar (e.g. a time signature at the very end): keep counting
            let k = ((pos - end) / m.length).floor();
            number += k + 1;
            label = number.to_string();
            start = end + Ratio::int(k) * m.length;
        }
        let rem = pos - start;
        let beat = Ratio::ONE + rem / m.beat;
        let whole = beat.trunc();
        let part = beat - Ratio::int(whole);
        let beat_s = if part.is_zero() { whole.to_string() } else { format!("{whole}+{part}") };
        (Some(number), format!("bar {label} beat {beat_s}"))
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct Score {
    pub info: OrderedMap,
    /// playerID -> display name, in `scorePlayers` order
    pub players: Vec<(String, String)>,
    pub flows: Vec<Flow>,
    /// flattened `scoreOptions`: path -> value
    pub options: OrderedMap,
    /// flattened `layouts`: path -> value
    pub layouts: OrderedMap,
}

impl Score {
    pub fn player_name(&self, id: &str) -> Option<&str> {
        self.players.iter().rev().find(|(i, _)| i == id).map(|(_, n)| n.as_str())
    }
    pub fn info(&self, k: &str) -> &str {
        self.info.get(k).unwrap_or("")
    }
}

/// The ID that names an array item (layoutID, playerID, ...), if it has one.
fn identity(n: &Node) -> Option<String> {
    for c in &n.children {
        if let Some(v) = c.value.as_deref() {
            if c.tag.ends_with("ID") && !v.is_empty() {
                return Some(format!("{}={v}", c.tag));
            }
            if (&*c.tag == "entityID" || &*c.tag == "propertyType") && !v.is_empty() {
                return Some(v.to_owned());
            }
        }
    }
    None
}

/// Flatten a subtree to path -> value. Array items are keyed by their ID when possible.
pub fn flatten(n: Option<&Node>) -> OrderedMap {
    let mut out = OrderedMap::default();
    fn go(n: &Node, prefix: &str, out: &mut OrderedMap) {
        if let Some(v) = n.value.as_deref() {
            let key = if prefix.is_empty() { n.tag.to_string() } else { prefix.to_owned() };
            out.insert(key, v.to_owned());
            return;
        }
        let mut counts: HashMap<&str, usize> = HashMap::new();
        for c in &n.children {
            let i = counts.entry(&c.tag).or_insert(0);
            let idx = *i;
            *i += 1;
            let name = if n.array {
                match identity(c) {
                    Some(id) => format!("{}[{id}]", c.tag),
                    None => format!("{}[#{idx}]", c.tag),
                }
            } else {
                c.tag.to_string()
            };
            let path = if prefix.is_empty() { name } else { format!("{prefix}/{name}") };
            go(c, &path, out);
        }
    }
    if let Some(n) = n {
        go(n, "", &mut out);
    }
    out
}

fn player_names(root: &Node) -> Vec<(String, String)> {
    let mut names: Vec<(String, String)> = Vec::new();
    for p in root.find("scorePlayers/array").map(Node::items).unwrap_or(&[]) {
        let id = p.text("playerID").to_owned();
        let name = crate::vocab::player_name(p);
        match names.iter_mut().find(|(i, _)| *i == id) {
            Some(slot) => slot.1 = name,
            None => names.push((id, name)),
        }
    }
    names
}

fn describe_dynamic(element: Option<&Node>) -> String {
    crate::dynamics::describe_group(element)
}

fn time_signature<'a>(tables: &Tables<'a>, element_id: &str) -> Option<&'a Node> {
    let el = tables.get("BarDivision")?.get(element_id)?;
    let ts = el.find("barDivisionData/timeSignature/timeSignaturesAndDivisions")?;
    ts.items().first()?.child("timeSignature")
}

fn meters(tables: &Tables, mut divisions: Vec<(Ratio, &Node)>) -> Vec<Meter> {
    divisions.sort_by_key(|(p, _)| *p);
    let mut meters: Vec<Meter> = Vec::new();
    for (pos, ev) in divisions {
        let sig = time_signature(tables, ev.text("barDivisionElementID"));
        let bar = match meters.last() {
            Some(prev) => {
                let so_far = if prev.length.is_zero() { Ratio::ZERO } else { (pos - prev.start) / prev.length };
                prev.bar + so_far.ceil()
            }
            None => 1,
        };
        if let Some(sig) = sig {
            let parse = |k: &str| sig.text(k).parse::<i128>().ok().filter(|v| *v != 0).unwrap_or(4);
            let (num, den) = (parse("numerator"), parse("denominator"));
            let mut beat = Ratio::new(4, den);
            if den >= 8 && num % 3 == 0 && num > 3 {
                beat = beat * Ratio::int(3); // compound time: dotted beats
            }
            meters.push(Meter {
                start: pos,
                bar,
                length: Ratio::new(4 * num, den),
                beat,
                label: format!("{num}/{den}"),
            });
        } else if let Some(prev) = meters.last().cloned() {
            meters.push(Meter { start: pos, bar, ..prev });
        }
    }
    if meters.first().is_none_or(|m| m.start > Ratio::ZERO) {
        meters.insert(
            0,
            Meter { start: Ratio::ZERO, bar: 1, length: Ratio::int(4), beat: Ratio::ONE, label: "4/4".into() },
        );
    }
    meters
}

fn split_camel_lower(kind: &str) -> String {
    let mut out = String::new();
    for (i, ch) in kind.chars().enumerate() {
        if i > 0 && ch.is_ascii_uppercase() {
            out.push(' ');
        }
        out.push(ch);
    }
    out.to_lowercase()
}

/// Python `f"{x:g}"` for the tempo range we see.
fn format_g(x: f64) -> String {
    if x == 0.0 {
        return "0".into();
    }
    let exp = x.abs().log10().floor() as i32;
    if !(-4..6).contains(&exp) {
        return format!("{x:e}");
    }
    let decimals = (5 - exp).max(0) as usize;
    let s = format!("{x:.decimals$}");
    if s.contains('.') { s.trim_end_matches('0').trim_end_matches('.').to_owned() } else { s }
}

/// Film data of one flow (`flowVideoData`), confirmed with the user's `ref-film-v1/v2.dorico`:
/// - `videoAttachmentPosition`: where the video starts in the flow (crotchets);
/// - `kVideoEventInTime`: the video start offset, seconds into the clip;
/// - `kVideoClipTimecodeStart`: the timecode of the clip's first frame (seconds);
/// - markers' `timePosition` is **clip time** (seconds): markers stay on the picture and
///   Dorico recomputes their beat position; Dorico shows them as timecode start + clip time.
struct Film {
    attached: bool,
    file: String,
    start: Ratio,
    offset: f64,
    timecode_start: f64,
    fps: f64,
}

fn read_film(flow: &Node, project_rate: &str) -> Film {
    let project_fps = crate::timecode::FrameRate::from_dorico(project_rate, false).map(|r| r.fps).unwrap_or(0.0);
    match crate::vocab::video(flow) {
        Some(v) => Film {
            attached: v.attached,
            file: v.file,
            start: v.start,
            offset: v.offset,
            timecode_start: v.timecode_start,
            fps: v.clip_fps.unwrap_or(project_fps),
        },
        None => Film { attached: false, file: String::new(), start: Ratio::ZERO, offset: 0.0, timecode_start: 0.0, fps: project_fps },
    }
}

/// Seconds -> "HH:MM:SS:FF" (non-drop) at `fps`, or "12.345 s" when the rate is unknown.
/// (The listing's form; frame rates and drop frame: [`crate::timecode`].)
pub fn timecode(secs: f64, fps: f64) -> String {
    match crate::timecode::FrameRate::from_fps(fps) {
        Some(r) => r.format(secs),
        None => format!("{secs:.3} s"),
    }
}

pub fn build_score(root: &Node) -> Score {
    let mut info = OrderedMap::default();
    if let Some(i) = root.child("info") {
        for c in &i.children {
            info.insert(c.tag.to_string(), c.value.as_deref().unwrap_or("").to_owned());
        }
    }
    let players = player_names(root);
    let player_lookup: HashMap<&str, &str> = players.iter().map(|(i, n)| (i.as_str(), n.as_str())).collect();

    let project_rate = root
        .find("scoreOptions/playbackOptions/timeDisplayPlaybackOptions/projectFrameRate")
        .and_then(|n| n.value.as_deref())
        .unwrap_or("");
    let mut flows = Vec::new();
    for f in root.find("flows/array").map(Node::items).unwrap_or(&[]) {
        let film = read_film(f, project_rate);
        let flow_id = f.text("flowID").to_owned();
        let name = match f.text("flowName") {
            "" => format!("Flow {flow_id}"),
            n => n.to_owned(),
        };
        let tables = element_tables(f);

        // stream id -> (owner, lane)
        let mut owners: HashMap<String, (String, String)> = HashMap::new();
        for fp in f.find("flowPlayers/array").map(Node::items).unwrap_or(&[]) {
            let pid = fp.text("playerID");
            let pname = player_lookup.get(pid).map(|s| s.to_string()).unwrap_or_else(|| format!("player {pid}"));
            owners.insert(fp.text("eventStreamID").to_owned(), (pname.clone(), String::new()));
            for inst in fp.child("flowPlayerInstruments").map(Node::items).unwrap_or(&[]) {
                let staves = inst.child("staveStreamInfos").map(Node::items).unwrap_or(&[]);
                for (i, s) in staves.iter().enumerate() {
                    let lane = if staves.len() > 1 { format!("stave {}", i + 1) } else { String::new() };
                    owners.insert(s.text("staveStreamID").to_owned(), (pname.clone(), lane));
                }
                let voices = inst.child("voiceStreamInfos").map(Node::items).unwrap_or(&[]);
                for (i, v) in voices.iter().enumerate() {
                    owners.insert(v.text("voiceStreamID").to_owned(), (pname.clone(), format!("voice {}", i + 1)));
                }
            }
        }
        for s in f.find("eventStreams/array").map(Node::items).unwrap_or(&[]) {
            let sid = s.text("streamID");
            if !owners.contains_key(sid) {
                let who = if s.text("eventStreamType") == "kGlobalTimebaseStream" {
                    "(global)".to_owned()
                } else {
                    format!("(stream {sid})")
                };
                owners.insert(sid.to_owned(), (who, String::new()));
            }
        }

        let mut placements: HashMap<&str, Vec<(&str, Ratio)>> = HashMap::new();
        for bi in f.find("blockInstances/array").map(Node::items).unwrap_or(&[]) {
            placements
                .entry(bi.text("blockID"))
                .or_default()
                .push((bi.text("streamID"), Ratio::parse(bi.text("position"))));
        }

        let mut raw: Vec<(&str, Ratio, &Node)> = Vec::new();
        for b in f.find("blocks/array").map(Node::items).unwrap_or(&[]) {
            let (stream, base) =
                placements.get(b.text("blockID")).and_then(|v| v.first().copied()).unwrap_or(("?", Ratio::ZERO));
            for ev in b.child("events").map(Node::items).unwrap_or(&[]) {
                raw.push((stream, base + Ratio::parse(ev.text("position")), ev));
            }
        }

        let mut flow = Flow { flow_id, name, meters: Vec::new(), video: None, events: Vec::new(), bars: Vec::new() };
        flow.meters = meters(
            &tables,
            raw.iter()
                .filter(|(_, _, ev)| &*ev.tag == "BarDivisionEventDefinition")
                .map(|(_, p, ev)| (*p, *ev))
                .collect(),
        );
        // bars (shared with the read model): divisions in the global stream start bars;
        // bar-number changes count from any stream
        let global: Vec<&str> = f
            .find("eventStreams/array")
            .map(Node::items)
            .unwrap_or(&[])
            .iter()
            .filter(|s| s.text("eventStreamType") == "kGlobalTimebaseStream")
            .map(|s| s.text("streamID"))
            .collect();
        let (mut divisions, mut changes) = (Vec::new(), Vec::new());
        let mut end =
            Ratio::parse(f.find("minimumNotatedLength/length").and_then(|n| n.value.as_deref()).unwrap_or("0"));
        for (stream, pos, ev) in &raw {
            end = end.max(*pos + Ratio::parse(ev.text("duration")));
            if &*ev.tag != "BarDivisionEventDefinition" {
                continue;
            }
            let el = tables.get("BarDivision").and_then(|t| t.get(ev.text("barDivisionElementID"))).copied();
            let (d, c) = bars::read_division(*pos, el);
            if global.contains(stream) {
                divisions.push(d);
            }
            changes.extend(c);
        }
        for bi in f.find("blockInstances/array").map(Node::items).unwrap_or(&[]) {
            end = end.max(Ratio::parse(bi.text("position")));
        }
        flow.bars = bars::compute_bars(&divisions, &changes, end);
        let numbers: Vec<Option<i128>> = flow.meters.iter().map(|m| flow.locate(m.start).0).collect();
        for (m, n) in flow.meters.iter_mut().zip(numbers) {
            if let Some(n) = n {
                m.bar = n;
            }
        }
        if film.attached {
            let (_, at) = flow.locate(film.start);
            flow.video = Some(format!(
                "{} at {at}, clip from {} (timecode {}), {} fps",
                film.file,
                timecode(film.offset, film.fps),
                timecode(film.timecode_start + film.offset, film.fps),
                format_g(film.fps)
            ));
        }
        let dynamics = tables.get("DynamicGroup");
        for (stream, pos, ev) in &raw {
            let (owner, lane) =
                owners.get(*stream).cloned().unwrap_or_else(|| (format!("(stream {stream})"), String::new()));
            let tag: &str = &ev.tag;
            let base_kind = tag.strip_suffix("EventDefinition").unwrap_or(tag);
            let dur = Ratio::parse(ev.text("duration"));
            let mut props = properties(ev);
            let (kind, text) = match base_kind {
                "Note" | "GraceNote" => {
                    let mut spelling = None;
                    let (mut harmonic_type, mut partial) = (None, None);
                    for e in property_entries(ev) {
                        match e.text("propertyType") {
                            "kNoteSpelling" => spelling = Some(clean_value(e.text("value"))),
                            // harmonics: type kNatural/kArtificial + partial number (the user
                            // confirmed partial 5 = int 5 in the Rite of Spring, 2026-10-31)
                            "kNoteHarmonicType" => harmonic_type = Some(clean_value(e.text("value"))),
                            "kNoteHarmonic" => {
                                partial = clean_value(e.text("value")).strip_prefix("int: ").map(str::to_owned)
                            }
                            _ => {}
                        }
                    }
                    let pitch: i64 = ev.text("pitch").parse().unwrap_or(0);
                    let mut text = format!("{} {}", pitch_name(pitch, spelling.as_deref()), duration_name(dur));
                    if harmonic_type.is_some() || partial.is_some() {
                        let kind = harmonic_type.as_deref().map(|t| t.strip_prefix('k').unwrap_or(t).to_lowercase());
                        text.push_str(&format!(", {} harmonic", kind.as_deref().unwrap_or("?")));
                        if let Some(p) = &partial {
                            text.push_str(&format!(" (partial {p})"));
                        }
                        props.retain(|p| !p.starts_with("NoteHarmonicType=") && !p.starts_with("NoteHarmonic="));
                    }
                    (if base_kind == "Note" { "note" } else { "grace note" }.to_owned(), text)
                }
                "Rest" => ("rest".to_owned(), duration_name(dur)),
                "DynamicGroup" => {
                    let el = dynamics.and_then(|d| d.get(ev.text("dynamicGroupID")).copied());
                    ("dynamic".to_owned(), describe_dynamic(el))
                }
                "BarDivision" => match time_signature(&tables, ev.text("barDivisionElementID")) {
                    Some(sig) => {
                        ("time signature".to_owned(), format!("{}/{}", sig.text("numerator"), sig.text("denominator")))
                    }
                    None => ("barline".to_owned(), "barline".to_owned()),
                },
                "ImmediateTempoChange" => {
                    let bpm = crate::vocab::tempo_bpm(ev);
                    let mut text =
                        bpm.filter(|b| *b != 0.0).map(|b| format!("{} bpm", format_g(b))).unwrap_or_default();
                    if let Some(t) = ev.find("data/text").and_then(|n| n.value.as_deref()).filter(|t| !t.is_empty()) {
                        text.push_str(&format!(" \"{t}\""));
                    }
                    ("tempo".to_owned(), text)
                }
                "Marker" => {
                    let m = crate::vocab::marker(ev);
                    props.retain(|p| !p.starts_with("MarkerText=") && !p.starts_with("MarkerIsImportant="));
                    let mut text = format!("\"{}\" at {}", m.name, timecode(film.timecode_start + m.time, film.fps));
                    if m.important {
                        text.push_str(" (important)");
                    }
                    ("marker".to_owned(), text)
                }
                other => {
                    let mut text = leaf_summary(ev, STANDARD_EVENT_FIELDS, 6);
                    if !dur.is_zero() {
                        text =
                            if text.is_empty() { format!("(length {dur})") } else { format!("{text} (length {dur})") };
                    }
                    (split_camel_lower(other), text)
                }
            };
            let (bar, where_) = flow.locate(*pos);
            flow.events.push(Event {
                flow: flow.name.clone(),
                owner,
                lane,
                kind,
                position: *pos,
                where_,
                bar,
                text,
                props,
                event_id: ev.text("eventID").to_owned(),
            });
        }
        let mut order: HashMap<&str, i64> = HashMap::new();
        for (i, (_, n)) in players.iter().enumerate() {
            order.insert(n, i as i64);
        }
        flow.events.sort_by(|a, b| {
            let ka = (order.get(a.owner.as_str()).copied().unwrap_or(-1), &a.lane, a.position, &a.kind, &a.text);
            let kb = (order.get(b.owner.as_str()).copied().unwrap_or(-1), &b.lane, b.position, &b.kind, &b.text);
            ka.cmp(&kb)
        });
        flows.push(flow);
    }

    Score {
        info,
        players,
        flows,
        options: flatten(root.child("scoreOptions")),
        layouts: flatten(root.child("layouts")),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn intensities() {
        let d = |v: &str| decode_intensity(&format!("steamVariantList:list: {v}"));
        assert_eq!(d("{int: 0}, {}, {bool: false}, {int: 3}"), "fff");
        assert_eq!(d("{int: 1}, {}, {bool: true}, {}"), "mp");
        assert_eq!(d("{int: 0}, {}, {bool: false}, {int: 8}"), "ffffffff");
        assert_eq!(d("{int: 0}, {int: 1}, {bool: false}, {}"), "f possibile");
    }

    #[test]
    fn timecodes() {
        assert_eq!(timecode(3621.0, 25.0), "01:00:21:00");
        assert_eq!(timecode(3617.56, 25.0), "01:00:17:14");
        assert_eq!(timecode(5.0, 0.0), "5.000 s");
    }

    #[test]
    fn names() {
        assert_eq!(pitch_name(70, Some("B")), "Bb4");
        assert_eq!(pitch_name(70, Some("A")), "A#4");
        assert_eq!(pitch_name(60, None), "C4");
        assert_eq!(duration_name(Ratio::new(3, 2)), "dotted crotchet");
        assert_eq!(duration_name(Ratio::new(3, 5)), "3/5 crotchets");
        assert_eq!(decode_intensity("steamVariantList:list: {int: 0}, {}, {bool: false}, {int: 2}"), "ff");
        assert_eq!(decode_intensity("steamVariantList:list: {int: 1}, {}, {bool: true}, {}"), "mp");
        assert_eq!(clean_value("string: \"kMarcato\""), "kMarcato");
        assert_eq!(format_g(80.0), "80");
        assert_eq!(format_g(133.33), "133.33");
        assert_eq!(split_camel_lower("PlayingTechnique"), "playing technique");
    }
}
