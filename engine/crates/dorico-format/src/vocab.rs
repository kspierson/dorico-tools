//! Dorico's vocabulary: the one place where raw encodings become values and readable names.
//!
//! Every tool reads names from here (the read model `dorico-model`, the listing in [`crate::model`],
//! dorigit's listing and notation, the Python tools through the model) so a name or a decoding
//! exists exactly once. Dynamics have their own module ([`crate::dynamics`]) because they are big.
//!
//! | Thing | Raw form | Here |
//! |---|---|---|
//! | values | `steamVariantList:list: …`, `string: "…"` | [`clean_value`], [`variant_ints`] |
//! | glyph tokens | `Trumpet (B{@flat@})` | [`glyphs`] → "Trumpet (B♭)" |
//! | technique appearances | library `name` / `text` | [`technique_appearances`]: `name` first (`text` can be an internal key such as "opentext") |
//! | tuplets | `{int: 3}, {int: 2}, {list: {int: 7}, {int: 0}}, {bool: true}` | [`tuplet`] → 3:2 quavers (note value 8 = crotchet, each step halves) |
//! | keys | `TonalityDivisionElementDefinition` | [`key_signature`] → fifths, mode, tonic |
//! | clefs, ottavas, ornaments, arpeggios, pauses, divisi, lines | entity IDs, `k…` enums | `*_name` functions |
//! | articulations | `kStaccatoTenuto` | [`ARTICULATIONS`], [`articulation_name`] |
//! | pitch | MIDI + `kNoteSpelling` letter | [`spell`], [`pitch_name`] |
//!
//! **Dorico version forms** (4.3 vs 5.1 re-saves, dorigit RESEARCH.md): readers accept both and
//! give one answer: [`event_muted`] (`true` and `kAlways`), [`glissando_playback`] (absent before
//! Dorico 5 = `kChromatic`), [`glyphs`] (5.1 writes `{@flat@}` in instrument names).

use crate::dtn::Node;
use crate::ratio::Ratio;
use serde::Serialize;
use std::collections::BTreeMap;

// ---------------------------------------------------------------------------------------
// values

/// Strip Dorico's variant wrappers: `steamVariantList:list: ` and `string: "..."`.
pub fn clean_value(v: &str) -> String {
    let v = v.strip_prefix("steamVariantList:list: ").unwrap_or(v);
    if let Some(inner) = v.strip_prefix("string: \"").and_then(|r| r.strip_suffix('"'))
        && !inner.contains('\n')
    {
        return inner.to_owned();
    }
    v.to_owned()
}

/// Tokens `{int: X}`, `{bool: X}`, `{}` in order (nested lists are walked through).
pub fn variant_tokens(s: &str) -> Vec<(String, String)> {
    let b = s.as_bytes();
    let mut out = Vec::new();
    let mut i = 0;
    while i < b.len() {
        if b[i] == b'{' {
            if b.get(i + 1) == Some(&b'}') {
                out.push((String::new(), String::new()));
                i += 2;
                continue;
            }
            let rest = &s[i + 1..];
            let kind = if rest.starts_with("int: ") {
                Some("int")
            } else if rest.starts_with("bool: ") {
                Some("bool")
            } else {
                None
            };
            if let Some(kind) = kind {
                let start = i + 1 + kind.len() + 2;
                let word_len = s[start..]
                    .bytes()
                    .enumerate()
                    .take_while(|&(j, c)| c.is_ascii_alphanumeric() || c == b'_' || (j == 0 && c == b'-'))
                    .count();
                if word_len > 0 && b.get(start + word_len) == Some(&b'}') {
                    out.push((kind.to_owned(), s[start..start + word_len].to_owned()));
                    i = start + word_len + 1;
                    continue;
                }
            }
        }
        i += 1;
    }
    out
}

/// Every `{int: N}` in a variant list, in order (`{int: 23999}, {int: 1712}` -> [23999, 1712]).
pub fn variant_ints(s: &str) -> Vec<i64> {
    variant_tokens(s).into_iter().filter(|(k, _)| k == "int").filter_map(|(_, v)| v.parse().ok()).collect()
}

/// Dorico's glyph tokens as characters: "Trumpet (B{@flat@})" -> "Trumpet (B♭)".
pub fn glyphs(s: &str) -> String {
    if !s.contains("{@") {
        return s.to_owned();
    }
    s.replace("{@flat@}", "♭").replace("{@sharp@}", "♯").replace("{@natural@}", "♮")
}

/// The last part of an ID, in words: "pta.stringsDownBow" -> "strings down bow",
/// "kSustainPedal" -> "sustain pedal" (a leading `k` enum prefix is dropped).
pub fn humanize(id: &str) -> String {
    let tail = id.rsplit('.').next().unwrap_or(id);
    let tail = match tail.strip_prefix('k') {
        Some(rest) if rest.starts_with(|c: char| c.is_ascii_uppercase()) => rest,
        _ => tail,
    };
    let mut out = String::new();
    for (i, ch) in tail.chars().enumerate() {
        if ch.is_uppercase() && i > 0 {
            out.push(' ');
        }
        out.extend(ch.to_lowercase());
    }
    out
}

// ---------------------------------------------------------------------------------------
// text

