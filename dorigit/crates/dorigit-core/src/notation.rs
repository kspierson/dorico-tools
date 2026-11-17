//! Notation for a range of bars, as MEI (Music Encoding Initiative), which the app renders
//! with Verovio (MERGE.md §8, milestone N1).
//!
//! Built from the shared read model (`dorico-model`): bars, time signatures, keys, parts with
//! staves and voices, notes (pitch, spelling, length), clefs, tuplets and dynamics; spelling,
//! keys, tuplets, dynamic names and glyphs come from the engine (`dorico_format::vocab`). It is a *preview* of the music for comparing
//! versions, not an engraving: Dorico's layout, beaming and spacing are not reproduced.
//!
//! - Concert pitch (as the listing; the user accepted this).
//! - Notes longer than a bar are split at barlines and tied; lengths that need several note
//!   values are split and tied too. Tuplets come from the voice's tuplet marks.
//! - Accidentals are shown where the key and earlier notes in the bar don't imply them.
//! - `Highlight`s colour notes (added/changed/removed in a diff).

use anyhow::{Result, bail};
use dorico_format::Node;
use dorico_format::vocab::{self, clean_value, glyphs};
use dorico_format::ratio::Ratio;
use dorico_model::{Flow, Mark, Note, Part, Voice};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, HashMap};
use std::fmt::Write as _;

/// Colour one note: the player's name, its position (crotchets from the flow start) and
/// optionally its MIDI pitch (otherwise every note there).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Highlight {
    pub player: String,
    /// As the diff writes positions: "62", "15203/80".
    pub pos: String,
    #[serde(default)]
    pub pitch: Option<i64>,
    /// CSS colour, e.g. "#2f9e44".
    pub color: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Request {
    pub flow_id: String,
    /// 1-based bar indices (a pick-up is bar 1), inclusive.
    pub from_bar: u32,
    pub to_bar: u32,
    /// Only these players (by name); `None` = all.
    #[serde(default)]
    pub players: Option<Vec<String>>,
    #[serde(default)]
    pub highlights: Vec<Highlight>,
}

/// MEI for `req` from a score's root node.
pub fn render(root: &Node, req: &Request) -> Result<String> {
    let model = dorico_model::read_score(root);
    let Some(flow) = model.flows.iter().find(|f| f.id == req.flow_id) else { bail!("no flow {}", req.flow_id) };
    Ok(mei(flow, &key_changes(flow), req))
}

// ---------------------------------------------------------------------------------------
// keys

/// (position, fifths) for each key change of the flow (fifths: +2 = D major, -3 = Eb major),
/// from the read model's flow keys.
fn key_changes(flow: &Flow) -> Vec<(Ratio, i32)> {
    let mut out: Vec<(Ratio, i32)> = flow.keys.iter().map(|k| (k.pos, k.key.fifths)).collect();
    out.sort_by_key(|(p, _)| *p);
    out.dedup_by_key(|(p, _)| *p);
    out
}

fn key_sig(fifths: i32) -> String {
    match fifths {
        0 => "0".into(),
        f if f > 0 => format!("{f}s"),
        f => format!("{}f", -f),
    }
}

/// Alteration of each letter (C..B) under a key.
fn key_alterations(fifths: i32) -> [i32; 7] {
    // order of sharps: F C G D A E B; letters indexed C=0 .. B=6
    const SHARPS: [usize; 7] = [3, 0, 4, 1, 5, 2, 6];
    let mut alt = [0; 7];
    if fifths > 0 {
        for &l in &SHARPS[..fifths as usize] {
            alt[l] = 1;
        }
    } else {
        for &l in SHARPS.iter().rev().take((-fifths) as usize) {
            alt[l] = -1;
        }
    }
    alt
}

// ---------------------------------------------------------------------------------------
// pitch

/// MEI pitch names by letter index (C=0 .. B=6, as `vocab::spell`).
const LETTERS: [char; 7] = ['c', 'd', 'e', 'f', 'g', 'a', 'b'];
const LETTER_SEMITONES: [i64; 7] = [0, 2, 4, 5, 7, 9, 11];

