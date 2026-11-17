//! Virtual Sound Stage 2 (Parallax-Audio; VST2 id "Para") state and preset decoder.
//!
//! VSS2 saves a list of tagged properties (JUCE `var` encoding). Two containers:
//! - plug-in state (the VST2 chunk Dorico saves): `"g Y8"`, u32 count, properties;
//! - `.vss2preset` file: zlib-compressed XML
//!   `<Preset PresetData="<JUCE base64>" Instrument=… Library=… Microphone-Position=…/>`, where
//!   PresetData decodes to u32 count + the same properties.
//!
//! A property: 4-byte tag (little-endian, so "oCiP" in the file is "PiCo"), a JUCE compressed
//! int size, then a JUCE var (type byte + data). Size 0 is either an empty value or, when a
//! small u32 count follows, a nested group (the shared room settings "RoSS").
//!
//! Meanings (from the user's projects and presets, 2026-11-01; "?" = not confirmed):
//!
//! | Tag | Meaning |
//! |---|---|
//! | PiNa / PiCo | pin (instrument) name / colour (ARGB hex) |
//! | PiMu / PiSo / PiBy | pin mute / solo / bypass |
//! | PiOG | pin output gain, dB? (Tpt 2: -2) |
//! | SSSe | source settings: flag byte, x, y, height (m, f32), facing vector (dx, dy), u32 0, u32 emitter count, then 7 f32 per emitter: offset across, ?, ?, ?, level? (1.0), ?, radius (0.1–0.25). Ensembles: 2 emitters at ±1.25 m (2.5 m wide); harp ±0.63; solo: 1 |
//! | ERLe / DSLe | early-reflection level / direct-sound level (dB?) |
//! | AirA | air absorption amount? (f64 first; empty for Piano) |
//! | PoSi | pin id (unique per instance) |
//! | PreN | path of the preset the instance was loaded from |
//! | GoLR, DoLR, ReTr, IOBy, IOPr, RSRo | unknown |
//! | RoSS.* | room settings shared by all instances: RoID room id, GOLv global output level?, DrWe dry/wet, Seat, MiSe mic settings (binary), UI state |
//!
//! Coordinates: x < 0 = left as heard (violins I at x≈-4.9, cellos +5.1), y = distance back
//! from the front (flutes ≈4, horns ≈8.5, percussion ≈12), height 1.5 everywhere so far.

use anyhow::{Context, Result, bail};
use serde::Serialize;
use std::io::Read;
use std::path::Path;

