//! Dorico's mixer and saved plug-in states, from `supplementary_data/vstaudioengine/enginedata`.
//!
//! [`read_mixer`] reads the mixer XML (see [`crate::playback`] for the chunk layout): the VST
//! rack, then every channel with its inserts (pre and post fader), sends and fader gain.
//! [`plugin_states`] reads the binary "PluginState" records that follow the XML. Each record
//! names its **owner**: the XML `id` of the rack instrument or insert it belongs to, so a state
//! is matched to its insert exactly (two inserts of the same plug-in can't be confused).
//!
//! Layout of a record (little-endian unless noted), checked on the user's projects 2026-11-01:
//! `u32 11, "PluginState", u64 size, u64 owner, u32 n, "VST3", u32 1, 32-char uid, u64 len,
//! data`. For VST2 plug-ins (wrapped by Dorico) `data` holds `"VstW"…` and then a standard VST2
//! fxBank/fxProgram (`"CcnK"`, big-endian), whose opaque chunk is what the plug-in's
//! `getChunk` returned.
//!
//! Found in the user's projects: channels store `gain` only when moved (linear, 1.0 = 0 dB) and
//! no pan at all; a send stores `enabled="0"` when switched off (confirmed by the user in
//! Dorico) and `gain` (linear); an `<insert>` with no `name`/`uid` is an empty slot that still
//! carries an old saved state (Dorico shows nothing there).

