//! One read model of a Dorico score for every tool (Project S, S4).
//!
//! Superset of the three readers it replaces: dorigit's listing model
//! (`dorico_format::model`), finale2dorico's reviewer reader (`f2d/dorico/read.py`) and
//! dorico-hp's `notation.py`. Positions are exact [`Ratio`]s in crotchets from the start of
//! the flow (block-instance offsets applied); pitches are concert MIDI numbers.
//!
//! ```text
//! Score ─ players (instruments)            library: technique appearances
//!       ─ flows ─ bars, time signatures, barlines, keys, tempos, rehearsal marks
//!               ─ parts (one per instrument of a player)
//!                    ─ staves: dynamics groups, clefs, stave marks (harp pedals, ottavas, ...)
//!                    ─ voices: notes, voice marks (slurs, trills, techniques, glissandi, ...)
//! ```
//!
//! Serialises to JSON (serde); `Ratio` values are strings like "81/4".
//!
//! Every decoding and readable name comes from `dorico_format::vocab` and
//! `dorico_format::dynamics` (the engine's one copy); this crate only arranges them.

use dorico_format::dtn::Node;
use dorico_format::dynamics;
use dorico_format::ratio::Ratio;
use dorico_format::tree::{ElementTables as Tables, element_tables, props};
use dorico_format::vocab::{self, clean_value};
use serde::Serialize;
use std::collections::{BTreeMap, HashMap};

pub use dorico_format::bars::{self, Bar, NumberChange, compute_bars};
pub use dorico_format::vocab::{
    ARTICULATIONS, Key, Marker, Pause, PlaybackTiming, TechniqueAppearance, Tuplet, Video, event_text,
    technique_appearances,
};

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize)]
pub struct Score {
    pub title: String,
    /// `info` leaves (title, composer, ...).
    pub info: BTreeMap<String, String>,
    pub players: Vec<Player>,
    pub flows: Vec<Flow>,
    /// Playing-technique appearance ID -> written text + playback technique (from the library).
    pub technique_appearances: BTreeMap<String, TechniqueAppearance>,
    /// Instrument types defined in the project library, by entity ID.
    pub instruments: BTreeMap<String, InstrumentDef>,
    /// Play options that decide when things sound (repeats, pauses, flow gap, frame rate).
    pub playback: PlaybackTiming,
}