#[derive(Debug, Clone, PartialEq, Serialize)]
pub enum Value {
    Int(i32),
    Bool(bool),
    Double(f64),
    Str(String),
    Int64(i64),
    Bin(#[serde(serialize_with = "hex")] Vec<u8>),
    /// Another JUCE var type (e.g. 7 = array), kept as type byte + raw bytes.
    Other(u8, #[serde(serialize_with = "hex")] Vec<u8>),
    Empty,
    Group(Vec<(String, Value)>),
}

fn hex<S: serde::Serializer>(b: &[u8], s: S) -> std::result::Result<S::Ok, S::Error> {
    s.serialize_str(&b.iter().map(|x| format!("{x:02x}")).collect::<String>())
}

fn cint(b: &[u8], p: &mut usize) -> Result<usize> {
    let n = *b.get(*p).context("truncated size")? as usize;
    let bytes = b.get(*p + 1..*p + 1 + n).context("truncated size")?;
    *p += 1 + n;
    Ok(bytes.iter().rev().fold(0usize, |v, &x| v << 8 | x as usize))
}

fn var(d: &[u8]) -> Value {
    let x = &d[1..];
    let f8 = |x: &[u8]| x.get(..8).map(|b| <[u8; 8]>::try_from(b).unwrap());
    match d[0] {
        1 => x.get(..4).map(|b| Value::Int(i32::from_le_bytes(b.try_into().unwrap()))).unwrap_or(Value::Bin(x.to_vec())),
        2 => Value::Bool(true),
        3 => Value::Bool(false),
        4 => f8(x).map(|b| Value::Double(f64::from_le_bytes(b))).unwrap_or(Value::Bin(x.to_vec())),
        5 => Value::Str(String::from_utf8_lossy(x).trim_end_matches('\0').to_string()),
        6 => f8(x).map(|b| Value::Int64(i64::from_le_bytes(b))).unwrap_or(Value::Bin(x.to_vec())),
        8 => Value::Bin(x.to_vec()),
        t => Value::Other(t, x.to_vec()),
    }
}

/// Reads the `n` top-level properties, losslessly: `"_count"` keeps `n`; a property the walk
/// can't follow stops it (`"_error"` says where) and everything from there on is kept raw in
/// `"_tail"`, as are bytes after the last property (the room group "RoSS" comes in several
/// layouts: in some states extra words precede its count; older presets differ again).
/// [`encode_state`] writes all of it back byte for byte.
fn props(b: &[u8], p: &mut usize, n: usize) -> Result<Vec<(String, Value)>> {
    let mut out = vec![("_count".to_string(), Value::Int(n as i32))];
    for _ in 0..n {
        let start = *p;
        let mut one = Vec::new();
        if let Err(e) = props_into(b, p, 1, &mut one) {
            out.push(("_error".into(), Value::Str(format!("{e} at byte {start}"))));
            *p = start;
            break;
        }
        out.extend(one);
    }
    if *p < b.len() {
        out.push(("_tail".into(), Value::Bin(b[*p..].to_vec())));
    }
    Ok(out)
}

fn props_into(b: &[u8], p: &mut usize, n: usize, out: &mut Vec<(String, Value)>) -> Result<()> {
    for _ in 0..n {
        let tag: String = b.get(*p..*p + 4).context("truncated tag")?.iter().rev().map(|&c| c as char).collect();
        *p += 4;
        let sz = cint(b, p)?;
        if sz == 0 {
            let count = b.get(*p..*p + 4).map(|x| u32::from_le_bytes(x.try_into().unwrap()));
            match count {
                Some(m) if m < 1000 => {
                    *p += 4;
                    let mut g = Vec::new();
                    let r = props_into(b, p, m as usize, &mut g);
                    out.push((tag, Value::Group(g)));
                    r?;
                }
                _ => out.push((tag, Value::Empty)),
            }
            continue;
        }
        let d = b.get(*p..*p + sz).context("truncated value")?;
        *p += sz;
        out.push((tag, var(d)));
    }
    Ok(())
}

/// Properties of a VSS2 plug-in state chunk.
pub fn parse_state(chunk: &[u8]) -> Result<Vec<(String, Value)>> {
    if chunk.len() < 8 {
        bail!("VSS2 state too short");
    }
    let n = u32::from_le_bytes(chunk[4..8].try_into().unwrap()) as usize;
    props(chunk, &mut 8, n)
}

/// Properties of a preset's decoded PresetData.
pub fn parse_preset_data(raw: &[u8]) -> Result<Vec<(String, Value)>> {
    let n = u32::from_le_bytes(raw.get(..4).context("empty preset")?.try_into().unwrap()) as usize;
    props(raw, &mut 4, n)
}

fn cint_bytes(v: usize) -> Vec<u8> {
    let bytes: Vec<u8> = v.to_le_bytes().into_iter().collect();
    let n = bytes.iter().rposition(|&b| b != 0).map_or(0, |i| i + 1);
    let mut out = vec![n as u8];
    out.extend(&bytes[..n]);
    out
}

fn encode_props(props: &[(String, Value)], out: &mut Vec<u8>) {
    for (tag, v) in props.iter().filter(|(t, _)| !t.starts_with('_')) {
        out.extend(tag.chars().rev().map(|c| c as u8));
        let data: Vec<u8> = match v {
            Value::Int(x) => [&[1u8][..], &x.to_le_bytes()].concat(),
            Value::Bool(true) => vec![2],
            Value::Bool(false) => vec![3],
            Value::Double(x) => [&[4u8][..], &x.to_le_bytes()].concat(),
            Value::Str(x) => [&[5u8][..], x.as_bytes(), &[0]].concat(),
            Value::Int64(x) => [&[6u8][..], &x.to_le_bytes()].concat(),
            Value::Bin(x) => [&[8u8][..], x].concat(),
            Value::Other(t, x) => [&[*t][..], x].concat(),
            Value::Empty => vec![],
            Value::Group(g) => {
                out.push(0);
                out.extend((g.iter().filter(|(t, _)| !t.starts_with('_')).count() as u32).to_le_bytes());
                encode_props(g, out);
                continue;
            }
        };
        out.extend(cint_bytes(data.len()));
        out.extend(data);
    }
}

/// Encode properties as a VSS2 plug-in state chunk (inverse of [`parse_state`]).
pub fn encode_state(props: &[(String, Value)]) -> Vec<u8> {
    let mut out = b"g Y8".to_vec();
    let n = match find(props, "_count") {
        Some(Value::Int(n)) => *n as u32,
        _ => props.iter().filter(|(t, _)| !t.starts_with('_')).count() as u32,
    };
    out.extend(n.to_le_bytes());
    encode_props(props, &mut out);
    if let Some(Value::Bin(t)) = find(props, "_tail") {
        out.extend(t);
    }
    out
}

fn bump_count(p: &mut [(String, Value)]) {
    if let Some((_, Value::Int(n))) = p.iter_mut().find(|(t, _)| t == "_count") {
        *n += 1;
    }
}

/// The room block of a state (from the "RoSS" tag to the end), raw.
pub fn room_bytes(state: &[u8]) -> Option<&[u8]> {
    let i = state.windows(4).position(|w| w == b"SSoR")?;
    Some(&state[i..])
}

/// One capsule of VSS2's main microphone array.
#[derive(Debug, Clone, PartialEq, Serialize, serde::Deserialize)]
pub struct Capsule {
    /// Metres, relative to the array (x across, y forward toward the stage, z up).
    pub position: [f32; 3],
    pub direction: [f32; 3],
    /// 0 = omni, 0.5 = cardioid (seen so far).
    pub pattern: f32,
    /// Output it feeds: 1 = left, 2 = right, 3 = both (the centre mic of a Decca tree).
    pub output: u32,
}

/// VSS2's main microphone setup (room property "MiSe", magic "rAiM"). Seen 2026-11-01: kind 1 =
/// Decca tree (3 omni: ±1 m, centre 1.2 m forward, outer ones turned ±45°), kind 5 = cardioid
/// pair 25 cm apart at ±45°, kind 12 = coincident cardioids at ±60°. Array position: x, y
/// (negative = in front of the stage edge), z = height (inferred: the user's projects have
/// heights 2.5 and 10 m).
#[derive(Debug, Clone, PartialEq, Serialize, serde::Deserialize)]
pub struct Mic {
    pub kind: u32,
    pub position: [f32; 3],
    pub direction: [f32; 3],
    pub capsules: Vec<Capsule>,
}

impl Mic {
    pub fn parse(b: &[u8]) -> Option<Mic> {
        if b.get(..4)? != b"rAiM" {
            return None;
        }
        let u = |o: usize| b.get(o..o + 4).map(|x| u32::from_le_bytes(x.try_into().unwrap()));
        let f = |o: usize| b.get(o..o + 4).map(|x| f32::from_le_bytes(x.try_into().unwrap()));
        let v3 = |o: usize| Some([f(o)?, f(o + 4)?, f(o + 8)?]);
        let n = u(32)? as usize;
        if n > 8 {
            return None;
        }
        let capsules = (0..n)
            .map(|i| {
                let o = 36 + 32 * i;
                Some(Capsule { position: v3(o)?, direction: v3(o + 12)?, pattern: f(o + 24)?, output: u(o + 28)? })
            })
            .collect::<Option<Vec<_>>>()?;
        Some(Mic { kind: u(4)?, position: v3(8)?, direction: v3(20)?, capsules })
    }

    /// "Decca tree (3 omni, 2.0 m wide), 3.5 m in front, 10 m high".
    pub fn describe(&self) -> String {
        let n = self.capsules.len();
        let omni = self.capsules.iter().all(|c| c.pattern == 0.0);
        let card = self.capsules.iter().all(|c| (c.pattern - 0.5).abs() < 1e-3);
        let xs: Vec<f32> = self.capsules.iter().map(|c| c.position[0]).collect();
        let width = xs.iter().cloned().fold(f32::MIN, f32::max) - xs.iter().cloned().fold(f32::MAX, f32::min);
        let angle = self.capsules.iter().map(|c| c.direction[0].atan2(c.direction[1]).to_degrees().abs()).fold(0.0f32, f32::max);
        let what = match (n, omni, card) {
            (3, true, _) => format!("Decca tree (3 omni, {width:.1} m wide)"),
            (2, _, true) if width < 0.01 => format!("coincident cardioids ±{angle:.0}°"),
            (2, _, true) => format!("cardioid pair {:.0} cm apart, ±{angle:.0}°", width * 100.0),
            _ => format!("{n} capsules, {width:.2} m wide"),
        };
        let y = self.position[1];
        let place = if y < 0.0 { format!("{:.1} m in front", -y) } else { format!("{y:.1} m into the stage") };
        format!("{what}, {place}, {:.1} m high", self.position[2])
    }
}

/// VSS2's room (shared by every instance of a project): room id, level, mic setup.
#[derive(Debug, Clone, PartialEq, Serialize, serde::Deserialize)]
pub struct Room {
    pub id: i32,
    /// The id as four ASCII letters when it is one ("ScSA", "ScSB", "Stdi").
    pub name: String,
    pub level: Option<f64>,
    pub seat: Option<i32>,
    pub dry_wet: Option<f64>,
    pub mic: Option<Mic>,
    /// The whole "MiSe" value (it carries more than the decoded array).
    #[serde(serialize_with = "hex", deserialize_with = "unhex")]
    pub mic_raw: Vec<u8>,
}

fn unhex<'de, D: serde::Deserializer<'de>>(d: D) -> std::result::Result<Vec<u8>, D::Error> {
    let s: String = serde::Deserialize::deserialize(d)?;
    (0..s.len() / 2).map(|i| u8::from_str_radix(&s[2 * i..2 * i + 2], 16).map_err(serde::de::Error::custom)).collect()
}

/// Where each room lets the main microphones go (y: furthest in front of the stage edge, z:
/// highest), measured 2026-11-02 from the captures: VSS2 moves the array inside these limits
/// whatever the project stores (Harry Potter Cues Plus 3–5 store y −3.5, z 10; the arrivals
/// fit y −3.0, z 8.0 within 0.02 ms). Rooms not listed: no limit seen.
pub const MIC_LIMITS: [(&str, f32, f32); 2] = [("ScSA", -3.0, 8.0), ("ScSB", -3.5, f32::MAX)];

impl Room {
    /// The main microphones where VSS2 actually puts them ([`MIC_LIMITS`]).
    pub fn effective_mic(&self) -> Option<Mic> {
        let mut m = self.mic.clone()?;
        if let Some((_, y, z)) = MIC_LIMITS.iter().find(|(n, _, _)| *n == self.name) {
            m.position[1] = m.position[1].max(*y);
            m.position[2] = m.position[2].min(*z);
        }
        Some(m)
    }

    pub fn describe(&self) -> String {
        let mut mic = self.mic.as_ref().map_or("default microphones".to_string(), Mic::describe);
        if let (Some(a), Some(b)) = (&self.mic, self.effective_mic())
            && a != &b
        {
            mic = format!("{} (stored: {:.1} m in front, {:.1} m high)", b.describe(), -a.position[1], a.position[2]);
        }
        format!("{} ({mic}; level {:+.1} dB)", if self.name.is_empty() { format!("room {}", self.id) } else { self.name.clone() }, self.level.unwrap_or(0.0))
    }

    /// Identifies the room's sound-relevant settings (ignores UI state).
    pub fn key(&self) -> String {
        let h: String = self.mic_raw.iter().map(|x| format!("{x:02x}")).collect();
        format!("{}|{:?}|{:?}|{:?}|{h}", self.id, self.level, self.seat, self.dry_wet)
    }
}

/// A property found by its tag anywhere in `b` (the room comes in several layouts, so it is
/// searched rather than walked).
fn scan(b: &[u8], tag: &str) -> Option<Value> {
    let t: Vec<u8> = tag.bytes().rev().collect();
    let i = b.windows(4).position(|w| w == t.as_slice())?;
    let mut p = i + 4;
    let sz = cint(b, &mut p).ok()?;
    if sz == 0 {
        return Some(Value::Empty);
    }
    Some(var(b.get(p..p + sz)?))
}

/// The room settings of a plug-in state.
pub fn room(state: &[u8]) -> Option<Room> {
    let b = room_bytes(state)?;
    let id = match scan(b, "RoID")? {
        Value::Int(i) => i,
        _ => return None,
    };
    let name = String::from_utf8(id.to_be_bytes().to_vec()).ok().filter(|s| s.bytes().all(|c| c.is_ascii_alphanumeric())).unwrap_or_default();
    let d = |t| match scan(b, t) {
        Some(Value::Double(x)) => Some(x),
        _ => None,
    };
    let mic_raw = match scan(b, "MiSe") {
        Some(Value::Bin(x)) => x,
        _ => vec![],
    };
    Some(Room {
        id,
        name,
        level: d("GOLv"),
        seat: match scan(b, "Seat") {
            Some(Value::Int(x)) => Some(x),
            _ => None,
        },
        dry_wet: d("DrWe"),
        mic: Mic::parse(&mic_raw),
        mic_raw,
    })
}

/// Properties that don't change the sound (checked 2026-11-01 on Oboe 1: changing name, colour,
/// pin id or preset path leaves the direct sound identical, −76 … −86 dB, and the reflections
/// within VSS2's own load-to-load spread).
pub const NOT_SOUND: [&str; 4] = ["PiNa", "PiCo", "PoSi", "PreN"];

/// A short id for what a state sounds like: its source properties (without [`NOT_SOUND`]) plus
/// its room's settings ([`Room::key`]). Equal ids = the same sound (up to VSS2's random
/// reflections).
pub fn sound_key(state: &[u8]) -> Result<String> {
    let p = parse_state(state)?;
    let has_room = p.iter().any(|(t, _)| t == "RoSS");
    let mut keep: Vec<(String, Value)> = vec![];
    for (t, v) in p {
        if NOT_SOUND.contains(&t.as_str()) || t == "_count" || t == "RoSS" || t == "_error" {
            continue;
        }
        if t == "_tail" {
            if has_room {
                continue;
            }
            // the walk stopped before the room: keep the source part of the raw rest
            if let Value::Bin(b) = &v {
                let end = b.windows(4).position(|w| w == b"SSoR").unwrap_or(b.len());
                keep.push((t, Value::Bin(b[..end].to_vec())));
            }
            continue;
        }
        keep.push((t, v));
    }
    let mut s = serde_json::to_string(&keep)?;
    s.push_str(&room(state).map_or(String::new(), |r| r.key()));
    // FNV-1a, 64 bit
    let h = s.bytes().fold(0xcbf29ce484222325u64, |h, b| (h ^ b as u64).wrapping_mul(0x100000001b3));
    Ok(format!("{:010x}", h >> 24))
}

/// A preset's properties made into a full plug-in state. Presets lack the pin id ("PoSi"),
/// the preset path ("PreN") and, above all, the **room** ("RoSS": room id, microphone setup
/// "MiSe", output level), which VSS2 shares between all instances of a project. Without the
/// room VSS2 does not place the source (no left/right crossfeed, other level; seen
/// 2026-11-01). `room` = [`room_bytes`] of a state from the project whose room to use.
pub fn state_from_preset(path: &Path, windows_path: &str, pin_id: i32, room: &[u8]) -> Result<Vec<u8>> {
    let mut p = parse_preset_data(&preset_raw(path)?)?;
    p.retain(|(t, _)| t != "RoSS" && t != "_tail" && t != "_error");
    let end = |p: &[(String, Value)]| p.iter().position(|(t, _)| t == "_error" || t == "_tail").unwrap_or(p.len());
    if !p.iter().any(|(t, _)| t == "PoSi") {
        let at = p.iter().position(|(t, _)| t == "DoLR").unwrap_or(end(&p));
        p.insert(at, ("PoSi".into(), Value::Int(pin_id)));
        bump_count(&mut p);
    }
    if !p.iter().any(|(t, _)| t == "PreN") {
        let at = end(&p);
        p.insert(at, ("PreN".into(), Value::Str(windows_path.to_string())));
        bump_count(&mut p);
    }
    // the room block goes last, verbatim; it counts as one property
    let n = p.iter().filter(|(t, _)| !t.starts_with('_')).count() as i32 + 1;
    p.retain(|(t, _)| t != "_count");
    p.insert(0, ("_count".into(), Value::Int(n)));
    p.push(("_tail".into(), Value::Bin(room.to_vec())));
    Ok(encode_state(&p))
}

/// JUCE `MemoryBlock::fromBase64Encoding`: "<size>." + 6-bit chars, least significant bit first.
pub fn juce_base64(s: &str) -> Result<Vec<u8>> {
    const ABC: &[u8] = b".ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+";
    let (size, data) = s.split_once('.').context("no size prefix")?;
    let size: usize = size.parse()?;
    let mut out = vec![0u8; size];
    let mut bit = 0usize;
    for c in data.bytes() {
        let v = ABC.iter().position(|&a| a == c).context("bad base64 char")?;
        for i in 0..6 {
            if bit / 8 < size && (v >> i) & 1 == 1 {
                out[bit / 8] |= 1 << (bit % 8);
            }
            bit += 1;
        }
    }
    Ok(out)
}

/// The readable summary of one VSS2 instance or preset.
#[derive(Debug, Clone, Default, Serialize)]
pub struct Vss2 {
    pub name: String,
    pub colour: String,
    pub preset: String,
    pub x: f32,
    pub y: f32,
    pub z: f32,
    /// Emitter points (1 = point source; 2 = a section spread between them).
    pub emitters: u32,
    /// Distance between the outermost emitters, metres (0 for a point source).
    pub width: f32,
    /// Degrees; 0 = facing the front (the listener), positive = turned toward +x (right).
    pub facing: f32,
    pub er_level: Option<f64>,
    pub direct_level: Option<f64>,
    pub gain: Option<f64>,
    pub air: Option<f64>,
    pub mute: bool,
    pub solo: bool,
    pub bypass: bool,
    pub pin_id: Option<i32>,
    pub room_id: Option<i32>,
    pub room_level: Option<f64>,
    pub room_dry_wet: Option<f64>,
    pub room_seat: Option<i32>,
    /// Set when part of the state could not be decoded (see `props`).
    pub undecoded: Option<String>,
    /// Every property, for fields not decoded yet.
    pub raw: Vec<(String, Value)>,
}

fn find<'a>(p: &'a [(String, Value)], path: &str) -> Option<&'a Value> {
    let (head, rest) = path.split_once('.').map_or((path, None), |(a, b)| (a, Some(b)));
    let v = p.iter().find(|(k, _)| k == head).map(|(_, v)| v)?;
    match (rest, v) {
        (None, v) => Some(v),
        (Some(r), Value::Group(g)) => find(g, r),
        _ => None,
    }
}

