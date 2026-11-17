//! Dorico's binary DTN format (`score.dtn`, `scorelibrary.dtn`) and the
//! equivalent XML text form (`score.xml`).
//!
//! DTN is a compact encoding of an XML-like tree. Layout (little-endian):
//!
//! ```text
//! u32 version (4), u32 unknown (1)
//! u32 nKeys,   nKeys   NUL-terminated UTF-8 strings   -- tag names, first-use order
//! u32 nValues, nValues NUL-terminated UTF-8 strings   -- "" first, then first-use order
//! u32 nNodes,  nNodes  node records in pre-order (node 0 = root)
//!   node = type byte, then LEB128 varints
//!     leaf    (type & 2 == 0): key, value
//!     element (type & 2 != 0): key, 0, nChildren, child indices...
//!     type & 1  -> array="true"
//!     type >> 2 -> per-file constant ("marker"); meaning unknown, preserved
//! ```
//!
//! Every DTN file seen so far (Dorico 2.0.5 - 5.1.60) re-encodes byte-for-byte.
//! See dorigit/docs/RESEARCH.md for how this was established.

use anyhow::{Context, Result, bail, ensure};
use std::collections::HashMap;
use std::sync::Arc;

pub type Str = Arc<str>;

/// One node of the score tree. `value` is `Some` for leaves, `None` for elements.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Node {
    pub tag: Str,
    pub value: Option<Str>,
    pub array: bool,
    pub children: Vec<Node>,
}

impl Node {
    pub fn leaf(tag: &str, value: &str) -> Node {
        Node { tag: tag.into(), value: Some(value.into()), array: false, children: Vec::new() }
    }

    pub fn element(tag: &str, children: Vec<Node>) -> Node {
        Node { tag: tag.into(), value: None, array: false, children }
    }

    pub fn is_leaf(&self) -> bool {
        self.value.is_some()
    }

    /// First child with this tag.
    pub fn child(&self, tag: &str) -> Option<&Node> {
        self.children.iter().find(|c| &*c.tag == tag)
    }

    pub fn child_mut(&mut self, tag: &str) -> Option<&mut Node> {
        self.children.iter_mut().find(|c| &*c.tag == tag)
    }

    /// Text of a leaf child, or "" if missing / not a leaf.
    pub fn text(&self, tag: &str) -> &str {
        self.child(tag).and_then(|c| c.value.as_deref()).unwrap_or("")
    }

    /// Follow a `a/b/c` path of child tags.
    pub fn find(&self, path: &str) -> Option<&Node> {
        path.split('/').try_fold(self, |n, part| n.child(part))
    }

    pub fn find_mut(&mut self, path: &str) -> Option<&mut Node> {
        let mut n = self;
        for part in path.split('/') {
            n = n.child_mut(part)?;
        }
        Some(n)
    }

    /// Children of an array container (empty if none).
    pub fn items(&self) -> &[Node] {
        &self.children
    }

    /// Visit every node depth-first (pre-order), without recursion.
    pub fn walk(&self, mut f: impl FnMut(&Node)) {
        let mut stack = vec![self];
        while let Some(n) = stack.pop() {
            f(n);
            stack.extend(n.children.iter().rev());
        }
    }
}

/// A decoded DTN document: the tree plus the per-file marker bits.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Document {
    pub root: Node,
    pub marker: u8,
}

pub const DTN_VERSION: u32 = 4;

// ---------------------------------------------------------------------------
// Binary
// ---------------------------------------------------------------------------

struct Cursor<'a> {
    data: &'a [u8],
    pos: usize,
}

impl Cursor<'_> {
    fn u32(&mut self) -> Result<u32> {
        let b = self.data.get(self.pos..self.pos + 4).context("truncated DTN (u32)")?;
        self.pos += 4;
        Ok(u32::from_le_bytes(b.try_into().unwrap()))
    }

    fn byte(&mut self) -> Result<u8> {
        let b = *self.data.get(self.pos).context("truncated DTN")?;
        self.pos += 1;
        Ok(b)
    }

    fn varint(&mut self) -> Result<usize> {
        let mut r: u64 = 0;
        let mut shift = 0;
        loop {
            let b = self.byte()?;
            ensure!(shift < 64, "varint too long at offset {}", self.pos);
            r |= u64::from(b & 0x7f) << shift;
            shift += 7;
            if b < 0x80 {
                return Ok(r as usize);
            }
        }
    }

    fn table(&mut self) -> Result<Vec<Str>> {
        let n = self.u32()? as usize;
        let mut out = Vec::with_capacity(n);
        for _ in 0..n {
            let rest = &self.data[self.pos..];
            let end = rest.iter().position(|&b| b == 0).context("unterminated DTN string")?;
            let s = std::str::from_utf8(&rest[..end]).context("DTN string is not UTF-8")?;
            out.push(Str::from(s));
            self.pos += end + 1;
        }
        Ok(out)
    }
}

