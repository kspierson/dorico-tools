//! XML text form of the score tree, in the same layout Dorico uses for
//! `score.xml` (tab indentation, `<tag/>` for empty values, `array="true"`).
//!
//! Lossless: `encode(from_xml(to_xml(doc)))` reproduces the original DTN bytes.
//! The DTN marker is kept in a processing instruction (`<?dorigit-dtn-marker N?>`).
//! Output is byte-identical to the old Python `to_xml` (oracle: engine/tests/oracles/dtn_py.py).

use crate::dtn::{Document, Node, Str};
use anyhow::{Context, Result, bail};
use quick_xml::events::Event;
use std::collections::HashMap;

pub const MARKER_PI: &str = "dorigit-dtn-marker";

fn escape_into(out: &mut String, s: &str) {
    for ch in s.chars() {
        match ch {
            '&' => out.push_str("&amp;"),
            '<' => out.push_str("&lt;"),
            '>' => out.push_str("&gt;"),
            '\r' => out.push_str("&#13;"),
            c => out.push(c),
        }
    }
}

pub fn to_xml(doc: &Document, with_marker: bool) -> String {
    let mut out = String::with_capacity(1 << 20);
    out.push_str("<?xml version=\"1.0\" encoding=\"utf-8\"?>\n");
    if with_marker {
        out.push_str(&format!("<?{MARKER_PI} {}?>\n", doc.marker));
    }
    enum Step<'a> {
        Open(&'a Node, usize),
        Close(&'a Node, usize),
    }
    let mut stack = vec![Step::Open(&doc.root, 0)];
    while let Some(step) = stack.pop() {
        match step {
            Step::Close(n, depth) => {
                out.extend(std::iter::repeat_n('\t', depth));
                out.push_str("</");
                out.push_str(&n.tag);
                out.push_str(">\n");
            }
            Step::Open(n, depth) => {
                out.extend(std::iter::repeat_n('\t', depth));
                out.push('<');
                out.push_str(&n.tag);
                if n.array {
                    out.push_str(" array=\"true\"");
                }
                match n.value.as_deref() {
                    Some("") => out.push_str("/>\n"),
                    Some(v) => {
                        out.push('>');
                        escape_into(&mut out, v);
                        out.push_str("</");
                        out.push_str(&n.tag);
                        out.push_str(">\n");
                    }
                    None if n.children.is_empty() => out.push_str("/>\n"),
                    None => {
                        out.push_str(">\n");
                        stack.push(Step::Close(n, depth));
                        for c in n.children.iter().rev() {
                            stack.push(Step::Open(c, depth + 1));
                        }
                    }
                }
            }
        }
    }
    out
}

/// Read the marker from the `<?dorigit-dtn-marker N?>` instruction, if present.
fn read_marker(text: &[u8]) -> u8 {
    let head = String::from_utf8_lossy(&text[..text.len().min(300)]);
    let tag = format!("<?{MARKER_PI} ");
    head.split_once(&tag)
        .and_then(|(_, rest)| rest.split_once("?>"))
        .and_then(|(n, _)| n.trim().parse().ok())
        .unwrap_or(0)
}

pub fn from_xml(text: &[u8]) -> Result<Document> {
    struct Frame {
        tag: Str,
        array: bool,
        children: Vec<Node>,
        text: String,
        element: bool,
    }
    let mut interned: HashMap<String, Str> = HashMap::new();
    let mut intern = |s: &str| -> Str {
        if let Some(v) = interned.get(s) {
            return v.clone();
        }
        let v: Str = s.into();
        interned.insert(s.to_owned(), v.clone());
        v
    };

    let mut reader = quick_xml::Reader::from_reader(text);
    reader.config_mut().trim_text(false);
    let mut buf = Vec::new();
    let mut stack: Vec<Frame> = Vec::new();
    let mut root: Option<Node> = None;

    loop {
        let event = reader.read_event_into(&mut buf).context("invalid XML")?;
        match event {
            Event::Start(ref e) | Event::Empty(ref e) => {
                let is_empty = matches!(event, Event::Empty(_));
                let tag = intern(std::str::from_utf8(e.name().as_ref())?);
                let mut array = false;
                for a in e.attributes() {
                    let a = a?;
                    if a.key.as_ref() == b"array" && a.value.as_ref() == b"true" {
                        array = true;
                    }
                }
                if let Some(top) = stack.last_mut() {
                    top.element = true;
                    top.text.clear();
                }
                if is_empty {
                    let node = Node { tag, value: Some(intern("")), array, children: Vec::new() };
                    match stack.last_mut() {
                        Some(top) => top.children.push(node),
                        None => root = Some(node),
                    }
                } else {
                    stack.push(Frame { tag, array, children: Vec::new(), text: String::new(), element: false });
                }
            }
            Event::Text(t) => {
                if let Some(top) = stack.last_mut()
                    && !top.element
                {
                    top.text.push_str(&t.unescape()?);
                }
            }
            Event::CData(t) => {
                if let Some(top) = stack.last_mut()
                    && !top.element
                {
                    top.text.push_str(std::str::from_utf8(&t)?);
                }
            }
            Event::End(_) => {
                let f = stack.pop().context("unbalanced XML")?;
                let node = if f.element {
                    Node { tag: f.tag, value: None, array: f.array, children: f.children }
                } else {
                    Node { tag: f.tag, value: Some(intern(&f.text)), array: f.array, children: Vec::new() }
                };
                match stack.last_mut() {
                    Some(top) => top.children.push(node),
                    None => root = Some(node),
                }
            }
            Event::Eof => break,
            _ => {}
        }
        buf.clear();
    }
    if !stack.is_empty() {
        bail!("XML ended inside <{}>", stack.last().unwrap().tag);
    }
    Ok(Document { root: root.context("XML has no root element")?, marker: read_marker(text) })
}