impl Vss2 {
    pub fn from_props(p: Vec<(String, Value)>) -> Vss2 {
        let s = |k| match find(&p, k) {
            Some(Value::Str(s)) => s.clone(),
            _ => String::new(),
        };
        let d = |k| match find(&p, k) {
            Some(Value::Double(x)) => Some(*x),
            Some(Value::Int(x)) => Some(*x as f64),
            _ => None,
        };
        let i = |k| match find(&p, k) {
            Some(Value::Int(x)) => Some(*x),
            _ => None,
        };
        let b = |k| matches!(find(&p, k), Some(Value::Bool(true)));
        let mut v = Vss2 {
            name: s("PiNa"),
            colour: s("PiCo"),
            preset: s("PreN"),
            er_level: d("ERLe"),
            direct_level: d("DSLe"),
            gain: d("PiOG"),
            air: match find(&p, "AirA") {
                Some(Value::Bin(x)) if x.len() >= 8 => Some(f64::from_le_bytes(x[..8].try_into().unwrap())),
                _ => None,
            },
            mute: b("PiMu"),
            solo: b("PiSo"),
            bypass: b("PiBy"),
            pin_id: i("PoSi"),
            room_id: i("RoSS.RoID"),
            room_level: d("RoSS.GOLv"),
            room_dry_wet: d("RoSS.DrWe"),
            room_seat: i("RoSS.Seat"),
            undecoded: match find(&p, "_error") {
                Some(Value::Str(e)) => Some(e.clone()),
                _ => None,
            },
            ..Default::default()
        };
        if let Some(Value::Bin(x)) = find(&p, "SSSe") {
            let f = |o: usize| x.get(o..o + 4).map(|b| f32::from_le_bytes(b.try_into().unwrap())).unwrap_or(f32::NAN);
            // 4-byte id, 1 flag byte, then x, y, height, facing dx, dy
            (v.x, v.y, v.z) = (f(5), f(9), f(13));
            v.facing = f(17).atan2(-f(21)).to_degrees();
            let n = x.get(29..33).map_or(0, |b| u32::from_le_bytes(b.try_into().unwrap()));
            if n <= 16 && x.len() >= 33 + 28 * n as usize {
                v.emitters = n;
                let offs: Vec<f32> = (0..n as usize).map(|i| f(33 + 28 * i)).collect();
                v.width = offs.iter().cloned().fold(f32::MIN, f32::max) - offs.iter().cloned().fold(f32::MAX, f32::min);
            }
        }
        v.raw = p;
        v
    }