fn text_under(n: &Node, tags: &[&str]) -> String {
    let mut parts = Vec::new();
    n.walk(|c| {
        if let Some(v) = c.value.as_deref()
            && tags.contains(&&*c.tag)
            && !v.is_empty()
        {
            let v = clean_value(v);
            let mut s = String::new();
            let mut in_tag = false;
            for ch in v.chars() {
                match ch {
                    '<' => in_tag = true,
                    '>' => in_tag = false,
                    c if !in_tag => s.push(c),
                    _ => {}
                }
            }
            if !s.trim().is_empty() {
                parts.push(s.trim().to_owned());
            }
        }
    });
    parts.join(" ")
}

/// Visible rich text under a node: `content` fragments (markup stripped), `plainText`,
/// `displayText`. Used for labels (divisi sections) and dorigit's text lines.
pub fn rich_text(n: &Node) -> String {
    text_under(n, &["content", "plainText", "displayText"])
}

/// Text carried by an event: rich text plus plain `text`/`string` leaves (tempo text, …).
pub fn event_text(ev: &Node) -> String {
    text_under(ev, &["content", "text", "plainText", "string", "displayText"])
}

// ---------------------------------------------------------------------------------------
// players, tempo

/// A player's name as Dorico stores it: `displayName`, else `baseName`, else "player N".
/// Raw: may hold glyph tokens (see [`glyphs`] for the readable label).
pub fn player_name(player: &Node) -> String {
    [player.text("displayName"), player.text("baseName")]
        .into_iter()
        .find(|s| !s.is_empty())
        .map(str::to_owned)
        .unwrap_or_else(|| format!("player {}", player.text("playerID")))
}

/// Beats per minute of an immediate tempo change (`data/absoluteTempo/tempoValue` is µs per
/// beat), rounded to 2 decimals; `None` without a metronome value.
pub fn tempo_bpm(ev: &Node) -> Option<f64> {
    let us: f64 = ev.find("data/absoluteTempo/tempoValue")?.value.as_deref()?.parse().ok()?;
    (us != 0.0).then(|| (60_000_000.0 / us * 100.0).round() / 100.0)
}

// ---------------------------------------------------------------------------------------
// version forms

/// `kEventMuted`: Dorico 4 wrote `true`/`false`, Dorico 5 writes an enum (`kAlways`, …).
/// `Some(true)` = always muted, `Some(false)` = not muted, `None` = a value not seen yet.
pub fn event_muted(value: &str) -> Option<bool> {
    match clean_value(value).as_str() {
        "true" | "kAlways" => Some(true),
        "false" | "kNever" => Some(false),
        _ => None,
    }
}

/// Glissando playback type: Dorico 5 writes `kGlissandoPlaybackType` (`kChromatic`, …) on every
/// glissando; older files leave it out, which plays the same as `kChromatic`.
pub fn glissando_playback(value: Option<&str>) -> String {
    value.map(clean_value).filter(|v| !v.is_empty()).unwrap_or_else(|| "kChromatic".to_owned())
}

// ---------------------------------------------------------------------------------------
// library: playing-technique appearances

/// A playing-technique appearance from the project library.
#[derive(Debug, Clone, Serialize)]
pub struct TechniqueAppearance {
    /// Readable name: library `name` ("Open (remove mute)"), else `text`.
    pub name: String,
    /// Library `text`, else `name` (what the reader returned before 2026-10-31; `text` can be
    /// an internal key such as "opentext": show `name`).
    pub text: String,
    /// Playback technique ID (`pt.pizzicato`, …).
    pub technique: String,
}

/// Playing-technique appearance ID -> appearance, from the score's library.
pub fn technique_appearances(root: &Node) -> BTreeMap<String, TechniqueAppearance> {
    root.find("library/playingTechniqueAppearanceCollectionDefinition/entities")
        .map(Node::items)
        .unwrap_or(&[])
        .iter()
        .map(|d| {
            let (name, text) = (d.text("name"), d.text("text"));
            (
                d.text("entityID").to_owned(),
                TechniqueAppearance {
                    name: if name.is_empty() { text } else { name }.to_owned(),
                    text: if text.is_empty() { name } else { text }.to_owned(),
                    technique: d.text("playingTechniqueEntityID").to_owned(),
                },
            )
        })
        .collect()
}

/// Name of a technique appearance; an ID missing from the library reads as words
/// ("pta.stringsDownBow" -> "strings down bow").
pub fn technique_name(appearances: &BTreeMap<String, TechniqueAppearance>, id: &str) -> String {
    appearances.get(id).map(|t| t.name.clone()).filter(|n| !n.is_empty()).unwrap_or_else(|| humanize(id))
}

// ---------------------------------------------------------------------------------------
// tuplets

/// A tuplet's ratio and note value: `tupletDefinition` = `{int: n}, {int: m}, {list: {int:
/// note value}, {int: dots}}, {bool: …}`. Note values: 8 = crotchet, 7 = quaver, 6 =
/// semiquaver, 9 = minim … (each step halves or doubles; checked against tuplet lengths in the
/// Rite of Spring: 3:2 of value 7 lasts 1 crotchet).
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Tuplet {
    /// Notes played (3 in 3:2).
    pub num: i64,
    /// In the time of (2 in 3:2).
    pub den: i64,
    /// Dorico's note-value code (8 = crotchet).
    pub note_value: i64,
    pub dots: i64,
    /// Length of one note value in crotchets (dots applied), e.g. "1/2" for quavers.
    pub unit: Option<Ratio>,
    /// "3:2 quavers", "2:3 dotted crotchets".
    pub name: String,
}

