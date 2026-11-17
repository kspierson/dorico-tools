//! Playback state: `supplementary_data/vstaudioengine/enginedata`.
//!
//! Layout: length-prefixed chunks (u32 LE length + bytes):
//! `"MixerData"`, a version string (`"1.0 beta 3"`), `"MixerDocument"`, then a
//! chunk holding 4 zero bytes + the mixer XML (`<mixer>`: channels, VST
//! instrument slots, inserts, routing). After that come other sections (audio
//! device mapping XML, then the opaque per-plugin state blobs, e.g. Kontakt),
//! which we don't parse.
//!
//! From the mixer XML we read the *setup*: which instruments and effects are
//! loaded. That lets us tell "playback setup changed" (plugins added / removed
//! / swapped) apart from "plugin internals re-saved" (which happens on every save).

use quick_xml::events::Event;
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PluginCount {
    pub name: String,
    pub uid: String,
    pub count: u32,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, Default)]
pub struct PlaybackSetup {
    pub instruments: Vec<PluginCount>,
    pub effects: Vec<PluginCount>,
}

impl PlaybackSetup {
    /// Canonical text form; equal setups give equal strings.
    pub fn canonical(&self) -> String {
        let mut s = String::new();
        for (kind, list) in [("instrument", &self.instruments), ("effect", &self.effects)] {
            for p in list {
                s.push_str(&format!("{kind}\t{}\t{}\t{}\n", p.uid, p.name, p.count));
            }
        }
        s
    }

    /// Human-readable differences, e.g. ["+1 Kontakt", "-12 Virtual Sound Stage 2"].
    pub fn changes_from(&self, old: &PlaybackSetup) -> Vec<String> {
        let mut out = Vec::new();
        for (label, a, b) in [("", &old.instruments, &self.instruments), (" (effect)", &old.effects, &self.effects)] {
            let count = |l: &[PluginCount]| -> BTreeMap<String, i64> {
                let mut m = BTreeMap::new();
                for p in l {
                    *m.entry(p.name.clone()).or_insert(0) += i64::from(p.count);
                }
                m
            };
            let (ca, cb) = (count(a), count(b));
            let names: std::collections::BTreeSet<&String> = ca.keys().chain(cb.keys()).collect();
            for n in names {
                let d = cb.get(n).copied().unwrap_or(0) - ca.get(n).copied().unwrap_or(0);
                if d != 0 {
                    out.push(format!("{}{} {n}{label}", if d > 0 { "+" } else { "" }, d));
                }
            }
        }
        out
    }

    pub fn total_instruments(&self) -> u32 {
        self.instruments.iter().map(|p| p.count).sum()
    }
}

/// The mixer XML inside enginedata, if the layout is as expected.
pub fn mixer_xml(enginedata: &[u8]) -> Option<&[u8]> {
    let mut p = 0usize;
    for _ in 0..4 {
        let len = u32::from_le_bytes(enginedata.get(p..p + 4)?.try_into().ok()?) as usize;
        let body = enginedata.get(p + 4..p + 4 + len)?;
        if let Some(start) = body.windows(5).take(64).position(|w| w == b"<?xml") {
            return Some(&body[start..]);
        }
        p += 4 + len;
    }
    None
}

/// Read which plugins are loaded. None if enginedata has an unexpected layout.
pub fn read_setup(enginedata: &[u8]) -> Option<PlaybackSetup> {
    let xml = mixer_xml(enginedata)?;
    let mut reader = quick_xml::Reader::from_reader(xml);
    let mut buf = Vec::new();
    let mut inst: BTreeMap<(String, String), u32> = BTreeMap::new();
    let mut fx: BTreeMap<(String, String), u32> = BTreeMap::new();
    loop {
        match reader.read_event_into(&mut buf) {
            Ok(Event::Start(e)) | Ok(Event::Empty(e)) => {
                let tag = e.name();
                let target = match tag.as_ref() {
                    b"instrument" => &mut inst,
                    b"insert" => &mut fx,
                    _ => {
                        buf.clear();
                        continue;
                    }
                };
                let (mut name, mut uid) = (String::new(), String::new());
                for a in e.attributes().flatten() {
                    let v = String::from_utf8_lossy(&a.value).to_string();
                    match a.key.as_ref() {
                        b"name" => name = v,
                        b"uid" => uid = v,
                        _ => {}
                    }
                }
                if !uid.is_empty() {
                    if name.is_empty() {
                        name = name_from_uid(&uid);
                    }
                    *target.entry((uid, name)).or_insert(0) += 1;
                }
            }
            Ok(Event::Eof) | Err(_) => break,
            _ => {}
        }
        buf.clear();
    }
    let list = |m: BTreeMap<(String, String), u32>| -> Vec<PluginCount> {
        m.into_iter().map(|((uid, name), count)| PluginCount { name, uid, count }).collect()
    };
    Some(PlaybackSetup { instruments: list(inst), effects: list(fx) })
}

/// VST2 plugins hosted via VST3 have class IDs "VST" + 4-char id + name prefix,
/// e.g. hex of "VSTNi$Dkontakt" -> "kontakt".
pub fn name_from_uid(uid: &str) -> String {
    let bytes: Option<Vec<u8>> =
        (0..uid.len() / 2).map(|i| u8::from_str_radix(uid.get(2 * i..2 * i + 2)?, 16).ok()).collect();
    match bytes {
        Some(b) if b.len() == 16 && b.starts_with(b"VST") => {
            String::from_utf8_lossy(&b[7..]).trim_end_matches('\0').trim().to_owned()
        }
        _ => uid.to_owned(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    pub fn sample(instruments: &[(&str, &str)]) -> Vec<u8> {
        let mut xml = String::from("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<mixer id=\"1\"><instruments>");
        for (name, uid) in instruments {
            xml.push_str(&format!(
                "<instrument id=\"2\" name=\"{name}\" uid=\"{uid}\"><insert uid=\"AB\" name=\"EQ\"/></instrument>"
            ));
        }
        xml.push_str("</instruments></mixer>");
        let mut out = Vec::new();
        for chunk in [b"MixerData".to_vec(), b"1.0 beta 3".to_vec(), b"MixerDocument".to_vec()] {
            out.extend((chunk.len() as u32).to_le_bytes());
            out.extend(chunk);
        }
        let mut body = vec![0u8; 4];
        body.extend(xml.as_bytes());
        out.extend((body.len() as u32).to_le_bytes());
        out.extend(body);
        out.extend(b"opaque plugin state");
        out
    }

    #[test]
    fn reads_setup_and_changes() {
        let a = read_setup(&sample(&[("Kontakt", "K1"), ("Kontakt", "K1")])).unwrap();
        let b = read_setup(&sample(&[("Kontakt", "K1"), ("VSS", "V1")])).unwrap();
        assert_eq!(a.instruments[0].count, 2);
        assert_eq!(a.effects[0].count, 2);
        assert_ne!(a.canonical(), b.canonical());
        assert_eq!(b.changes_from(&a), vec!["-1 Kontakt", "+1 VSS"]);
        assert_eq!(name_from_uid("5653544E6924446B6F6E74616B740000"), "kontakt");
    }
}