    /// The preset file name without folder and extension ("Flute 1").
    pub fn preset_name(&self) -> &str {
        let f = self.preset.rsplit(['\\', '/']).next().unwrap_or("");
        f.strip_suffix(".vss2preset").unwrap_or(f)
    }
}

/// A `.vss2preset` file.
#[derive(Debug, Clone, Serialize)]
pub struct Preset {
    pub instrument: String,
    pub library: String,
    pub mic_position: String,
    pub vss: Vss2,
}

fn preset_xml(path: &Path) -> Result<String> {
    let mut xml = String::new();
    flate2::read::ZlibDecoder::new(std::fs::File::open(path)?).read_to_string(&mut xml).with_context(|| format!("{}", path.display()))?;
    Ok(xml)
}

fn xml_attr(xml: &str, k: &str) -> String {
    let key = format!("{k}=\"");
    xml.find(&key).map(|i| xml[i + key.len()..].split('"').next().unwrap_or("").to_string()).unwrap_or_default()
}

/// A preset's decoded PresetData (u32 count + properties). Behind VSS2's 4-byte magic it is
/// a state VSS2 loads.
pub fn preset_raw(path: &Path) -> Result<Vec<u8>> {
    juce_base64(&xml_attr(&preset_xml(path)?, "PresetData"))
}