/// Note-value code -> length in crotchets (8 = crotchet, 7 = quaver, …).
pub fn note_value_length(code: i64) -> Option<Ratio> {
    let shift = code - 8;
    match shift {
        0..=4 => Some(Ratio::int(1 << shift)),
        -10..=-1 => Some(Ratio::new(1, 1 << -shift)),
        _ => None,
    }
}

/// Note-value code -> plural name ("quavers").
pub fn note_value_name(code: i64) -> Option<&'static str> {
    Some(match code {
        11 => "breves",
        10 => "semibreves",
        9 => "minims",
        8 => "crotchets",
        7 => "quavers",
        6 => "semiquavers",
        5 => "demisemiquavers",
        4 => "hemidemisemiquavers",
        _ => return None,
    })
}

/// Decode a `tupletDefinition`.
pub fn tuplet(definition: &str) -> Option<Tuplet> {
    let ints = variant_ints(&clean_value(definition));
    let [num, den, note_value, dots, ..] = ints[..] else {
        let [num, den, ..] = ints[..] else { return None };
        return Some(Tuplet { num, den, note_value: 0, dots: 0, unit: None, name: format!("{num}:{den}") });
    };
    let dot_factor = match dots {
        0 => Some(Ratio::ONE),
        1 => Some(Ratio::new(3, 2)),
        2 => Some(Ratio::new(7, 4)),
        3 => Some(Ratio::new(15, 8)),
        _ => None,
    };
    let unit = note_value_length(note_value).zip(dot_factor).map(|(l, f)| l * f);
    let name = match note_value_name(note_value) {
        Some(values) => {
            let dotted = match dots {
                0 => "",
                1 => "dotted ",
                2 => "double-dotted ",
                _ => "multi-dotted ",
            };
            format!("{num}:{den} {dotted}{values}")
        }
        None => format!("{num}:{den} (note value {note_value})"),
    };
    Some(Tuplet { num, den, note_value, dots, unit, name })
}

// ---------------------------------------------------------------------------------------
// keys

/// A key signature.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Key {
    /// Sharps (+) or flats (−): +2 = D major / B minor, −3 = Eb major / C minor; 0 for atonal.
    pub fifths: i32,
    /// "major", "minor", "atonal" (open key: no key signature) or Dorico's type in words.
    pub mode: String,
    /// Tonic ("Eb", "F#"); empty when atonal.
    pub tonic: String,
    /// "Eb major", "F minor", "atonal".
    pub name: String,
}

const ACC_SUFFIX: [(&str, i32); 3] = [(".sharp", 1), (".flat", -1), (".natural", 0)];

fn accidental_of(id: &str) -> Option<i32> {
    ACC_SUFFIX.iter().find(|(s, _)| id.ends_with(s)).map(|(_, a)| *a)
}

/// Decode a `TonalityDivisionElementDefinition` (or its `tonalityDivisionData`). Keys are
/// `keySignature/root`: `tonalityType` (kKeySigMajor / kKeySigMinor / kKeySigAtonal),
/// `root/noteName`, `root/accidentalID` (…western.sharp/flat/natural). Seen in the user's
/// projects and the Rite of Spring (2026-10-31). Other types count the signature's accidentals.
pub fn key_signature(element: &Node) -> Option<Key> {
    let data = element.child("tonalityDivisionData").unwrap_or(element);
    let ks = data.child("keySignature")?;
    let root = ks.child("root");
    let ttype = root.map(|r| r.text("tonalityType")).unwrap_or("");
    let mode = match ttype {
        "kKeySigMajor" => "major".to_owned(),
        "kKeySigMinor" => "minor".to_owned(),
        "kKeySigAtonal" => "atonal".to_owned(),
        "" => String::new(),
        other => humanize(other.trim_start_matches("kKeySig")),
    };
    let letter = root.and_then(|r| r.find("root/noteName")).and_then(|n| n.value.as_deref()).unwrap_or("");
    let acc = root
        .and_then(|r| r.find("root/accidentalID"))
        .and_then(|n| n.value.as_deref())
        .and_then(accidental_of)
        .unwrap_or(0);
    let tonic = if letter.is_empty() || mode == "atonal" {
        String::new()
    } else {
        format!("{letter}{}", accidental_text(acc as i64))
    };
    // from the tonic: position on the circle of fifths
    let from_tonic = || -> Option<i32> {
        let base = match letter {
            "F" => -1,
            "C" => 0,
            "G" => 1,
            "D" => 2,
            "A" => 3,
            "E" => 4,
            "B" => 5,
            _ => return None,
        };
        let shift = match mode.as_str() {
            "major" => 0,
            "minor" => -3,
            _ => return None,
        };
        Some(base + 7 * acc + shift).filter(|f| (-7..=7).contains(f))
    };
    // otherwise: the signature's own accidentals (custom keys)
    let from_accidentals = || -> i32 {
        let accs: Vec<i32> = ks
            .child("accidentals")
            .map(Node::items)
            .unwrap_or(&[])
            .iter()
            .filter_map(|a| a.find("noteNameAndAccidental/accidentalID")?.value.as_deref().and_then(accidental_of))
            .collect();
        let sharps = accs.iter().filter(|&&a| a > 0).count() as i32;
        let flats = accs.iter().filter(|&&a| a < 0).count() as i32;
        sharps - flats
    };
    let fifths = if mode == "atonal" { 0 } else { from_tonic().unwrap_or_else(from_accidentals) };
    let name = match (tonic.is_empty(), mode.is_empty()) {
        (true, _) => if mode.is_empty() { "key".to_owned() } else { mode.clone() },
        (false, true) => tonic.clone(),
        (false, false) => format!("{tonic} {mode}"),
    };
    Some(Key { fifths, mode, tonic, name })
}