/// An instrument type from the project library (concert pitch ranges like "C4-C7").
#[derive(Debug, Clone, Serialize)]
pub struct InstrumentDef {
    pub name: String,
    pub standard_range: String,
    pub advanced_range: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct Player {
    pub id: String,
    /// As stored (Dorico 5 writes glyph tokens: "Trumpet (B{@flat@})").
    pub name: String,
    /// Readable: glyph tokens as characters ("Trumpet (B♭)").
    pub label: String,
    pub instruments: Vec<PlayerInstrument>,
}

#[derive(Debug, Clone, Serialize)]
pub struct PlayerInstrument {
    pub id: String,
    /// Dorico instrument type (e.g. `instrument.wind.flute`).
    pub entity: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct Flow {
    pub id: String,
    pub name: String,
    /// End of the music: last event end, block placement or `minimumNotatedLength`.
    pub length: Ratio,
    pub bars: Vec<Bar>,
    pub time_signatures: Vec<TimeSignature>,
    pub barlines: Vec<Barline>,
    /// Positions of key changes (`TonalityDivision`). Kept for callers; `keys` has the keys.
    pub key_changes: Vec<Ratio>,
    /// Key changes of the whole flow (global stream), with the key. A stave can have its own
    /// key (e.g. an open-key timpani stave): those are stave marks of kind "key".
    pub keys: Vec<KeyChange>,
    pub tempos: Vec<Tempo>,
    pub rehearsal_marks: Vec<Ratio>,
    /// Bar-number changes (from any stream: Dorico may store them on a stave).
    pub bar_number_changes: Vec<NumberChange>,
    /// Repeat structure: kind "segno", "coda", "fine", "jump" (detail: jump, qualification,
    /// e.g. kDalSegno + kAlCoda, kToCoda + kEndOfFlow) and "ending" (1st/2nd-time bar line;
    /// detail: segments). Repeat barlines are in `barlines`.
    pub repeats: Vec<Mark>,
    /// 1st/2nd-time endings with their segment lengths (also listed in `repeats`).
    pub endings: Vec<Ending>,
    /// Pauses on the whole flow (global stream); stave pauses are stave marks of kind "pause".
    pub pauses: Vec<FlowPause>,
    /// Attached video, if the flow has video settings.
    pub video: Option<Video>,
    pub markers: Vec<FlowMarker>,
    pub parts: Vec<Part>,
}

#[derive(Debug, Clone, Serialize)]
pub struct TimeSignature {
    pub pos: Ratio,
    pub num: i64,
    pub den: i64,
    pub beat_unit: String,
    pub beat_groups: Vec<i64>,
    /// Length of the bar that starts here if it is irregular (pick-up).
    pub pickup: Option<Ratio>,
}

#[derive(Debug, Clone, Serialize)]
pub struct KeyChange {
    pub pos: Ratio,
    pub event_id: String,
    #[serde(flatten)]
    pub key: Key,
}

#[derive(Debug, Clone, Serialize)]
pub struct Barline {
    pub pos: Ratio,
    pub kind: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct Tempo {
    pub pos: Ratio,
    /// Beats per minute of the stated beat unit (`unit`); see `crotchet_bpm`.
    pub bpm: Option<f64>,
    pub text: String,
    pub gradual: bool,
    pub end: Option<Ratio>,
    pub final_percent: Option<f64>,
    pub event_id: String,
    /// "absolute", "equation" (metric modulation), "relative", "reset", "gradual" or Dorico's raw type.
    pub kind: String,
    /// Stated beat unit in crotchets (♩. = 3/2).
    pub unit: Ratio,
    /// Crotchets per minute: immediate tempos with a metronome value; gradual tempos: Dorico's
    /// stored starting tempo.
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
}

/// A 1st/2nd-time ending line: one segment per ending, in order.
#[derive(Debug, Clone, Serialize)]
pub struct Ending {
    pub event_id: String,
    pub pos: Ratio,
    pub end: Ratio,
    /// Length of each segment (crotchets).
    pub segments: Vec<Ratio>,
    /// Passes through the repeated section (`kRepeatEndingLineNumTimesPlayed`; Dorico's
    /// "repeat 3 times" = 4). The first segment plays on every pass but the last ones, each
    /// later segment on one pass. `None` = one pass per segment.
    pub times_played: Option<u32>,
}

/// A marker at a flow position (film): Dorico keeps the marker's clip time and recomputes `pos`.
#[derive(Debug, Clone, Serialize)]
pub struct FlowMarker {
    pub pos: Ratio,
    pub event_id: String,
    #[serde(flatten)]
    pub marker: Marker,
}

/// A pause on every stave (global stream): fermata, caesura, breath mark.
#[derive(Debug, Clone, Serialize)]
pub struct FlowPause {
    pub pos: Ratio,
    pub event_id: String,
    #[serde(flatten)]
    pub pause: Pause,
}

/// One instrument held by a player in a flow.
#[derive(Debug, Clone, Serialize)]
pub struct Part {
    pub player_id: String,
    /// As stored (may hold glyph tokens).
    pub player_name: String,
    /// Readable ("Trumpet (B♭)").
    pub player_label: String,
    pub instrument_id: String,
    pub entity: String,
    /// 1-based number of this instrument within its player (doublings: 2, 3, ...).
    pub number: usize,
    /// How many instruments the player holds in this flow.
    pub of: usize,
    pub staves: Vec<Stave>,
    pub voices: Vec<Voice>,
}

#[derive(Debug, Clone, Serialize)]
pub struct Stave {
    /// 0-based stave of the instrument (`nthStaveInInstrument`).
    pub index: usize,
    pub stave_id: String,
    pub stream_id: String,
    /// Divisi staves: 0-based divisi index (every divisi stave also has `index` 0).
    pub divisi: Option<i64>,
    pub dynamics: Vec<DynamicGroup>,
    pub marks: Vec<Mark>,
}

#[derive(Debug, Clone, Serialize)]
pub struct Voice {
    pub stream_id: String,
    /// The stave this voice belongs to by default (index and ID; divisi staves share index 0).
    pub stave_index: usize,
    pub stave_id: String,
    pub notes: Vec<Note>,
    pub marks: Vec<Mark>,
}

#[derive(Debug, Clone, Serialize)]
pub struct Note {
    pub event_id: String,
    pub pos: Ratio,
    pub dur: Ratio,
    pub pitch: i64,
    pub grace: bool,
    pub articulations: Vec<String>,
    pub tremolo: bool,
    /// Muted in playback (`kEventMuted`: Dorico 4 `true`, Dorico 5 `kAlways`).
    #[serde(skip_serializing_if = "is_false")]
    pub muted: bool,
    /// Unscoped properties (`kNoteVelocity`, `kNoteSpelling`, ...), raw values.
    pub props: BTreeMap<String, String>,
}

/// Anything else on a stave or voice: slur, trill, technique, glissando, arpeggio, tuplet,
/// text, clef, harp pedals, ottava, pedal line, divisi, rest, key, ornament, pause, line,
/// bar rest, stave count change; other events keep their Dorico name as kind.
#[derive(Debug, Clone, Serialize)]
pub struct Mark {
    pub kind: String,
    pub event_id: String,
    pub pos: Ratio,
    /// `pos + duration` when the mark has a length.
    pub end: Option<Ratio>,
    /// Readable name where one exists ("Pizzicato", "3:2 quavers", "8va", "bass", "up",
    /// "short trill", "Solo + gli altri", "F minor", "wavy").
    #[serde(skip_serializing_if = "String::is_empty")]
    pub name: String,
    /// Kind-specific details (appearance, text, technique, type, entity, pedals, ...).
    pub detail: BTreeMap<String, String>,
    /// Tuplets: ratio and note value.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tuplet: Option<Tuplet>,
    /// Stave key changes: the key.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub key: Option<Key>,
}

fn is_false(b: &bool) -> bool {
    !*b
}

impl Mark {
    /// A mark with no name or typed detail.
    pub fn plain(kind: String, event_id: &str, pos: Ratio, end: Option<Ratio>, detail: BTreeMap<String, String>) -> Mark {
        Mark { kind, event_id: event_id.to_owned(), pos, end, name: String::new(), detail, tuplet: None, key: None }
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct DynamicGroup {
    pub event_id: String,
    pub pos: Ratio,
    pub element_id: String,
    /// Number of events sharing the element: > 1 means the dynamics are linked across staves.
    pub linked: usize,
    pub items: Vec<DynamicItem>,
}

#[derive(Debug, Clone, Serialize)]
pub struct DynamicItem {
    pub pos: Ratio,
    /// "dynamic", "hairpin", "combined", "force" or the raw definition name.
    pub kind: String,
    /// Machine value: "mf", "cresc", "dim", "fp", "mf-mp", "sfz", ... (`dynamics::level`).
    pub level: String,
    pub end: Option<Ratio>,
    /// Force dynamics: `intensityLevel`; hairpins: appearance (niente, ...).
    pub extra: String,
    /// Readable, as Dorico shows it: "subito mf", "poco f", "sffz", "dim. hairpin al niente
    /// over 2", "custom dynamic (…)" (`dynamics::describe`).
    pub name: String,
}

impl Voice {
    /// Notes grouped into chords: same position and grace-ness, in time order.
    pub fn chords(&self) -> Vec<Vec<&Note>> {
        let mut map: BTreeMap<(Ratio, bool), Vec<&Note>> = BTreeMap::new();
        for n in &self.notes {
            map.entry((n.pos, n.grace)).or_default().push(n);
        }
        let mut v: Vec<_> = map.into_iter().collect();
        v.sort_by_key(|((p, g), _)| (*p, !*g));
        v.into_iter().map(|(_, n)| n).collect()
    }
}

impl Flow {
    /// 1-based bar index and the bar containing `pos`.
    pub fn bar_at(&self, pos: Ratio) -> Option<&Bar> {
        bars::bar_at(&self.bars, pos)
    }
}

// ---------------------------------------------------------------------------
// Reading
// ---------------------------------------------------------------------------

fn items_at<'a>(n: &'a Node, path: &str) -> &'a [Node] {
    n.find(path).map(Node::items).unwrap_or(&[])
}

/// Every unscoped property as raw values.
fn prop_map(n: &Node) -> BTreeMap<String, String> {
    props::entries(n)
        .iter()
        .filter(|e| e.child("context").is_none())
        .map(|e| (e.text("propertyType").to_owned(), e.text("value").to_owned()))
        .collect()
}

fn dynamic_group(event_id: &str, pos: Ratio, element_id: &str, el: Option<&Node>) -> DynamicGroup {
    let refs = el.map(|e| e.text("referencingEventIDs")).unwrap_or("");
    let linked = if refs.is_empty() { 1 } else { refs.split(',').count() };
    let mut items = Vec::new();
    for s in el.map(|e| items_at(e, "subElements")).unwrap_or(&[]) {
        let p = pos + Ratio::parse(s.text("position"));
        let l = dynamics::level(s);
        items.push(DynamicItem {
            pos: p,
            kind: l.kind,
            level: l.level,
            end: l.duration.map(|d| p + d),
            extra: l.extra,
            name: dynamics::describe(s),
        });
    }
    DynamicGroup { event_id: event_id.to_owned(), pos, element_id: element_id.to_owned(), linked, items }
}

/// What the flow's marks need to look things up: the library's technique appearances and the
/// flow's element tables (keys).
struct Lookup<'a> {
    techniques: &'a BTreeMap<String, TechniqueAppearance>,
    tables: &'a Tables<'a>,
}

impl Lookup<'_> {
    fn key(&self, ev: &Node) -> Option<Key> {
        let el = self.tables.get("TonalityDivision")?.get(ev.text("tonalityDivisionElementID"))?;
        vocab::key_signature(el)
    }
}

/// `fromNoteEventAndBlockInstanceIDs` -> the note's event ID ("" when unattached: -1).
fn attached_event(v: &str) -> String {
    match vocab::variant_ints(&clean_value(v)).first() {
        Some(&id) if id >= 0 => id.to_string(),
        _ => String::new(),
    }
}

fn mark(ev: &Node, pos: Ratio, look: &Lookup) -> Mark {
    let tag: &str = &ev.tag;
    let base = tag.strip_suffix("EventDefinition").unwrap_or(tag);
    let dur = Ratio::parse(ev.text("duration"));
    let mut detail = BTreeMap::new();
    let mut put = |k: &str, v: &str| {
        if !v.is_empty() {
            detail.insert(k.to_owned(), clean_value(v));
        }
    };
    let (mut name, mut tuplet, mut key) = (String::new(), None, None);
    let kind: String = match base {
        "Slur" => "slur".into(),
        "Trill" => "trill".into(),
        "Tuplet" => {
            let def = ev.text("tupletDefinition");
            put("definition", def);
            tuplet = vocab::tuplet(def);
            name = tuplet.as_ref().map(|t| t.name.clone()).unwrap_or_default();
            "tuplet".into()
        }
        "Arpeggio" => {
            put("type", ev.text("arpeggioType"));
            name = vocab::arpeggio_name(ev.text("arpeggioType"));
            "arpeggio".into()
        }
        "GlissandoLine" => {
            let line = props::get(ev, "kGlissandoLineType").unwrap_or("");
            put("type", line);
            put("from", ev.text("fromNoteEventAndBlockInstanceIDs"));
            put("to", ev.text("toNoteEventAndBlockInstanceIDs"));
            put("from_event", &attached_event(ev.text("fromNoteEventAndBlockInstanceIDs")));
            put("to_event", &attached_event(ev.text("toNoteEventAndBlockInstanceIDs")));
            put("playback", &vocab::glissando_playback(props::get(ev, "kGlissandoPlaybackType")));
            name = vocab::glissando_line_name(line);
            "glissando".into()
        }
        "PlayingTechnique" => {
            let aid = ev.text("appearanceEntityID");
            put("appearance", aid);
            if let Some(t) = look.techniques.get(aid) {
                put("text", &t.text);
                put("technique", &t.technique);
            }
            name = vocab::technique_name(look.techniques, aid);
            "technique".into()
        }
        "Clef" => {
            let entity = ev.find("entityIDs/idForTransposingLayouts").and_then(|n| n.value.as_deref()).unwrap_or("");
            put("entity", entity);
            name = if entity.is_empty() { String::new() } else { vocab::clef_name(entity) };
            "clef".into()
        }
        "HarpPedal" => {
            for p in ev.child("pedalSettings").map(|n| n.children.as_slice()).unwrap_or(&[]) {
                put(&p.tag, p.value.as_deref().unwrap_or(""));
            }
            "harp pedals".into()
        }
        "OttavaLine" => {
            put("entity", ev.text("entityID"));
            name = vocab::ottava_name(ev.text("entityID"));
            "ottava".into()
        }
        "PedalLine" => {
            put("type", ev.text("pedalLineType"));
            name = vocab::humanize(ev.text("pedalLineType"));
            "pedal".into()
        }
        "Divisi" => {
            name = vocab::divisi_name(ev);
            "divisi".into()
        }
        "Rest" => "rest".into(),
        "BarRest" => "bar rest".into(),
        "Text" => {
            put("text", &event_text(ev));
            "text".into()
        }
        "Ornament" => {
            put("entity", ev.text("entityID"));
            name = vocab::ornament_name(ev.text("entityID"));
            "ornament".into()
        }
        "Pause" => {
            let pause = vocab::pause(ev);
            put("type", &pause.kind);
            put("duration", &pause.fermata_duration);
            name = vocab::pause_name(ev);
            "pause".into()
        }
        "TonalityDivision" => {
            key = look.key(ev);
            name = key.as_ref().map(|k| k.name.clone()).unwrap_or_default();
            "key".into()
        }
        "HorizontalLine" => {
            put("style", ev.text("lineStyleEntityID"));
            put("placement", props::get(ev, "kHorizontalLinePlacement").unwrap_or(""));
            put("start_attachment", ev.text("startAttachmentType"));
            put("end_attachment", ev.text("endAttachmentType"));
            put("system", ev.text("systemLine"));
            name = vocab::humanize(ev.text("lineStyleEntityID"));
            "line".into()
        }
        "StaveCountChange" => {
            put("stave_count", ev.text("staveCount"));
            put("staves_to_show", ev.text("stavesToShow"));
            put("staves_to_hide", ev.text("stavesToHide"));
            "stave count change".into()
        }
        other => {
            if tag.contains("Text") {
                put("text", &event_text(ev));
            }
            other.into()
        }
    };
    Mark {
        kind,
        event_id: ev.text("eventID").to_owned(),
        pos,
        end: (!dur.is_zero()).then_some(pos + dur),
        name,
        detail,
        tuplet,
        key,
    }
}

fn note(ev: &Node, pos: Ratio) -> Note {
    let props = prop_map(ev);
    let mut articulations = Vec::new();
    for k in vocab::ARTICULATION_PROPERTIES {
        if let Some(v) = props.get(k) {
            let a = vocab::articulation_name(v);
            if !articulations.contains(&a) {
                articulations.push(a);
            }
        }
    }
    Note {
        event_id: ev.text("eventID").to_owned(),
        pos,
        dur: Ratio::parse(ev.text("duration")),
        pitch: ev.text("pitch").parse().unwrap_or(0),
        grace: &*ev.tag == "GraceNoteEventDefinition",
        articulations,
        tremolo: props.contains_key("kNoteSingleStemTremolo"),
        muted: props.get("kEventMuted").and_then(|v| vocab::event_muted(v)).unwrap_or(false),
        props,
    }
}

fn players(root: &Node) -> Vec<Player> {
    items_at(root, "scorePlayers/array")
        .iter()
        .map(|p| {
            let id = p.text("playerID").to_owned();
            let name = vocab::player_name(p);
            let label = vocab::glyphs(&name);
            let instruments = p
                .child("instruments")
                .map(Node::items)
                .unwrap_or(&[])
                .iter()
                .map(|i| {
                    let entity = match i.text("entityID") {
                        "" => i.text("instrumentEntityID"),
                        e => e,
                    };
                    PlayerInstrument { id: i.text("instrumentID").to_owned(), entity: entity.to_owned() }
                })
                .collect();
            Player { id, name, label, instruments }
        })
        .collect()
}

/// Events of every stream: stream ID -> [(absolute position, event)], following each stream's
/// block instances (a block can be placed more than once).
fn stream_events(flow: &Node) -> HashMap<&str, Vec<(Ratio, &Node)>> {
    let blocks: HashMap<&str, &Node> = items_at(flow, "blocks/array").iter().map(|b| (b.text("blockID"), b)).collect();
    let mut out: HashMap<&str, Vec<(Ratio, &Node)>> = HashMap::new();
    for bi in items_at(flow, "blockInstances/array") {
        let Some(b) = blocks.get(bi.text("blockID")) else { continue };
        let base = Ratio::parse(bi.text("position"));
        let list = out.entry(bi.text("streamID")).or_default();
        for ev in b.child("events").map(Node::items).unwrap_or(&[]) {
            list.push((base + Ratio::parse(ev.text("position")), ev));
        }
    }
    for list in out.values_mut() {
        list.sort_by_key(|(p, _)| *p);
    }
    out
}

pub fn read_score(root: &Node) -> Score {
    let info = root
        .child("info")
        .map(|i| i.children.iter().map(|c| (c.tag.to_string(), c.value.as_deref().unwrap_or("").to_owned())).collect())
        .unwrap_or_default();
    let players = players(root);
    let techniques = technique_appearances(root);
    let presets = vocab::tempo_presets(root);
    let flows = items_at(root, "flows/array").iter().map(|f| read_flow(f, &players, &techniques, &presets)).collect();
    Score {
        title: root.find("info/title").and_then(|n| n.value.as_deref()).unwrap_or("").to_owned(),
        info,
        players,
        flows,
        technique_appearances: techniques,
        instruments: instrument_defs(root),
        playback: vocab::playback_timing(root),
    }
}

fn instrument_defs(root: &Node) -> BTreeMap<String, InstrumentDef> {
    items_at(root, "library/instruments/entities")
        .iter()
        .map(|e| {
            let pd = e.child("pitchedInstrumentData");
            let get = |t: &str| pd.map(|p| p.text(t)).unwrap_or("").to_owned();
            (
                e.text("entityID").to_owned(),
                InstrumentDef {
                    name: e.text("name").to_owned(),
                    standard_range: get("standardRange"),
                    advanced_range: get("advancedRange"),
                },
            )
        })
        .collect()
}

fn read_flow(
    f: &Node,
    players: &[Player],
    techniques: &BTreeMap<String, TechniqueAppearance>,
    presets: &BTreeMap<String, vocab::TempoPreset>,
) -> Flow {
    let tables = element_tables(f);
    let look = Lookup { techniques, tables: &tables };
    let events = stream_events(f);
    let empty = Vec::new();
    let on = |sid: &str| events.get(sid).unwrap_or(&empty);

    // --- global stream ---------------------------------------------------------------
    let mut time_signatures = Vec::new();
    let mut barlines = Vec::new();
    let mut key_changes = Vec::new();
    let mut keys = Vec::new();
    let mut tempos = Vec::new();
    let mut rehearsal_marks = Vec::new();
    let mut divisions = Vec::new();
    let mut repeats = Vec::new();
    let mut endings = Vec::new();
    let mut pauses = Vec::new();
    let mut markers = Vec::new();
    for s in items_at(f, "eventStreams/array").iter().filter(|s| s.text("eventStreamType") == "kGlobalTimebaseStream") {
        for &(pos, ev) in on(s.text("streamID")) {
            match &*ev.tag {
                "BarDivisionEventDefinition" => {
                    let el = tables.get("BarDivision").and_then(|t| t.get(ev.text("barDivisionElementID")));
                    let bd = el.and_then(|e| e.child("barDivisionData"));
                    let pickup = bd.map(|b| b.text("irregularBarLength")).filter(|s| !s.is_empty()).map(Ratio::parse);
                    let sig = bd
                        .and_then(|b| b.find("timeSignature/timeSignaturesAndDivisions"))
                        .and_then(|a| a.items().first())
                        .and_then(|t| t.child("timeSignature"));
                    let mut ts = None;
                    if let Some(sig) = sig {
                        let num = sig.text("numerator").parse().unwrap_or(4);
                        let den = sig.text("denominator").parse().unwrap_or(4);
                        let g = sig.find("beatGroupingAndOptions/beatGrouping");
                        let unit = g.map(|g| g.text("beatUnit")).unwrap_or("").to_owned();
                        let groups = g
                            .map(|g| clean_value(g.text("beatLengthsInUnits")))
                            .unwrap_or_default()
                            .split(',')
                            .filter_map(|t| {
                                t.trim().trim_start_matches("{int:").trim_end_matches('}').trim().parse().ok()
                            })
                            .collect();
                        time_signatures.push(TimeSignature {
                            pos,
                            num,
                            den,
                            beat_unit: unit,
                            beat_groups: groups,
                            pickup,
                        });
                        ts = Some((num, den));
                    }
                    if let Some(kind) =
                        bd.and_then(|b| b.find("barlineChangeIfAny/type")).and_then(|n| n.value.as_deref())
                    {
                        barlines.push(Barline { pos, kind: kind.to_owned() });
                    }
                    divisions.push(bars::Division { pos, time_signature: ts, pickup });
                }
                "RepeatMarkerEventDefinition" => {
                    let mut detail = BTreeMap::new();
                    let section = ev.text("sectionType");
                    let jump = ev.find("jumpTypeAndQualification/jumpType").and_then(|n| n.value.as_deref());
                    let kind = match (section, jump) {
                        (_, Some(j)) => {
                            detail.insert("jump".to_owned(), j.to_owned());
                            let q = ev.find("jumpTypeAndQualification/jumpQualification");
                            if let Some(q) = q.and_then(|n| n.value.as_deref()) {
                                detail.insert("qualification".to_owned(), q.to_owned());
                            }
                            "jump".to_owned()
                        }
                        ("", None) => "repeat marker".to_owned(),
                        (sec, None) => sec.trim_start_matches('k').to_lowercase(),
                    };
                    repeats.push(Mark::plain(kind, ev.text("eventID"), pos, None, detail));
                }
                "RepeatEndingLineEventDefinition" => {
                    let mut detail = BTreeMap::new();
                    if let Some(n) = props::get(ev, "kRepeatEndingLineNumSegments") {
                        detail.insert("segments".to_owned(), clean_value(n));
                    }
                    let dur = Ratio::parse(ev.text("duration"));
                    // segment k's length: kRepeatEndingLineSegmentDuration with propertyOffset "2:k:0:0"
                    let mut segs: BTreeMap<usize, Ratio> = BTreeMap::new();
                    for e in ev.find("propertyTable/entries").map(Node::items).unwrap_or(&[]) {
                        if e.text("propertyType") == "kRepeatEndingLineSegmentDuration" {
                            let off = clean_value(e.find("context/propertyOffset").and_then(|n| n.value.as_deref()).unwrap_or(""));
                            let k = off.split(':').nth(1).and_then(|k| k.parse().ok()).unwrap_or(segs.len());
                            segs.insert(k, Ratio::parse(&clean_value(e.text("value"))));
                        }
                    }
                    let mut segments: Vec<Ratio> = segs.into_values().collect();
                    if segments.is_empty() {
                        segments.push(dur);
                    }
                    let times_played = props::get(ev, "kRepeatEndingLineNumTimesPlayed")
                        .and_then(|v| clean_value(v).trim_start_matches("int:").trim().parse::<u32>().ok());
                    endings.push(Ending { event_id: ev.text("eventID").to_owned(), pos, end: pos + dur, segments, times_played });
                    repeats.push(Mark::plain("ending".to_owned(), ev.text("eventID"), pos, Some(pos + dur), detail));
                }
                "TonalityDivisionEventDefinition" => {
                    key_changes.push(pos);
                    if let Some(key) = look.key(ev) {
                        keys.push(KeyChange { pos, event_id: ev.text("eventID").to_owned(), key });
                    }
                }
                "RehearsalMarkEventDefinition" => rehearsal_marks.push(pos),
                "ImmediateTempoChangeEventDefinition" => {
                    let t = vocab::tempo_mark(ev, presets);
                    tempos.push(Tempo {
                        pos,
                        bpm: t.bpm,
                        text: t.text,
                        gradual: false,
                        end: None,
                        final_percent: None,
                        event_id: ev.text("eventID").to_owned(),
                        kind: t.kind,
                        unit: t.unit,
                        crotchet_bpm: t.crotchet_bpm,
                        bpm_max: t.bpm_max,
                        equation: t.equation,
                        percent: t.percent,
                        reset: t.reset,
                        preset: t.preset,
                    })
                }
                t if t.starts_with("GradualTempoChange") => {
                    let g = vocab::gradual_tempo_mark(ev);
                    tempos.push(Tempo {
                        pos,
                        bpm: None,
                        text: g.text,
                        gradual: true,
                        end: Some(pos + Ratio::parse(ev.text("duration"))),
                        final_percent: g.final_percent,
                        event_id: ev.text("eventID").to_owned(),
                        kind: "gradual".to_owned(),
                        unit: Ratio::ONE,
                        crotchet_bpm: g.initial_crotchet_bpm,
                        bpm_max: None,
                        equation: None,
                        percent: None,
                        reset: String::new(),
                        preset: g.preset,
                    })
                }
                "PauseEventDefinition" => pauses.push(FlowPause {
                    pos,
                    event_id: ev.text("eventID").to_owned(),
                    pause: vocab::pause(ev),
                }),
                "MarkerEventDefinition" => markers.push(FlowMarker {
                    pos,
                    event_id: ev.text("eventID").to_owned(),
                    marker: vocab::marker(ev),
                }),
                _ => {}
            }
        }
    }

    // --- parts -------------------------------------------------------------------------
    let names: HashMap<&str, &Player> = players.iter().map(|p| (p.id.as_str(), p)).collect();
    let entities: HashMap<&str, &str> =
        players.iter().flat_map(|p| p.instruments.iter().map(|i| (i.id.as_str(), i.entity.as_str()))).collect();
    let mut parts = Vec::new();
    for fp in items_at(f, "flowPlayers/array") {
        let pid = fp.text("playerID");
        let insts = fp.child("flowPlayerInstruments").map(Node::items).unwrap_or(&[]);
        for (n, fpi) in insts.iter().enumerate() {
            let iid = fpi.text("instrumentID");
            let mut stave_of_id = HashMap::new();
            let mut staves = Vec::new();
            for ssi in fpi.child("staveStreamInfos").map(Node::items).unwrap_or(&[]) {
                let index: usize = ssi.text("nthStaveInInstrument").parse().unwrap_or(0);
                stave_of_id.insert(ssi.text("staveID"), index);
                let mut st = Stave {
                    index,
                    stave_id: ssi.text("staveID").to_owned(),
                    stream_id: ssi.text("staveStreamID").to_owned(),
                    divisi: ssi
                        .find("divisiIndex/index")
                        .and_then(|n| n.value.as_deref()?.parse().ok())
                        .filter(|&i: &i64| i >= 0),
                    dynamics: Vec::new(),
                    marks: Vec::new(),
                };
                for &(pos, ev) in on(&st.stream_id) {
                    if &*ev.tag == "DynamicGroupEventDefinition" {
                        let gid = ev.text("dynamicGroupID");
                        let el = tables.get("DynamicGroup").and_then(|t| t.get(gid)).copied();
                        st.dynamics.push(dynamic_group(ev.text("eventID"), pos, gid, el));
                    } else {
                        st.marks.push(mark(ev, pos, &look));
                    }
                }
                staves.push(st);
            }
            staves.sort_by_key(|s| s.index);
            let mut voices = Vec::new();
            for vsi in fpi.child("voiceStreamInfos").map(Node::items).unwrap_or(&[]) {
                let mut v = Voice {
                    stream_id: vsi.text("voiceStreamID").to_owned(),
                    stave_index: stave_of_id.get(vsi.text("defaultLogicalStaveID")).copied().unwrap_or(0),
                    stave_id: vsi.text("defaultLogicalStaveID").to_owned(),
                    notes: Vec::new(),
                    marks: Vec::new(),
                };
                for &(pos, ev) in on(&v.stream_id) {
                    match &*ev.tag {
                        "NoteEventDefinition" | "GraceNoteEventDefinition" => v.notes.push(note(ev, pos)),
                        _ => v.marks.push(mark(ev, pos, &look)),
                    }
                }
                voices.push(v);
            }
            parts.push(Part {
                player_id: pid.to_owned(),
                player_name: names.get(pid).map(|p| p.name.clone()).unwrap_or_else(|| format!("player {pid}")),
                player_label: names.get(pid).map(|p| p.label.clone()).unwrap_or_else(|| format!("player {pid}")),
                instrument_id: iid.to_owned(),
                entity: entities.get(iid).copied().unwrap_or("").to_owned(),
                number: n + 1,
                of: insts.len(),
                staves,
                voices,
            });
        }
    }

    // --- length and bars -----------------------------------------------------------------
    let mut length =
        Ratio::parse(f.find("minimumNotatedLength/length").and_then(|n| n.value.as_deref()).unwrap_or("0"));
    for list in events.values() {
        for &(pos, ev) in list {
            length = length.max(pos + Ratio::parse(ev.text("duration")));
        }
    }
    for bi in items_at(f, "blockInstances/array") {
        length = length.max(Ratio::parse(bi.text("position")));
    }
    // bar-number changes can sit in any stream
    let mut bar_number_changes = Vec::new();
    for list in events.values() {
        for &(pos, ev) in list {
            if &*ev.tag == "BarDivisionEventDefinition" {
                let el = tables.get("BarDivision").and_then(|t| t.get(ev.text("barDivisionElementID"))).copied();
                if let (_, Some(c)) = bars::read_division(pos, el) {
                    bar_number_changes.push(c);
                }
            }
        }
    }
    bar_number_changes.sort_by_key(|c| c.pos);
    let bars = compute_bars(&divisions, &bar_number_changes, length);

    let name = f.text("flowName").to_owned();
    Flow {
        id: f.text("flowID").to_owned(),
        name,
        length,
        bars,
        time_signatures,
        barlines,
        key_changes,
        keys,
        tempos,
        rehearsal_marks,
        bar_number_changes,
        repeats,
        endings,
        pauses,
        video: vocab::video(f),
        markers,
        parts,
    }
}

/// Read a `.dorico` file's score into the model.
pub fn read_project(project: &dorico_format::Project) -> anyhow::Result<Score> {
    Ok(read_score(&project.score()?.root))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn real_test_file_reads() {
        let Ok(c) = dorico_paths::corpus::Corpus::load() else { return };
        let files = c.dorico_files("test_files");
        let Some(f) = files.first() else { return };
        let s = read_project(&dorico_format::Project::read(f).unwrap()).unwrap();
        let flow = &s.flows[0];
        assert!(!flow.bars.is_empty() && !flow.parts.is_empty());
        let notes: usize = flow.parts.iter().flat_map(|p| &p.voices).map(|v| v.notes.len()).sum();
        assert!(notes > 100, "{notes} notes");
        assert!(serde_json::to_string(&s).unwrap().len() > 1000);
    }
}