pub fn read_preset(path: &Path) -> Result<Preset> {
    let xml = preset_xml(path)?;
    let attr = |k: &str| xml_attr(&xml, k);
    let raw = juce_base64(&attr("PresetData"))?;
    Ok(Preset {
        instrument: attr("Instrument"),
        library: attr("Library"),
        mic_position: attr("Microphone-Position"),
        vss: Vss2::from_props(parse_preset_data(&raw)?),
    })
}

#[cfg(test)]
pub(crate) mod tests {
    use super::*;

    fn prop(tag: &str, val: &[u8]) -> Vec<u8> {
        let mut b: Vec<u8> = tag.bytes().rev().collect();
        b.extend([1, val.len() as u8]);
        b.extend(val);
        b
    }

    #[test]
    fn decodes_state() {
        let mut sse = vec![0x96, 0xf2, 0xa4, 0x1b, 0];
        for f in [-0.87f32, 6.73, 1.5, 0.0, -1.0] {
            sse.extend(f.to_le_bytes());
        }
        let mut c = b"g Y8".to_vec();
        c.extend(4u32.to_le_bytes());
        c.extend(prop("PiNa", b"\x05Cl 2\0"));
        c.extend(prop("SSSe", &[&[8u8][..], &sse].concat()));
        c.extend(prop("ERLe", &[&[4u8][..], &2.0f64.to_le_bytes()].concat()));
        // nested room group with one int
        c.extend(b"SSoR\x00");
        c.extend(1u32.to_le_bytes());
        c.extend(prop("RoID", &[1, 7, 0, 0, 0]));
        let v = Vss2::from_props(parse_state(&c).unwrap());
        assert_eq!(v.name, "Cl 2");
        assert!((v.x + 0.87).abs() < 1e-6 && (v.y - 6.73).abs() < 1e-6 && v.z == 1.5);
        assert!(v.facing.abs() < 1e-6);
        assert_eq!((v.er_level, v.room_id), (Some(2.0), Some(7)));
    }