// ---------------------------------------------------------------------------------------
// marks

/// Note articulations: Dorico's `kArticulation*` values -> names.
pub const ARTICULATIONS: &[(&str, &str)] = &[
    ("kStaccato", "staccato"),
    ("kStaccatissimo", "staccatissimo"),
    ("kTenuto", "tenuto"),
    ("kStaccatoTenuto", "staccato-tenuto"),
    ("kSpiccato", "spiccato"),
    ("kAccent", "accent"),
    ("kMarcato", "marcato"),
    ("kStress", "stress"),
    ("kUnstress", "unstress"),
];

/// Note properties that hold articulations.
pub const ARTICULATION_PROPERTIES: [&str; 3] = ["kArticulationDuration", "kArticulationForce", "kArticulationStress"];

/// Articulation value ("kStaccatoTenuto" or `string: "…"`) -> name ("staccato-tenuto"); values
/// not in the table read as words.
pub fn articulation_name(value: &str) -> String {
    let v = clean_value(value);
    ARTICULATIONS.iter().find(|(raw, _)| *raw == v).map(|(_, n)| (*n).to_owned()).unwrap_or_else(|| humanize(&v))
}

/// Clef entity -> name: "clef.bass" -> "bass", "clef.treble.8vb" -> "treble 8vb".
pub fn clef_name(entity: &str) -> String {
    entity.strip_prefix("clef.").unwrap_or(entity).replace('.', " ")
}

/// Ottava line entity -> "8va", "8vb", "15ma", "15mb" (others: the entity's tail).
pub fn ottava_name(entity: &str) -> String {
    match entity {
        "line.ottava.up.8" => "8va".to_owned(),
        "line.ottava.down.8" => "8vb".to_owned(),
        "line.ottava.up.15" => "15ma".to_owned(),
        "line.ottava.down.15" => "15mb".to_owned(),
        other => other.strip_prefix("line.ottava.").unwrap_or(other).to_owned(),
    }
}

/// Ornament entity -> words: "ornament.shortTrill" -> "short trill".
pub fn ornament_name(entity: &str) -> String {
    humanize(entity)
}

/// `arpeggioType` -> "up", "down", "non arpeggio", "plain".
pub fn arpeggio_name(kind: &str) -> String {
    match kind {
        "kUpArpeggio" => "up".to_owned(),
        "kDownArpeggio" => "down".to_owned(),
        "kNoArpeggio" => "non arpeggio".to_owned(),
        "kArpeggio" | "" => "plain".to_owned(),
        other => other.to_owned(),
    }
}

/// Glissando line type: `kWavyLine` -> "wavy", `kFlatLine` -> "straight".
pub fn glissando_line_name(kind: &str) -> String {
    match clean_value(kind).as_str() {
        "kWavyLine" => "wavy".to_owned(),
        "kFlatLine" => "straight".to_owned(),
        "" => String::new(),
        other => humanize(other),
    }
}

/// A pause event (fermata, breath mark, caesura) -> "fermata", "fermata (very long)".
/// Accepts the event or its `pauseData` (where Dorico keeps `pauseType`).
pub fn pause_name(ev: &Node) -> String {
    let ev = ev.child("pauseData").unwrap_or(ev);
    let kind = humanize(ev.text("pauseType"));
    match ev.text("fermataDuration") {
        "" | "kNormal" => kind,
        d => format!("{kind} ({})", humanize(d)),
    }
}

/// A divisi change's sections: "1 / 2", "Solo + gli altri", or "unison" (no sections).
pub fn divisi_name(ev: &Node) -> String {
    let labels = |path: &str| -> Vec<String> {
        ev.find(path)
            .map(Node::items)
            .unwrap_or(&[])
            .iter()
            .map(|s| {
                let t = rich_text(s);
                if t.is_empty() { "?".to_owned() } else { t }
            })
            .collect()
    };
    let soloists = labels("sections/soloists");
    let sections = labels("sections/sections");
    match (soloists.is_empty(), sections.is_empty()) {
        (true, true) => "unison".to_owned(),
        (true, false) => sections.join(" / "),
        (false, true) => soloists.join(" + "),
        (false, false) => format!("{} + {}", soloists.join(" + "), sections.join(" / ")),
    }
}

// ---------------------------------------------------------------------------------------
// pitch and duration

const LETTERS: [char; 7] = ['C', 'D', 'E', 'F', 'G', 'A', 'B'];
const LETTER_SEMITONES: [i64; 7] = [0, 2, 4, 5, 7, 9, 11];
/// Without a spelling: sharps (C, C#, D, …).
const DEFAULT_SPELLING: [(usize, i64); 12] =
    [(0, 0), (0, 1), (1, 0), (1, 1), (2, 0), (3, 0), (3, 1), (4, 0), (4, 1), (5, 0), (5, 1), (6, 0)];