/// (letter index 0..6, alteration -2..2, octave) for a MIDI pitch and Dorico's spelled letter
/// (the engine's `vocab::spell`).
fn spell(midi: i64, spelling: Option<char>) -> (usize, i32, i64) {
    let (l, a, o) = vocab::spell(midi, spelling);
    (l, a as i32, o)
}

fn note_spelling(n: &Note) -> Option<char> {
    n.props.get("kNoteSpelling").and_then(|v| clean_value(v).chars().next())
}

// ---------------------------------------------------------------------------------------
// durations

/// Written note values: (MEI dur, length in crotchets as n/d).
const VALUES: [(&str, i128, i128); 9] = [
    ("breve", 8, 1),
    ("1", 4, 1),
    ("2", 2, 1),
    ("4", 1, 1),
    ("8", 1, 2),
    ("16", 1, 4),
    ("32", 1, 8),
    ("64", 1, 16),
    ("128", 1, 32),
];

/// Split a length into note values with dots (largest first). Lengths that aren't sums of
/// note values down to 128ths end with the nearest smaller piece (preview only).
fn split_length(mut len: Ratio) -> Vec<(&'static str, u8)> {
    let mut out = Vec::new();
    let smallest = Ratio::new(1, 32);
    while len >= smallest && out.len() < 8 {
        let mut pick = None;
        for (name, n, d) in VALUES {
            let v = Ratio::new(n, d);
            for (dots, mul) in [(2u8, Ratio::new(7, 4)), (1, Ratio::new(3, 2)), (0, Ratio::ONE)] {
                if v * mul <= len {
                    pick = Some((name, dots, v * mul));
                    break;
                }
            }
            if pick.is_some() {
                break;
            }
        }
        let Some((name, dots, used)) = pick else { break };
        out.push((name, dots));
        len = len - used;
    }
    if out.is_empty() {
        out.push(("128", 0));
    }
    out
}

fn is_dyadic(r: Ratio) -> bool {
    let d = r.denom();
    d > 0 && d & (d - 1) == 0
}

// ---------------------------------------------------------------------------------------
// layout of one voice in one bar

#[derive(Debug, Clone)]
struct Tuplet {
    start: Ratio,
    end: Ratio,
    num: i64,
    numbase: i64,
}

fn tuplets(v: &Voice) -> Vec<Tuplet> {
    v.marks
        .iter()
        .filter_map(|m| {
            let t = m.tuplet.as_ref()?;
            (t.num > 0 && t.den > 0).then(|| Tuplet { start: m.pos, end: m.end.unwrap_or(m.pos), num: t.num, numbase: t.den })
        })
        .collect()
}

/// One slot on a voice's timeline in a bar: a chord (notes) or a rest.
#[derive(Debug)]
struct Slot<'a> {
    start: Ratio,
    end: Ratio,
    notes: Vec<&'a Note>,
    graces: Vec<&'a Note>,
    tie_in: bool,
    tie_out: bool,
}

fn slots<'a>(v: &'a Voice, start: Ratio, end: Ratio) -> Vec<Slot<'a>> {
    let mut chords: BTreeMap<Ratio, Vec<&Note>> = BTreeMap::new();
    let mut graces: BTreeMap<Ratio, Vec<&Note>> = BTreeMap::new();
    for n in &v.notes {
        if n.grace {
            if n.pos >= start && n.pos < end {
                graces.entry(n.pos).or_default().push(n);
            }
        } else if n.pos < end && n.pos + n.dur > start && !n.dur.is_zero() {
            chords.entry(n.pos).or_default().push(n);
        }
    }
    let mut out: Vec<Slot> = Vec::new();
    let mut cursor = start;
    for (pos, notes) in chords {
        let note_end = notes.iter().map(|n| n.pos + n.dur).min().unwrap_or(pos);
        let s = pos.max(start).max(cursor);
        let e = note_end.min(end);
        if e <= s {
            continue; // overlapped by the previous chord (several voices in one stream)
        }
        if s > cursor {
            out.push(Slot { start: cursor, end: s, notes: vec![], graces: vec![], tie_in: false, tie_out: false });
        }
        out.push(Slot {
            start: s,
            end: e,
            graces: graces.remove(&pos).unwrap_or_default(),
            notes,
            tie_in: pos < start,
            tie_out: note_end > end,
        });
        cursor = e;
    }
    if cursor < end && !out.is_empty() {
        out.push(Slot { start: cursor, end, notes: vec![], graces: vec![], tie_in: false, tie_out: false });
    }
    out
}