    #[test]
    fn encode_round_trip() {
        let mut c = b"g Y8".to_vec();
        c.extend(3u32.to_le_bytes());
        c.extend(prop("PiNa", b"\x05Cl 2\0"));
        c.extend(prop("ERLe", &[&[4u8][..], &2.0f64.to_le_bytes()].concat()));
        c.extend(b"SSoR\x00");
        c.extend(1u32.to_le_bytes());
        c.extend(prop("RoID", &[1, 7, 0, 0, 0]));
        assert_eq!(encode_state(&parse_state(&c).unwrap()), c);
    }

    /// A Decca tree "MiSe" value as VSS2 writes it (kind 1, array at y −3.5 m, 10 m high).
    pub(crate) fn decca_mic() -> Vec<u8> {
        let mut m = b"rAiM".to_vec();
        m.extend(1u32.to_le_bytes());
        for f in [0.0f32, -3.5, 10.0, 0.0, 1.0, 0.0] {
            m.extend(f.to_le_bytes());
        }
        m.extend(3u32.to_le_bytes());
        let h = std::f32::consts::FRAC_1_SQRT_2;
        for (pos, dir, out) in [([-1.0f32, 0.0, 0.0], [-h, h, 0.0], 1u32), ([0.0, 1.2, 0.0], [0.0, 1.0, 0.0], 3), ([1.0, 0.0, 0.0], [h, h, 0.0], 2)] {
            for f in pos.iter().chain(&dir).chain(&[0.0f32]) {
                m.extend(f.to_le_bytes());
            }
            m.extend(out.to_le_bytes());
        }
        m
    }