/// (letter index C=0..B=6, alteration −2..2, octave) for a MIDI pitch and Dorico's spelled
/// letter (`kNoteSpelling`'s first character); sharps when there is no usable spelling.
pub fn spell(midi: i64, letter: Option<char>) -> (usize, i64, i64) {
    if let Some(i) = letter.and_then(|l| LETTERS.iter().position(|&x| x == l.to_ascii_uppercase())) {
        for acc in [0, -1, 1, -2, 2] {
            if (LETTER_SEMITONES[i] + acc).rem_euclid(12) == midi.rem_euclid(12) {
                return (i, acc, (midi - acc).div_euclid(12) - 1);
            }
        }
    }
    let (l, a) = DEFAULT_SPELLING[midi.rem_euclid(12) as usize];
    (l, a, (midi - a).div_euclid(12) - 1)
}

/// Alteration -> "bb", "b", "", "#", "##".
pub fn accidental_text(a: i64) -> &'static str {
    match a {
        -2 => "bb",
        -1 => "b",
        1 => "#",
        2 => "##",
        _ => "",
    }
}

/// MIDI number -> "Bb4", honouring Dorico's spelled letter when known.
pub fn pitch_name(midi: i64, spelling: Option<&str>) -> String {
    let (l, a, octave) = spell(midi, spelling.and_then(|s| s.chars().next()));
    format!("{}{}{octave}", LETTERS[l], accidental_text(a))
}

/// Length in crotchets -> "dotted crotchet", "minim", or "3/5 crotchets".
pub fn duration_name(d: Ratio) -> String {
    let names: [(Ratio, &str); 8] = [
        (Ratio::int(8), "breve"),
        (Ratio::int(4), "semibreve"),
        (Ratio::int(2), "minim"),
        (Ratio::int(1), "crotchet"),
        (Ratio::new(1, 2), "quaver"),
        (Ratio::new(1, 4), "semiquaver"),
        (Ratio::new(1, 8), "demisemiquaver"),
        (Ratio::new(1, 16), "hemidemisemiquaver"),
    ];
    if let Some((_, n)) = names.iter().find(|(r, _)| *r == d) {
        return (*n).to_owned();
    }
    for (base, name) in names {
        if d == base * Ratio::new(3, 2) {
            return format!("dotted {name}");
        }
        if d == base * Ratio::new(7, 4) {
            return format!("double-dotted {name}");
        }
    }
    format!("{d} crotchets")
}

// ---------------------------------------------------------------------------------------
// time: tempo marks, pauses, film, playback timing options (used by dorico-timeline)

/// A beat unit `{list: {int: 8}, {int: 0}}` (note-value code, dots) -> length in crotchets.
pub fn beat_unit(value: &str) -> Option<Ratio> {
    let ints = variant_ints(&clean_value(value));
    let (&code, dots) = (ints.first()?, ints.get(1).copied().unwrap_or(0));
    let mut len = note_value_length(code)?;
    let mut add = len;
    for _ in 0..dots.clamp(0, 4) {
        add = add / Ratio::int(2);
        len = len + add;
    }
    Some(len)
}

/// µs per beat -> beats per minute, rounded to 2 decimals (as the listing shows them).
fn bpm_of(us: f64) -> Option<f64> {
    (us > 0.0).then(|| (60_000_000.0 / us * 100.0).round() / 100.0)
}

/// A tempo preset from the project library (`library/tempoPresetDefinitions`).
#[derive(Debug, Clone, Serialize)]
pub struct TempoPreset {
    pub name: String,
    pub gradual: bool,
    /// Immediate presets: "kAbsolute" (amount = bpm) or "kRelative" (amount = percent).
    pub immediate_type: String,
    pub amount: Option<f64>,
}

/// Tempo presets by entity ID.
pub fn tempo_presets(root: &Node) -> BTreeMap<String, TempoPreset> {
    root.find("library/tempoPresetDefinitions/entities")
        .map(Node::items)
        .unwrap_or(&[])
        .iter()
        .map(|p| {
            (
                p.text("entityID").to_owned(),
                TempoPreset {
                    name: p.text("name").to_owned(),
                    gradual: p.text("isGradual") == "true",
                    immediate_type: p.text("immediateType").to_owned(),
                    amount: p.text("amount").parse().ok(),
                },
            )
        })
        .collect()
}

/// An immediate tempo change (`ImmediateTempoChangeEventDefinition/data`).
///
/// - `kAbsolute`: `absoluteTempo/tempoValue` = µs per **stated beat unit** (`beatUnits`;
///   ♩. = 60 is 1,000,000 per dotted crotchet); `tempoValueRange` = upper value of "92-96".
/// - `kEquation` (metric modulation): `tempoEquation/left` = `right` as note values, "old = new"
///   (f2d Round 12): the new `right` lasts as long as the old `left`.
/// - `kRelative`: `relativePercent` of the tempo in effect (Dorico stores "meno mosso" as the
///   Mosso preset at 110 %, `modifierFlags` 8; reference flow 7).
/// - `kReset`: `resetType` `kATempo` (back to the last absolute tempo) or `kTempoPrimo` (the
///   flow's first tempo).
#[derive(Debug, Clone, Serialize)]
pub struct TempoMark {
    /// "absolute", "equation", "relative" or Dorico's raw type for anything else.
    pub kind: String,
    /// Beats per minute of the stated unit.
    pub bpm: Option<f64>,
    /// The stated beat unit in crotchets (1 = crotchet, 3/2 = dotted crotchet).
    pub unit: Ratio,
    /// Crotchets per minute (what the timeline uses).
    pub crotchet_bpm: Option<f64>,
    /// Upper value of a metronome range ("92-96"), stated unit.
    pub bpm_max: Option<f64>,
    /// Metric modulation "old = new" as note lengths in crotchets.
    pub equation: Option<(Ratio, Ratio)>,
    /// Relative tempos: percent of the tempo in effect.
    pub percent: Option<f64>,
    /// Reset tempos: "kATempo" or "kTempoPrimo".
    pub reset: String,
    pub preset: String,
    pub text: String,
}