// ---------------------------------------------------------------------------------------
// clefs

/// MEI clef (shape, line, octave displacement) for a Dorico clef entity.
fn clef_for(entity: &str) -> (&'static str, u8, i8) {
    let e = entity.strip_prefix("clef.").unwrap_or(entity);
    match e {
        "bass" => ("F", 4, 0),
        "alto" => ("C", 3, 0),
        "tenor" => ("C", 4, 0),
        "percussion" | "perc" => ("perc", 3, 0),
        e if e.starts_with("bass") && e.contains("8vb") => ("F", 4, -8),
        e if e.starts_with("treble") && e.contains("8vb") => ("G", 2, -8),
        e if e.starts_with("treble") && e.contains("8va") => ("G", 2, 8),
        _ => ("G", 2, 0),
    }
}

/// Default clef when the stave has no clef event: by instrument, then by the notes' pitch.
fn default_clef(part: &Part, stave_index: usize) -> &'static str {
    let e = part.entity.to_lowercase();
    if part.staves.len() > 1 && stave_index > 0 {
        return "clef.bass";
    }
    for (needle, clef) in [
        ("viola", "clef.alto"),
        ("violoncello", "clef.bass"),
        ("cello", "clef.bass"),
        ("contrabass", "clef.bass"),
        ("doublebass", "clef.bass"),
        ("bassoon", "clef.bass"),
        ("trombone", "clef.bass"),
        ("tuba", "clef.bass"),
        ("timpani", "clef.bass"),
        ("bass.clarinet", "clef.treble"),
        ("guitar", "clef.treble8vb"),
    ] {
        if e.contains(needle) {
            return clef;
        }
    }
    let pitches: Vec<i64> = part
        .voices
        .iter()
        .filter(|v| v.stave_index == stave_index)
        .flat_map(|v| v.notes.iter().map(|n| n.pitch))
        .collect();
    if pitches.is_empty() {
        return "clef.treble";
    }
    let mut p = pitches;
    p.sort();
    if p[p.len() / 2] < 55 { "clef.bass" } else { "clef.treble" }
}