    fn state_with(name: &str, er: f64, mic: &[u8]) -> Vec<u8> {
        let mut c = b"g Y8".to_vec();
        c.extend(4u32.to_le_bytes());
        c.extend(prop("PiNa", &[&[5u8][..], name.as_bytes(), b"\0"].concat()));
        c.extend(prop("ERLe", &[&[4u8][..], &er.to_le_bytes()].concat()));
        c.extend(prop("PoSi", &[1, 7, 0, 0, 0]));
        c.extend(b"SSoR\x00");
        c.extend(2u32.to_le_bytes());
        c.extend(prop("RoID", &[&[1u8][..], &1399018305i32.to_le_bytes()].concat()));
        let mut v = vec![8u8];
        v.extend(mic);
        let mut t: Vec<u8> = b"MiSe".iter().rev().copied().collect();
        t.extend([1, v.len() as u8]);
        t.extend(v);
        c.extend(t);
        c
    }

    #[test]
    fn room_and_mic() {
        let r = room(&state_with("Ob 1", 2.0, &decca_mic())).unwrap();
        assert_eq!((r.id, r.name.as_str()), (1399018305, "ScSA"));
        let m = r.mic.clone().unwrap();
        assert_eq!(m.capsules.len(), 3);
        assert_eq!(m.capsules[1].output, 3);
        assert_eq!(m.describe(), "Decca tree (3 omni, 2.0 m wide), 3.5 m in front, 10.0 m high");
        // ScSA keeps the tree within 3.0 m of the stage and 8 m high
        let e = r.effective_mic().unwrap();
        assert_eq!((e.position[1], e.position[2]), (-3.0, 8.0));
    }