use quick_xml::events::Event;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, Default)]
pub struct Mixer {
    /// VST instrument rack, in document order.
    pub rack: Vec<RackSlot>,
    pub channels: Vec<Channel>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct RackSlot {
    pub id: u64,
    pub slot: u32,
    pub name: String,
    pub uid: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Channel {
    pub id: u64,
    /// Element name without "-channel": "instrument-return", "fx-return", "output", "input".
    pub kind: String,
    pub name: String,
    /// Rack instrument feeding an instrument-return channel (its `id`, see [`Mixer::rack_slot`]).
    pub instrument_id: Option<u64>,
    /// Fader gain, linear (1.0 = 0 dB); None when not stored (Dorico's default).
    pub gain: Option<f64>,
    pub inserts: Vec<Insert>,
    pub sends: Vec<Send>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Insert {
    pub id: u64,
    pub slot: u32,
    /// None for an empty slot (may still have a leftover saved state).
    pub name: Option<String>,
    pub uid: Option<String>,
    pub enabled: bool,
    pub post_fader: bool,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Send {
    pub id: u64,
    /// 1-based; assumed to address the n-th FX channel in document order.
    pub slot: u32,
    pub enabled: bool,
    /// Linear (1.0 = 0 dB); None when not stored.
    pub gain: Option<f64>,
}

impl Mixer {
    pub fn rack_slot(&self, instrument_id: u64) -> Option<&RackSlot> {
        self.rack.iter().find(|r| r.id == instrument_id)
    }
    /// FX channels in document order (send slot n -> element n-1).
    pub fn fx_channels(&self) -> impl Iterator<Item = &Channel> {
        self.channels.iter().filter(|c| c.kind == "fx-return")
    }
    /// The channel and insert with this XML id.
    pub fn insert(&self, id: u64) -> Option<(&Channel, &Insert)> {
        self.channels.iter().find_map(|c| c.inserts.iter().find(|i| i.id == id).map(|i| (c, i)))
    }
}

/// Linear gain -> dB.
pub fn db(gain: f64) -> f64 {
    20.0 * gain.log10()
}

fn attrs(e: &quick_xml::events::BytesStart) -> Vec<(String, String)> {
    e.attributes()
        .flatten()
        .map(|a| (String::from_utf8_lossy(a.key.as_ref()).into_owned(), String::from_utf8_lossy(&a.value).into_owned()))
        .collect()
}

fn get<'a>(a: &'a [(String, String)], k: &str) -> Option<&'a str> {
    a.iter().find(|(n, _)| n == k).map(|(_, v)| v.as_str())
}

fn num<T: std::str::FromStr>(a: &[(String, String)], k: &str) -> Option<T> {
    get(a, k).and_then(|v| v.parse().ok())
}

/// Read the mixer from enginedata. None if the layout is unexpected.
pub fn read_mixer(enginedata: &[u8]) -> Option<Mixer> {
    let xml = crate::playback::mixer_xml(enginedata)?;
    let mut r = quick_xml::Reader::from_reader(xml);
    let mut buf = Vec::new();
    let mut m = Mixer::default();
    let mut cur: Option<Channel> = None;
    let mut post = false;
    loop {
        let ev = r.read_event_into(&mut buf);
        match ev {
            Ok(Event::Start(ref e)) | Ok(Event::Empty(ref e)) => {
                let tag = String::from_utf8_lossy(e.name().as_ref()).into_owned();
                let a = attrs(e);
                if let Some(kind) = tag.strip_suffix("-channel") {
                    let ch = Channel {
                        id: num(&a, "id").unwrap_or(0),
                        kind: kind.to_string(),
                        name: get(&a, "name").unwrap_or("").to_string(),
                        instrument_id: num(&a, "instrument-id"),
                        gain: num(&a, "gain"),
                        inserts: vec![],
                        sends: vec![],
                    };
                    if matches!(ev, Ok(Event::Empty(_))) {
                        m.channels.push(ch);
                    } else {
                        cur = Some(ch);
                    }
                } else if tag == "pre-insert-section" {
                    post = false;
                } else if tag == "post-insert-section" {
                    post = true;
                } else if tag == "instrument" && cur.is_none() {
                    if let (Some(id), Some(uid)) = (num(&a, "id"), get(&a, "uid")) {
                        m.rack.push(RackSlot {
                            id,
                            slot: num(&a, "slot").unwrap_or(0),
                            name: get(&a, "name").unwrap_or("").to_string(),
                            uid: uid.to_string(),
                        });
                    }
                } else if let Some(ch) = cur.as_mut() {
                    if tag == "insert" {
                        ch.inserts.push(Insert {
                            id: num(&a, "id").unwrap_or(0),
                            slot: num(&a, "slot").unwrap_or(0),
                            name: get(&a, "name").map(str::to_string),
                            uid: get(&a, "uid").map(str::to_string),
                            enabled: get(&a, "enabled") != Some("0"),
                            post_fader: post,
                        });
                    } else if tag == "send" {
                        ch.sends.push(Send {
                            id: num(&a, "id").unwrap_or(0),
                            slot: num(&a, "slot").unwrap_or(0),
                            enabled: get(&a, "enabled") != Some("0"),
                            gain: num(&a, "gain"),
                        });
                    }
                }
            }
            Ok(Event::End(ref e)) => {
                if e.name().as_ref().ends_with(b"-channel")
                    && let Some(ch) = cur.take()
                {
                    m.channels.push(ch);
                }
            }
            Ok(Event::Eof) | Err(_) => break,
            _ => {}
        }
        buf.clear();
    }
    Some(m)
}

/// A VST2 fxBank ("FBCh") or fxProgram ("FPCh") opaque chunk inside a state.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Vst2Chunk {
    pub kind: String,
    /// The plug-in's 4-character VST2 id, e.g. "Para" (Virtual Sound Stage 2), "AVr5" (Altiverb 7).
    pub fx_id: String,
    #[serde(skip)]
    pub chunk: Vec<u8>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct PluginState {
    /// XML id of the rack instrument or insert this state belongs to.
    pub owner: u64,
    /// Dorico's plug-in uid (as in the mixer XML).
    pub uid: String,
    pub vst2: Option<Vst2Chunk>,
    /// The record's state bytes (after the uid).
    #[serde(skip)]
    pub data: Vec<u8>,
}

fn u32le(b: &[u8], p: usize) -> Option<u32> {
    Some(u32::from_le_bytes(b.get(p..p + 4)?.try_into().ok()?))
}
fn u64le(b: &[u8], p: usize) -> Option<u64> {
    Some(u64::from_le_bytes(b.get(p..p + 8)?.try_into().ok()?))
}
fn u32be(b: &[u8], p: usize) -> Option<u32> {
    Some(u32::from_be_bytes(b.get(p..p + 4)?.try_into().ok()?))
}

/// The VST2 opaque chunk in a state's data, if any.
pub fn vst2_chunk(data: &[u8]) -> Option<Vst2Chunk> {
    let c = data.windows(4).take(256).position(|w| w == b"CcnK")?;
    let kind = data.get(c + 8..c + 12)?;
    let off = match kind {
        b"FBCh" => 156,
        b"FPCh" => 56,
        _ => return None,
    };
    let n = u32be(data, c + off)? as usize;
    Some(Vst2Chunk {
        kind: String::from_utf8_lossy(kind).into_owned(),
        fx_id: String::from_utf8_lossy(data.get(c + 16..c + 20)?).into_owned(),
        chunk: data.get(c + off + 4..c + off + 4 + n)?.to_vec(),
    })
}

/// Every saved plug-in state in enginedata, in file order.
pub fn plugin_states(enginedata: &[u8]) -> Vec<PluginState> {
    const TAG: &[u8] = b"\x0b\x00\x00\x00PluginState";
    let mut out = Vec::new();
    let mut p = 0;
    while let Some(i) = enginedata[p..].windows(TAG.len()).position(|w| w == TAG) {
        let a = p + i + TAG.len();
        p = a;
        let rec = (|| {
            let size = u64le(enginedata, a)? as usize;
            let owner = u64le(enginedata, a + 8)?;
            let end = (a + 8 + size).min(enginedata.len());
            let body = enginedata.get(a + 16..end)?;
            // u32 n, "VST3", u32 1, uid (32 hex chars), u64 len, data
            if body.get(4..8)? != b"VST3" {
                return None;
            }
            let uid = String::from_utf8_lossy(body.get(12..44)?).into_owned();
            let len = u64le(body, 44)? as usize;
            let data = body.get(52..(52 + len).min(body.len()))?.to_vec();
            let _ = u32le(body, 0)?;
            Some(PluginState { owner, uid, vst2: vst2_chunk(&data), data })
        })();
        if let Some(s) = rec {
            out.push(s);
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    fn enginedata(xml: &str, states: &[(u64, &str, &[u8])]) -> Vec<u8> {
        let mut b = Vec::new();
        for s in [&b"MixerData"[..], b"1.0 beta 3", b"MixerDocument"] {
            b.extend((s.len() as u32).to_le_bytes());
            b.extend(s);
        }
        let mut x = vec![0u8; 4];
        x.extend(xml.as_bytes());
        b.extend((x.len() as u32).to_le_bytes());
        b.extend(x);
        for (owner, uid, data) in states {
            let mut body = Vec::new();
            body.extend(40u32.to_le_bytes());
            body.extend(b"VST3");
            body.extend(1u32.to_le_bytes());
            body.extend(uid.as_bytes());
            body.extend((data.len() as u64).to_le_bytes());
            body.extend(*data);
            b.extend(b"\x0b\x00\x00\x00PluginState");
            b.extend(((body.len() + 8) as u64).to_le_bytes());
            b.extend(owner.to_le_bytes());
            b.extend(body);
        }
        b
    }

    const XML: &str = r#"<?xml version="1.0" encoding="UTF-8"?>
<mixer id="1"><channels id="2">
 <output-channel id="5" name="Out" gain="0.5"><pre-insert-section id="12"><insert-plugins id="15">
  <insert id="756" name="Compressor" slot="4" uid="5B38F28281144FFE80285FF7CCF20483"><ports id="757" /></insert>
 </insert-plugins></pre-insert-section></output-channel>
 <fx-return-channel id="758" name="Fx Reverb"><pre-insert-section id="765"><insert-plugins id="768">
  <insert id="788" name="REVerence" slot="1" uid="ED824AB48E0846D5959682F5626D0972" enabled="0"><ports id="789" /></insert>
 </insert-plugins></pre-insert-section><send-section id="773"><sends id="776" /></send-section></fx-return-channel>
 <instruments id="3"><instrument id="828" name="SWAM Flute 64bit" slot="2" uid="565354466C74435357414D20466C7574" /></instruments>
 <instrument-return-channel id="833" name="1" instrument-id="828"><pre-insert-section id="840"><insert-plugins id="843">
  <insert id="11030" name="VirtualSoundStage2_x64" slot="1" uid="565354506172617669727475616C736F"><ports id="11031" /></insert>
  <insert id="37908" slot="2"><ports id="37909" /></insert>
 </insert-plugins></pre-insert-section><post-insert-section id="844"><insert-plugins id="847">
  <insert id="900" name="EQ" slot="1" uid="AB"><ports id="901" /></insert></insert-plugins></post-insert-section>
 <send-section id="848"><sends id="851"><send id="864" slot="1" enabled="0" gain="0.500000" /></sends></send-section>
 </instrument-return-channel>
</channels></mixer>"#;

    #[test]
    fn reads_channels_inserts_sends() {
        let m = read_mixer(&enginedata(XML, &[])).unwrap();
        assert_eq!(m.rack.len(), 1);
        assert_eq!(m.channels.iter().map(|c| c.kind.as_str()).collect::<Vec<_>>(), ["output", "fx-return", "instrument-return"]);
        let out = &m.channels[0];
        assert_eq!(out.gain, Some(0.5));
        assert_eq!(out.inserts[0].name.as_deref(), Some("Compressor"));
        assert!(!m.channels[1].inserts[0].enabled);
        let ch = &m.channels[2];
        assert_eq!(m.rack_slot(ch.instrument_id.unwrap()).unwrap().slot, 2);
        assert_eq!(ch.inserts.len(), 3);
        assert_eq!(ch.inserts[1].name, None);
        assert!(ch.inserts[2].post_fader && !ch.inserts[0].post_fader);
        assert_eq!(ch.sends, vec![Send { id: 864, slot: 1, enabled: false, gain: Some(0.5) }]);
        assert_eq!(m.insert(37908).unwrap().0.id, 833);
        assert_eq!(m.fx_channels().count(), 1);
        assert!((db(0.5) + 6.0206).abs() < 1e-3);
    }

    #[test]
    fn reads_states_by_owner_and_vst2_chunk() {
        // a VST2 fxBank with an opaque chunk "hello"
        let mut bank = b"VstW\x00\x00\x00\x08\x00\x00\x00\x01\x00\x00\x00\x00".to_vec();
        let c = bank.len();
        bank.extend(b"CcnK\x00\x00\x00\x00FBCh\x00\x00\x00\x02Para");
        bank.resize(c + 156, 0);
        bank.extend(5u32.to_be_bytes());
        bank.extend(b"hello");
        let uid = "565354506172617669727475616C736F";
        let s = plugin_states(&enginedata(XML, &[(11030, uid, &bank), (756, "5B38F28281144FFE80285FF7CCF20483", b"raw")]));
        assert_eq!(s.len(), 2);
        assert_eq!(s[0].owner, 11030);
        assert_eq!(s[0].uid, uid);
        let v = s[0].vst2.as_ref().unwrap();
        assert_eq!((v.kind.as_str(), v.fx_id.as_str(), v.chunk.as_slice()), ("FBCh", "Para", &b"hello"[..]));
        assert_eq!((s[1].owner, s[1].vst2.is_none(), s[1].data.as_slice()), (756, true, &b"raw"[..]));
    }
}