pub fn decode(data: &[u8]) -> Result<Document> {
    let mut c = Cursor { data, pos: 0 };
    let version = c.u32()?;
    if version != DTN_VERSION {
        bail!("unsupported DTN version {version}");
    }
    c.u32()?;
    let keys = c.table()?;
    let vals = c.table()?;
    let count = c.u32()? as usize;
    ensure!(count > 0, "DTN has no nodes");

    enum Raw {
        Leaf(usize, usize),
        Element(usize, Vec<usize>),
    }
    let mut raw = Vec::with_capacity(count);
    let mut flags = Vec::with_capacity(count);
    let mut marker = None;
    for _ in 0..count {
        let t = c.byte()?;
        match marker {
            None => marker = Some(t >> 2),
            Some(m) if m != t >> 2 => bail!("mixed node markers ({m} and {}); format not understood", t >> 2),
            _ => {}
        }
        flags.push(t & 1 == 1);
        let key = c.varint()?;
        ensure!(key < keys.len(), "tag index out of range");
        if t & 2 == 0 {
            let v = c.varint()?;
            ensure!(v < vals.len(), "value index out of range");
            raw.push(Raw::Leaf(key, v));
        } else {
            c.varint()?; // always 0 so far
            let n = c.varint()?;
            let mut kids = Vec::with_capacity(n);
            for _ in 0..n {
                let k = c.varint()?;
                ensure!(k < count, "child index out of range");
                kids.push(k);
            }
            raw.push(Raw::Element(key, kids));
        }
    }
    ensure!(c.pos == data.len(), "{} unexpected trailing bytes", data.len() - c.pos);

    // Children always come after their parent (pre-order), so build back to front.
    let mut built: Vec<Option<Node>> = (0..count).map(|_| None).collect();
    for i in (0..count).rev() {
        let node = match &raw[i] {
            Raw::Leaf(k, v) => {
                Node { tag: keys[*k].clone(), value: Some(vals[*v].clone()), array: flags[i], children: Vec::new() }
            }
            Raw::Element(k, kids) => {
                let mut children = Vec::with_capacity(kids.len());
                for &kid in kids {
                    ensure!(kid > i, "DTN child precedes parent");
                    children.push(built[kid].take().context("DTN node graph is not a tree")?);
                }
                Node { tag: keys[*k].clone(), value: None, array: flags[i], children }
            }
        };
        built[i] = Some(node);
    }
    let root = built[0].take().unwrap();
    ensure!(built.iter().all(Option::is_none), "DTN has unreachable nodes");
    Ok(Document { root, marker: marker.unwrap_or(0) })
}

pub fn encode(doc: &Document) -> Vec<u8> {
    let mut keys: Vec<&str> = Vec::new();
    let mut kidx: HashMap<&str, usize> = HashMap::new();
    let mut vals: Vec<&str> = vec![""];
    let mut vidx: HashMap<&str, usize> = HashMap::from([("", 0)]);
    // pre-order flattening; each entry = node + its child indices
    let mut flat: Vec<(&Node, Vec<usize>)> = Vec::new();
    let mut stack: Vec<(&Node, Option<usize>)> = vec![(&doc.root, None)];
    while let Some((n, parent)) = stack.pop() {
        let next = keys.len();
        kidx.entry(&n.tag).or_insert_with(|| {
            keys.push(&n.tag);
            next
        });
        if let Some(v) = n.value.as_deref() {
            let next = vals.len();
            vidx.entry(v).or_insert_with(|| {
                vals.push(v);
                next
            });
        }
        let i = flat.len();
        flat.push((n, Vec::new()));
        if let Some(p) = parent {
            flat[p].1.push(i);
        }
        for child in n.children.iter().rev() {
            stack.push((child, Some(i)));
        }
    }

    let mut out = Vec::with_capacity(flat.len() * 6);
    out.extend_from_slice(&DTN_VERSION.to_le_bytes());
    out.extend_from_slice(&1u32.to_le_bytes());
    for table in [&keys, &vals] {
        out.extend_from_slice(&(table.len() as u32).to_le_bytes());
        for s in table.iter() {
            out.extend_from_slice(s.as_bytes());
            out.push(0);
        }
    }
    out.extend_from_slice(&(flat.len() as u32).to_le_bytes());

    fn varint(out: &mut Vec<u8>, mut n: usize) {
        loop {
            let b = (n & 0x7f) as u8;
            n >>= 7;
            if n == 0 {
                out.push(b);
                return;
            }
            out.push(b | 0x80);
        }
    }

    let m = doc.marker << 2;
    for (n, kids) in &flat {
        let is_element = !n.is_leaf();
        out.push(m | u8::from(n.array) | if is_element { 2 } else { 0 });
        varint(&mut out, kidx[&*n.tag]);
        match n.value.as_deref() {
            Some(v) => varint(&mut out, vidx[v]),
            None => {
                varint(&mut out, 0);
                varint(&mut out, kids.len());
                for &k in kids {
                    varint(&mut out, k);
                }
            }
        }
    }
    out
}