    #[test]
    fn sound_key_ignores_names_not_settings() {
        let a = sound_key(&state_with("Ob 1", 2.0, &decca_mic())).unwrap();
        assert_eq!(a, sound_key(&state_with("Oboe", 2.0, &decca_mic())).unwrap());
        assert_ne!(a, sound_key(&state_with("Ob 1", 3.0, &decca_mic())).unwrap());
        let mut other_mic = decca_mic();
        other_mic[16..20].copy_from_slice(&2.5f32.to_le_bytes()); // array height
        assert_ne!(a, sound_key(&state_with("Ob 1", 2.0, &other_mic)).unwrap());
    }

    #[test]
    fn juce_base64_round() {
        // JUCE encodes bytes [1, 2, 3] as "3.AIgA" (6-bit groups, LSB first)
        let enc = {
            let abc = b".ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+";
            let bits: Vec<u8> = [1u8, 2, 3].iter().flat_map(|b| (0..8).map(move |i| b >> i & 1)).collect();
            let s: String = bits.chunks(6).map(|c| abc[c.iter().enumerate().map(|(i, b)| (*b as usize) << i).sum::<usize>()] as char).collect();
            format!("3.{s}")
        };
        assert_eq!(juce_base64(&enc).unwrap(), vec![1, 2, 3]);
    }
}