/// Decode an immediate tempo change.
pub fn tempo_mark(ev: &Node, presets: &BTreeMap<String, TempoPreset>) -> TempoMark {
    let data = ev.child("data");
    let get = |p: &str| data.and_then(|d| d.find(p)).and_then(|n| n.value.as_deref()).unwrap_or("");
    let preset = get("presetID").to_owned();
    let unit = beat_unit(get("absoluteTempo/beatUnits")).unwrap_or(Ratio::ONE);
    let bpm = get("absoluteTempo/tempoValue").parse().ok().and_then(bpm_of);
    let bpm_max = get("tempoValueRange").parse().ok().and_then(bpm_of);
    let raw = get("type");
    let kind = match raw {
        "kAbsolute" => "absolute".to_owned(),
        "kEquation" => "equation".to_owned(),
        "kRelative" => "relative".to_owned(),
        "kReset" => "reset".to_owned(),
        "" => "absolute".to_owned(),
        other => other.to_owned(),
    };
    let equation = match (beat_unit(get("tempoEquation/left")), beat_unit(get("tempoEquation/right"))) {
        (Some(l), Some(r)) => Some((l, r)),
        _ => None,
    };
    let percent = (kind == "relative")
        .then(|| get("relativePercent").parse().ok().or_else(|| presets.get(&preset).and_then(|p| p.amount)))
        .flatten();
    TempoMark {
        kind,
        bpm,
        unit,
        crotchet_bpm: bpm.map(|b| b * unit.to_f64()),
        bpm_max,
        equation,
        percent,
        reset: get("resetType").to_owned(),
        preset,
        text: get("text").to_owned(),
    }
}

/// A gradual tempo change (`GradualTempoChangeEventDefinition/data`). Dorico: the final tempo
/// is `finalTempoPercent` of the starting tempo (help: "Final tempo %"). `initialTempo` is
/// Dorico's stored starting tempo.
#[derive(Debug, Clone, Serialize)]
pub struct GradualTempoMark {
    pub final_percent: Option<f64>,
    /// Stored starting tempo, crotchets per minute.
    pub initial_crotchet_bpm: Option<f64>,
    pub preset: String,
    pub text: String,
}

/// Decode a gradual tempo change.
pub fn gradual_tempo_mark(ev: &Node) -> GradualTempoMark {
    let data = ev.child("data");
    let get = |p: &str| data.and_then(|d| d.find(p)).and_then(|n| n.value.as_deref()).unwrap_or("");
    let unit = beat_unit(get("initialTempo/beatUnits")).unwrap_or(Ratio::ONE);
    GradualTempoMark {
        final_percent: get("finalTempoPercent").parse().ok(),
        initial_crotchet_bpm: get("initialTempo/tempoValue").parse().ok().and_then(bpm_of).map(|b| b * unit.to_f64()),
        preset: get("presetID").to_owned(),
        text: get("text").to_owned(),
    }
}

/// A pause (`PauseEventDefinition/pauseData`): fermata, breath mark, caesura …
#[derive(Debug, Clone, Serialize)]
pub struct Pause {
    /// Dorico's `pauseType` ("kFermata", "kBreathMark", "kCaesura" …).
    pub kind: String,
    /// Fermata length as stored ("" = normal): "kNormal", "kVeryShort", "kShort", "kLong", "kVeryLong",
    /// "kShortHenze", "kLongHenze" …
    pub fermata_duration: String,
    /// Readable ("fermata (very long)").
    pub name: String,
}

/// Decode a pause event.
pub fn pause(ev: &Node) -> Pause {
    let d = ev.child("pauseData").unwrap_or(ev);
    Pause {
        kind: d.text("pauseType").to_owned(),
        fermata_duration: d.text("fermataDuration").to_owned(),
        name: pause_name(d),
    }
}

/// A flow's video (`flowVideoData`), confirmed with the user's `ref-film-v1/v2.dorico`
/// (dorigit RESEARCH.md): `videoAttachmentPosition` = where the clip starts in the flow
/// (crotchets); `kVideoEventInTime` = the clip time at that point (seconds);
/// `kVideoClipTimecodeStart` = timecode of the clip's first frame (seconds); markers'
/// `timePosition` is clip time.
#[derive(Debug, Clone, Serialize)]
pub struct Video {
    pub attached: bool,
    /// File name without folders.
    pub file: String,
    pub start: Ratio,
    pub offset: f64,
    pub timecode_start: f64,
    /// The clip's own frame rate (`kVideoClipFrameRate`), if stored.
    pub clip_fps: Option<f64>,
}