fn clef_attrs(entity: &str) -> String {
    let (shape, line, dis) = clef_for(entity);
    let mut s = format!(r#" clef.shape="{shape}" clef.line="{line}""#);
    if dis != 0 {
        let _ = write!(s, r#" clef.dis="8" clef.dis.place="{}""#, if dis > 0 { "above" } else { "below" });
    }
    s
}

fn clef_element(entity: &str) -> String {
    let (shape, line, dis) = clef_for(entity);
    let mut s = format!(r#"<clef shape="{shape}" line="{line}""#);
    if dis != 0 {
        let _ = write!(s, r#" dis="8" dis.place="{}""#, if dis > 0 { "above" } else { "below" });
    }
    s.push_str("/>");
    s
}

// ---------------------------------------------------------------------------------------
// MEI

fn esc(s: &str) -> String {
    s.replace('&', "&amp;").replace('<', "&lt;").replace('>', "&gt;").replace('"', "&quot;")
}

struct StaffInfo<'a> {
    n: usize,
    part: &'a Part,
    stave_index: usize,
    voices: Vec<&'a Voice>,
    divisi: bool,
    clefs: Vec<(Ratio, String)>,
    dynamics: &'a [dorico_model::DynamicGroup],
}

fn mei(flow: &Flow, keys: &[(Ratio, i32)], req: &Request) -> String {
    let from = req.from_bar.max(1) as usize;
    let to = (req.to_bar as usize).min(flow.bars.len()).max(from);
    let bars = &flow.bars[(from - 1).min(flow.bars.len())..to.min(flow.bars.len())];
    let range_start = bars.first().map(|b| b.start).unwrap_or(Ratio::ZERO);

    // staves
    let mut staves: Vec<StaffInfo> = Vec::new();
    for part in &flow.parts {
        if let Some(only) = &req.players
            && !only.contains(&glyphs(&part.player_name))
        {
            continue;
        }
        for st in &part.staves {
            let mut clefs: Vec<(Ratio, String)> = st
                .marks
                .iter()
                .filter(|m: &&Mark| m.kind == "clef")
                .filter_map(|m| Some((m.pos, m.detail.get("entity")?.clone())))
                .collect();
            clefs.sort_by_key(|(p, _)| *p);
            staves.push(StaffInfo {
                n: staves.len() + 1,
                part,
                stave_index: st.index,
                // by stave id: a divisi stave has the same index as its main stave
                voices: part.voices.iter().filter(|v| v.stave_id == st.stave_id).collect(),
                divisi: st.divisi.is_some(),
                clefs,
                dynamics: &st.dynamics,
            });
        }
        // voices on no known stave (unusual files): give them a staff rather than lose them
        let orphans: Vec<&Voice> =
            part.voices.iter().filter(|v| !part.staves.iter().any(|st| st.stave_id == v.stave_id)).collect();
        if !orphans.is_empty() {
            staves.push(StaffInfo {
                n: staves.len() + 1,
                part,
                stave_index: if part.staves.is_empty() { 0 } else { part.staves.len() },
                voices: orphans,
                divisi: false,
                clefs: Vec::new(),
                dynamics: &[],
            });
        }
    }

    let key_at = |pos: Ratio| keys.iter().rev().find(|(p, _)| *p <= pos).map(|(_, f)| *f).unwrap_or(0);
    let mut out = String::new();
    out.push_str(r#"<?xml version="1.0" encoding="UTF-8"?>"#);
    out.push_str(r#"<mei xmlns="http://www.music-encoding.org/ns/mei" meiversion="5.0">"#);
    let _ = write!(
        out,
        r#"<meiHead><fileDesc><titleStmt><title>{}</title></titleStmt><pubStmt/></fileDesc></meiHead>"#,
        esc(&flow.name)
    );
    out.push_str("<music><body><mdiv><score>");

    let first = bars.first();
    let mut fifths = key_at(range_start);
    let _ = write!(
        out,
        r#"<scoreDef key.sig="{}" meter.count="{}" meter.unit="{}"><staffGrp>"#,
        key_sig(fifths),
        first.map(|b| b.num).unwrap_or(4),
        first.map(|b| b.den).unwrap_or(4)
    );
    // group multi-stave parts with a brace
    let mut i = 0;
    while i < staves.len() {
        let part = staves[i].part;
        let j = staves[i..].iter().take_while(|s| std::ptr::eq(s.part, part)).count();
        let group = j > 1;
        if group {
            out.push_str(r#"<staffGrp symbol="brace" bar.thru="true">"#);
        }
        for s in &staves[i..i + j] {
            let clef = s
                .clefs
                .iter()
                .rev()
                .find(|(p, _)| *p <= range_start)
                .map(|(_, c)| c.as_str())
                .unwrap_or_else(|| default_clef(s.part, s.stave_index));
            let label = if s.divisi {
                "div."
            } else if s.stave_index == 0 {
                part.player_name.as_str()
            } else {
                ""
            };
            let _ = write!(out, r#"<staffDef n="{}" lines="5"{}>"#, s.n, clef_attrs(clef));
            if !label.is_empty() {
                let _ = write!(out, "<label>{}</label>", esc(&glyphs(label)));
            }
            out.push_str("</staffDef>");
        }
        if group {
            out.push_str("</staffGrp>");
        }
        i += j;
    }
    out.push_str("</staffGrp></scoreDef><section>");

    let highlight_of = |part: &Part, n: &Note| -> Option<&str> {
        req.highlights
            .iter()
            .find(|h| h.player == glyphs(&part.player_name) && Ratio::parse(&h.pos) == n.pos && h.pitch.is_none_or(|p| p == n.pitch))
            .map(|h| h.color.as_str())
    };

    let mut prev: Option<&dorico_format::bars::Bar> = None;
    for (bi, bar) in bars.iter().enumerate() {
        let end = bar.start + bar.length;
        // meter / key changes at this bar
        let k = key_at(bar.start);
        let meter_changed = prev.is_some_and(|p| (p.num, p.den) != (bar.num, bar.den));
        if bi > 0 && (k != fifths || meter_changed) {
            out.push_str("<scoreDef");
            if k != fifths {
                let _ = write!(out, r#" key.sig="{}""#, key_sig(k));
                fifths = k;
            }
            if meter_changed {
                let _ = write!(out, r#" meter.count="{}" meter.unit="{}""#, bar.num, bar.den);
            }
            out.push_str("/>");
        }
        let _ = write!(out, r#"<measure n="{}">"#, esc(&bar.label));
        let beat = Ratio::new(4, bar.den.max(1) as i128);
        let tstamp = |pos: Ratio| -> String {
            let t = Ratio::ONE + (pos - bar.start) / beat;
            format!("{:.3}", t.to_f64()).trim_end_matches('0').trim_end_matches('.').to_owned()
        };
        let mut control = String::new();
        for s in &staves {
            let _ = write!(out, r#"<staff n="{}">"#, s.n);
            let mut any_layer = false;
            let mut acc_state: HashMap<(usize, i64), i32> = HashMap::new();
            let key_alt = key_alterations(fifths);
            for (li, v) in s.voices.iter().enumerate() {
                let sl = slots(v, bar.start, end);
                if sl.is_empty() {
                    continue;
                }
                any_layer = true;
                let tups = tuplets(v);
                // beams follow the beat: a minim in x/2, a dotted crotchet in compound x/8,
                // otherwise a crotchet
                let beam_len = if bar.den == 2 {
                    Ratio::int(2)
                } else if bar.den == 8 && bar.num % 3 == 0 {
                    Ratio::new(3, 2)
                } else {
                    Ratio::ONE
                };
                let mut elems: Vec<Elem> = Vec::new();
                for slot in &sl {
                    // clef changes inside the range (first layer only)
                    if li == 0 {
                        for (p, c) in &s.clefs {
                            if *p == slot.start && *p > range_start {
                                elems.push(Elem { xml: clef_element(c), beam: None, tuplet: None });
                            }
                        }
                    }
                    let tup_index = tups.iter().position(|t| t.start <= slot.start && slot.start < t.end);
                    let scale = tup_index
                        .map(|i| Ratio::new(tups[i].num as i128, tups[i].numbase as i128))
                        .unwrap_or(Ratio::ONE);
                    let mut written = (slot.end - slot.start) * scale;
                    if !is_dyadic(written) {
                        // outside a known tuplet or nested: show the nearest plain value
                        written = Ratio::new((written * Ratio::int(32) + Ratio::new(1, 2)).floor().max(1), 32);
                    }
                    let pieces = split_length(written);
                    let group = ((slot.start - bar.start) / beam_len).floor();
                    // grace notes before the chord (not beamed with the main notes)
                    for g in &slot.graces {
                        let (l, a, o) = spell(g.pitch, note_spelling(g));
                        let shown = a != *acc_state.get(&(l, o)).unwrap_or(&key_alt[l]);
                        acc_state.insert((l, o), a);
                        let mut x = format!(r#"<note grace="unacc" dur="8" pname="{}" oct="{o}""#, LETTERS[l]);
                        accid_attr(&mut x, a, shown);
                        x.push_str("/>");
                        elems.push(Elem { xml: x, beam: None, tuplet: tup_index });
                    }
                    if slot.notes.is_empty() {
                        for (dur, dots) in &pieces {
                            let mut x = format!(r#"<rest dur="{dur}""#);
                            if *dots > 0 {
                                let _ = write!(x, r#" dots="{dots}""#);
                            }
                            x.push_str("/>");
                            elems.push(Elem { xml: x, beam: None, tuplet: tup_index });
                        }
                        continue;
                    }
                    let last = pieces.len() - 1;
                    for (pi, (dur, dots)) in pieces.iter().enumerate() {
                        let tie = match (slot.tie_in || pi > 0, slot.tie_out || pi < last) {
                            (false, false) => None,
                            (false, true) => Some("i"),
                            (true, true) => Some("m"),
                            (true, false) => Some("t"),
                        };
                        let chord = slot.notes.len() > 1;
                        let mut x = String::new();
                        if chord {
                            let _ = write!(x, r#"<chord dur="{dur}""#);
                            if *dots > 0 {
                                let _ = write!(x, r#" dots="{dots}""#);
                            }
                            x.push('>');
                        }
                        for n in &slot.notes {
                            let (l, a, o) = spell(n.pitch, note_spelling(n));
                            // accidentals only on the first piece of the first bar of a note
                            let shown =
                                !slot.tie_in && pi == 0 && a != *acc_state.get(&(l, o)).unwrap_or(&key_alt[l]);
                            acc_state.insert((l, o), a);
                            let _ = write!(x, r#"<note pname="{}" oct="{o}""#, LETTERS[l]);
                            if !chord {
                                let _ = write!(x, r#" dur="{dur}""#);
                                if *dots > 0 {
                                    let _ = write!(x, r#" dots="{dots}""#);
                                }
                            }
                            accid_attr(&mut x, a, shown);
                            if let Some(t) = tie {
                                let _ = write!(x, r#" tie="{t}""#);
                            }
                            if let Some(c) = highlight_of(s.part, n) {
                                let _ = write!(x, r#" color="{}""#, esc(c));
                            }
                            x.push_str("/>");
                        }
                        if chord {
                            x.push_str("</chord>");
                        }
                        // quavers and shorter beam within the beat
                        let beamable = matches!(*dur, "8" | "16" | "32" | "64" | "128");
                        elems.push(Elem { xml: x, beam: beamable.then_some(group), tuplet: tup_index });
                    }
                }
                let _ = write!(out, r#"<layer n="{}">"#, li + 1);
                write_layer(&mut out, &elems, &tups);
                out.push_str("</layer>");
            }
            if !any_layer {
                out.push_str(r#"<layer n="1"><mRest/></layer>"#);
            }
            out.push_str("</staff>");

            // dynamics on this staff in this bar
            for g in s.dynamics.iter() {
                for item in &g.items {
                    if item.pos < bar.start || item.pos >= end {
                        continue;
                    }
                    match item.kind.as_str() {
                        "hairpin" => {
                            let stop = item.end.unwrap_or(item.pos);
                            let (mut m, mut p) = (0usize, stop);
                            // which bar of the range the hairpin ends in
                            for (k2, b2) in bars.iter().enumerate().skip(bi) {
                                if stop <= b2.start + b2.length {
                                    m = k2 - bi;
                                    p = stop;
                                    break;
                                }
                                m = k2 - bi;
                                p = b2.start + b2.length;
                            }
                            let b2 = &bars[bi + m];
                            let beat2 = Ratio::new(4, b2.den.max(1) as i128);
                            let t2 = Ratio::ONE + (p - b2.start) / beat2;
                            let form = if item.level == "dim" { "dim" } else { "cres" };
                            let _ = write!(
                                control,
                                r#"<hairpin form="{form}" staff="{}" tstamp="{}" tstamp2="{m}m+{}"/>"#,
                                s.n,
                                tstamp(item.pos),
                                format!("{:.3}", t2.to_f64()).trim_end_matches('0').trim_end_matches('.')
                            );
                        }
                        _ if !item.level.is_empty() => {
                            let _ = write!(
                                control,
                                r#"<dynam staff="{}" tstamp="{}">{}</dynam>"#,
                                s.n,
                                tstamp(item.pos),
                                esc(&item.name)
                            );
                        }
                        _ => {}
                    }
                }
            }
        }
        out.push_str(&control);
        out.push_str("</measure>");
        prev = Some(bar);
    }
    out.push_str("</section></score></mdiv></body></music></mei>");
    out
}

/// One written element of a layer, before beams and tuplets are wrapped around it.
struct Elem {
    xml: String,
    /// Beam group (beat number in the bar) for beamable notes; None breaks a beam.
    beam: Option<i128>,
    /// Index of the voice's tuplet this element belongs to.
    tuplet: Option<usize>,
}

/// Write elements, wrapping runs in `<tuplet>` and, inside those, runs of 2+ beamable notes
/// in the same beat in `<beam>`.
fn write_layer(out: &mut String, elems: &[Elem], tups: &[Tuplet]) {
    let mut i = 0;
    while i < elems.len() {
        let t = elems[i].tuplet;
        let j = i + elems[i..].iter().take_while(|e| e.tuplet == t).count();
        if let Some(ti) = t {
            let _ = write!(out, r#"<tuplet num="{}" numbase="{}">"#, tups[ti].num, tups[ti].numbase);
        }
        write_beams(out, &elems[i..j]);
        if t.is_some() {
            out.push_str("</tuplet>");
        }
        i = j;
    }
}

fn write_beams(out: &mut String, elems: &[Elem]) {
    let mut i = 0;
    while i < elems.len() {
        let g = elems[i].beam;
        let j = if g.is_some() { i + elems[i..].iter().take_while(|e| e.beam == g).count() } else { i + 1 };
        if j - i >= 2 {
            out.push_str("<beam>");
        }
        for e in &elems[i..j] {
            out.push_str(&e.xml);
        }
        if j - i >= 2 {
            out.push_str("</beam>");
        }
        i = j;
    }
}

fn accid_attr(out: &mut String, alteration: i32, shown: bool) {
    let a = match alteration {
        -2 => "ff",
        -1 => "f",
        1 => "s",
        2 => "x",
        _ => "n",
    };
    if shown {
        let _ = write!(out, r#" accid="{a}""#);
    } else if alteration != 0 {
        let _ = write!(out, r#" accid.ges="{a}""#);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn keys_and_spelling() {
        assert_eq!(key_sig(-3), "3f");
        assert_eq!(key_alterations(2), [1, 0, 0, 1, 0, 0, 0]); // D major: F#, C#
        assert_eq!(key_alterations(-2), [0, 0, -1, 0, 0, 0, -1]); // Bb major: Bb, Eb
        assert_eq!(spell(70, Some('B')), (6, -1, 4)); // Bb4
        assert_eq!(spell(70, Some('A')), (5, 1, 4)); // A#4
        assert_eq!(spell(60, Some('B')), (6, 1, 3)); // B#3 = C4
        assert_eq!(spell(61, None), (0, 1, 4));
    }

    #[test]
    fn lengths() {
        assert_eq!(split_length(Ratio::new(3, 1)), vec![("2", 1)]);
        assert_eq!(split_length(Ratio::new(5, 1)), vec![("1", 0), ("4", 0)]);
        assert_eq!(split_length(Ratio::new(7, 4)), vec![("4", 2)]);
        assert!(is_dyadic(Ratio::new(3, 8)) && !is_dyadic(Ratio::new(1, 3)));
    }
}

// ---------------------------------------------------------------------------------------
// before / after notation for a diff

pub const ADDED: &str = "#2f9e44";
pub const REMOVED: &str = "#c92a2a";
pub const CHANGED: &str = "#3b5bdb";

/// Notation of the bars that changed in one flow: the old version with removed/changed notes
/// coloured, the new one with added/changed notes coloured. Bar labels are each version's own.
#[derive(Debug, Clone, Serialize)]
pub struct DiffNotation {
    pub flow_id: String,
    pub before: Option<String>,
    pub after: Option<String>,
    pub before_bars: Option<(String, String)>,
    pub after_bars: Option<(String, String)>,
    pub players: Vec<String>,
    /// More changed bars exist than shown (the view is capped at `MAX_BARS`).
    pub truncated: bool,
}

/// At most this many bars per view (plus one bar of context on each side).
pub const MAX_BARS: u32 = 12;

/// "Bb4 crotchet" -> MIDI 70.
pub fn parse_pitch(text: &str) -> Option<i64> {
    let word = text.split_whitespace().next()?;
    let mut chars = word.chars().peekable();
    let letter = chars.next()?.to_ascii_lowercase();
    let i = LETTERS.iter().position(|&l| l == letter)?;
    let mut acc = 0i64;
    while let Some(&c) = chars.peek() {
        match c {
            '#' => acc += 1,
            'x' => acc += 2,
            'b' => acc -= 1,
            _ => break,
        }
        chars.next();
    }
    let octave: i64 = chars.collect::<String>().parse().ok()?;
    Some((octave + 1) * 12 + LETTER_SEMITONES[i] + acc)
}

pub fn diff_notation(old: &Node, new: &Node, d: &dorico_format::diff::ScoreDiff, flow_id: &str) -> Result<DiffNotation> {
    let Some(fd) = d.flows.iter().find(|f| f.flow_id == flow_id) else { bail!("flow {flow_id} didn't change") };
    let mut positions = Vec::new();
    let mut players: Vec<String> = Vec::new();
    let (mut before_hl, mut after_hl) = (Vec::new(), Vec::new());
    for o in &fd.owners {
        for c in &o.changes {
            positions.push(c.position);
            if o.owner.starts_with('(') {
                continue; // global lane (tempo, markers…): only widens the bar range
            }
            if !players.contains(&o.owner) {
                players.push(o.owner.clone());
            }
            if !matches!(c.kind.as_str(), "note" | "grace note") {
                continue;
            }
            let h = |color: &str| Highlight {
                player: o.owner.clone(),
                pos: c.position.to_string(),
                pitch: parse_pitch(&c.text),
                color: color.to_owned(),
            };
            match c.change {
                dorico_format::diff::Change::Added => after_hl.push(h(ADDED)),
                dorico_format::diff::Change::Removed => before_hl.push(h(REMOVED)),
                dorico_format::diff::Change::Modified => {
                    // a modified note's old pitch is in its details ("C4 crotchet -> D4 crotchet")
                    let old_text = c.details.iter().find_map(|x| x.split_once(" -> ").map(|(a, _)| a.to_owned()));
                    before_hl.push(Highlight {
                        pitch: old_text.as_deref().and_then(parse_pitch).or_else(|| parse_pitch(&c.text)),
                        ..h(CHANGED)
                    });
                    after_hl.push(h(CHANGED));
                }
            }
        }
    }
    positions.sort();
    let (Some(&first), Some(&last)) = (positions.first(), positions.last()) else { bail!("no changes in this flow") };

    let mut out = DiffNotation {
        flow_id: flow_id.to_owned(),
        before: None,
        after: None,
        before_bars: None,
        after_bars: None,
        players: players.clone(),
        truncated: false,
    };
    for (root, hl, is_after) in [(old, before_hl, false), (new, after_hl, true)] {
        let model = dorico_model::read_score(root);
        let Some(flow) = model.flows.iter().find(|f| f.id == flow_id) else { continue };
        let index = |p: Ratio| flow.bar_at(p).map(|b| b.index).unwrap_or(1);
        let (a, mut b) = (index(first), index(last));
        if b > a + MAX_BARS - 1 {
            b = a + MAX_BARS - 1;
            out.truncated = true;
        }
        let from = a.saturating_sub(1).max(1);
        let to = (b + 1).min(flow.bars.len() as u32);
        let req = Request {
            flow_id: flow_id.to_owned(),
            from_bar: from,
            to_bar: to,
            players: (!players.is_empty()).then(|| players.clone()),
            highlights: hl,
        };
        let mei_text = mei(flow, &key_changes(flow), &req);
        let label = |i: u32| flow.bars.get(i as usize - 1).map(|b| b.label.clone()).unwrap_or_default();
        if is_after {
            out.after = Some(mei_text);
            out.after_bars = Some((label(from), label(to)));
        } else {
            out.before = Some(mei_text);
            out.before_bars = Some((label(from), label(to)));
        }
    }
    Ok(out)
}

#[cfg(test)]
mod diff_tests {
    use super::parse_pitch;

    #[test]
    fn pitches() {
        assert_eq!(parse_pitch("C4 crotchet"), Some(60));
        assert_eq!(parse_pitch("Bb4 dotted minim"), Some(70));
        assert_eq!(parse_pitch("F#5 quaver"), Some(78));
        assert_eq!(parse_pitch("Cx-1 quaver"), Some(2));
        assert_eq!(parse_pitch("pizz."), None);
    }
}