/// Decode a flow's video settings (`None` when the flow has no `flowVideoData`).
pub fn video(flow: &Node) -> Option<Video> {
    let v = flow.child("flowVideoData")?;
    let num = |ptype: &str| -> Option<f64> {
        v.find("properties/entries")
            .map(Node::items)
            .unwrap_or(&[])
            .iter()
            .find(|e| e.text("propertyType") == ptype)
            .and_then(|e| clean_value(e.text("value")).strip_prefix("double: ").and_then(|x| x.parse().ok()))
    };
    let path = v.text("videoFilename");
    Some(Video {
        attached: v.text("hasVideoAttached") == "true",
        file: path.rsplit(['/', '\\']).next().unwrap_or(path).to_owned(),
        start: Ratio::parse(v.text("videoAttachmentPosition")),
        offset: num("kVideoEventInTime").unwrap_or(0.0),
        timecode_start: num("kVideoClipTimecodeStart").unwrap_or(0.0),
        clip_fps: num("kVideoClipFrameRate").filter(|f| *f > 0.0),
    })
}

/// A marker (`MarkerEventDefinition`): name, important flag, clip time in seconds.
#[derive(Debug, Clone, Serialize)]
pub struct Marker {
    pub name: String,
    pub important: bool,
    /// Clip time (seconds); Dorico keeps markers on the picture and recomputes `position`.
    pub time: f64,
}

/// Decode a marker event.
pub fn marker(ev: &Node) -> Marker {
    let mut m = Marker { name: String::new(), important: false, time: ev.text("timePosition").parse().unwrap_or(0.0) };
    for e in ev.find("propertyTable/entries").map(Node::items).unwrap_or(&[]) {
        match e.text("propertyType") {
            "kMarkerText" => m.name = clean_value(e.text("value")),
            "kMarkerIsImportant" => m.important = clean_value(e.text("value")) == "true",
            _ => {}
        }
    }
    m
}

/// Play options that decide when things sound (`scoreOptions/playbackOptions`). Missing
/// options get Dorico's defaults as found in the user's projects (older projects lack
/// `pausePlaybackOptions`).
#[derive(Debug, Clone, Serialize)]
pub struct PlaybackTiming {
    pub play_repeats: bool,
    pub play_repeats_after_ds: bool,
    pub play_pauses: bool,
    /// Fermata length (`kNormal`, `kLongHenze` …) -> (elongation %, silence %).
    pub fermata_percent: BTreeMap<String, (f64, f64)>,
    pub breath_mark_shortening_percent: f64,
    pub caesura_silence_percent: f64,
    pub gap_between_flows: f64,
    pub pre_roll: f64,
    /// `timeDisplayPlaybackOptions/projectFrameRate` ("k25") and `useDropFormat`.
    pub project_frame_rate: String,
    pub use_drop_format: bool,
    pub show_timecode: bool,
}

/// Read the play options that affect timing.
pub fn playback_timing(root: &Node) -> PlaybackTiming {
    let o = root.find("scoreOptions/playbackOptions");
    let get = |p: &str| o.and_then(|o| o.find(p)).and_then(|n| n.value.as_deref());
    let flag = |p: &str, d: bool| get(p).map(|v| v == "true").unwrap_or(d);
    let num = |p: &str, d: f64| get(p).and_then(|v| v.parse().ok()).unwrap_or(d);
    let mut fermata_percent = BTreeMap::new();
    for (key, opt, e, s) in [
        ("kVeryShort", "veryShort", 15.0, 15.0),
        ("kShort", "short", 25.0, 25.0),
        ("kNormal", "normal", 50.0, 50.0),
        ("kLong", "long", 100.0, 100.0),
        ("kVeryLong", "veryLong", 200.0, 200.0),
        ("kShortHenze", "shortHenze", 25.0, 25.0),
        ("kLongHenze", "longHenze", 100.0, 100.0),
    ] {
        let p = |what: &str| format!("pausePlaybackOptions/{opt}{what}Percent");
        fermata_percent.insert(key.to_owned(), (num(&p("Elongation"), e), num(&p("Silence"), s)));
    }
    PlaybackTiming {
        play_repeats: flag("repeatsPlaybackOptions/playRepeats", true),
        play_repeats_after_ds: flag("repeatsPlaybackOptions/playRepeatsAfterDS", false),
        play_pauses: flag("pausePlaybackOptions/playPauses", true),
        fermata_percent,
        breath_mark_shortening_percent: num("pausePlaybackOptions/breathMarkShorteningPercent", 50.0),
        caesura_silence_percent: num("pausePlaybackOptions/caesuraSilencePercent", 50.0),
        gap_between_flows: num("gapBetweenFlowsSeconds", 5.0),
        pre_roll: num("preRollBeforeFlowSeconds", 0.0),
        project_frame_rate: get("timeDisplayPlaybackOptions/projectFrameRate").unwrap_or("").to_owned(),
        use_drop_format: flag("timeDisplayPlaybackOptions/useDropFormat", false),
        show_timecode: flag("timeDisplayPlaybackOptions/showTimecode", false),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn leaf(t: &str, v: &str) -> Node {
        Node::leaf(t, v)
    }
    fn el(t: &str, k: Vec<Node>) -> Node {
        Node::element(t, k)
    }
    fn key(ttype: &str, letter: &str, acc: &str) -> Node {
        let mut root = vec![leaf("tonalityType", ttype)];
        if !letter.is_empty() {
            root.push(el(
                "root",
                vec![leaf("noteName", letter), leaf("accidentalID", &format!("accidental.12et.western.{acc}"))],
            ));
        }
        el(
            "TonalityDivisionElementDefinition",
            vec![el("tonalityDivisionData", vec![el("keySignature", vec![el("root", root), leaf("accidentals", "")])])],
        )
    }

    #[test]
    fn keys() {
        let k = key_signature(&key("kKeySigMajor", "A", "flat")).unwrap();
        assert_eq!((k.fifths, k.name.as_str()), (-4, "Ab major"));
        let k = key_signature(&key("kKeySigMinor", "C", "natural")).unwrap();
        assert_eq!((k.fifths, k.name.as_str()), (-3, "C minor"));
        let k = key_signature(&key("kKeySigMinor", "B", "flat")).unwrap();
        assert_eq!((k.fifths, k.mode.as_str()), (-5, "minor"));
        let k = key_signature(&key("kKeySigMajor", "G", "natural")).unwrap();
        assert_eq!(k.fifths, 1);
        let k = key_signature(&key("kKeySigAtonal", "", "")).unwrap();
        assert_eq!((k.fifths, k.name.as_str(), k.tonic.as_str()), (0, "atonal", ""));
    }

    #[test]
    fn tuplets() {
        let t = tuplet("steamVariantList:list: {int: 3}, {int: 2}, {list: {int: 7}, {int: 0}}, {bool: true}").unwrap();
        assert_eq!((t.num, t.den, t.unit, t.name.as_str()), (3, 2, Some(Ratio::new(1, 2)), "3:2 quavers"));
        assert_eq!(tuplet("{int: 5}, {int: 4}, {list: {int: 6}, {int: 0}}, {bool: true}").unwrap().name, "5:4 semiquavers");
        let t = tuplet("{int: 2}, {int: 3}, {list: {int: 8}, {int: 1}}").unwrap();
        assert_eq!((t.name.as_str(), t.unit), ("2:3 dotted crotchets", Some(Ratio::new(3, 2))));
        assert_eq!(tuplet("{int: 3}, {int: 2}, {list: {int: 2}, {int: 0}}").unwrap().name, "3:2 (note value 2)");
        assert!(tuplet("").is_none());
    }

    #[test]
    fn names() {
        assert_eq!(humanize("pta.stringsDownBow"), "strings down bow");
        assert_eq!(humanize("shortTrill"), "short trill");
        assert_eq!(humanize("kSustainPedal"), "sustain pedal");
        assert_eq!(humanize("kind"), "kind");
        assert_eq!(glyphs("Clarinet (B{@flat@})"), "Clarinet (B♭)");
        assert_eq!(articulation_name("kStaccatoTenuto"), "staccato-tenuto");
        assert_eq!(articulation_name("string: \"kTenuto\""), "tenuto");
        assert_eq!(articulation_name("kSoftAccent"), "soft accent");
        assert_eq!(clef_name("clef.treble.8vb"), "treble 8vb");
        assert_eq!(ottava_name("line.ottava.down.15"), "15mb");
        assert_eq!(ornament_name("ornament.shortTrill"), "short trill");
        assert_eq!(arpeggio_name("kNoArpeggio"), "non arpeggio");
        assert_eq!(glissando_line_name("string: \"kWavyLine\""), "wavy");
        assert_eq!(variant_ints("steamVariantList:list: {int: 23999}, {int: -1}"), vec![23999, -1]);
        assert_eq!(clean_value("string: \"kMarcato\""), "kMarcato");
    }

    #[test]
    fn version_forms() {
        assert_eq!(event_muted("true"), Some(true));
        assert_eq!(event_muted("string: \"kAlways\""), Some(true));
        assert_eq!(event_muted("false"), Some(false));
        assert_eq!(glissando_playback(None), "kChromatic");
        assert_eq!(glissando_playback(Some("string: \"kChromatic\"")), "kChromatic");
    }

    #[test]
    fn pitches() {
        assert_eq!(pitch_name(70, Some("B")), "Bb4");
        assert_eq!(pitch_name(70, Some("A")), "A#4");
        assert_eq!(pitch_name(60, None), "C4");
        assert_eq!(pitch_name(61, None), "C#4");
        assert_eq!(pitch_name(60, Some("B")), "B#3");
        assert_eq!(spell(70, Some('b')), (6, -1, 4));
        assert_eq!(duration_name(Ratio::new(3, 2)), "dotted crotchet");
        assert_eq!(duration_name(Ratio::new(3, 5)), "3/5 crotchets");
    }

    #[test]
    fn beat_units() {
        assert_eq!(beat_unit("steamVariantList:list: {list: {int: 8}, {int: 0}}"), Some(Ratio::ONE));
        assert_eq!(beat_unit("steamVariantList:list: {list: {int: 8}, {int: 1}}"), Some(Ratio::new(3, 2)));
        assert_eq!(beat_unit("steamVariantList:list: {list: {int: 9}, {int: 0}}"), Some(Ratio::int(2)));
        assert_eq!(beat_unit("steamVariantList:list: {list: {int: 7}, {int: 2}}"), Some(Ratio::new(7, 8)));
        assert_eq!(beat_unit(""), None);
    }
}
