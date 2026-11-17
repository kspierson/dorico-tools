//! Building and editing score trees while keeping DTN's rules, plus event property tables.
//!
//! DTN rule: an element never has zero children. An empty container is a *leaf* with value ""
//! (and the array flag if it is an array). The helpers here switch between the two forms as
//! children come and go, so callers never write an invalid tree.
//!
//! Merged from the Python helpers in finale2dorico (`f2d/dorico/tree.py`: `L`, `E`, `A`, `prop`,
//! `ptable`, `event_head`) and dorico-hp (`doricohp/project.py`: `append_child`, `remove_children`,
//! `array_of`, `get_prop`, `set_prop`). Those copies go away when their tools move onto the
//! engine (dorico-hp in S5, f2d in S8/S13).

use crate::dtn::Node;
use crate::ratio::Ratio;
use std::collections::HashMap;

/// A flow's element tables: kind ("DynamicGroup", "BarDivision", "TonalityDivision", …) ->
/// element ID -> element (`…ElementDefinition`).
pub type ElementTables<'a> = HashMap<String, HashMap<&'a str, &'a Node>>;

/// The element tables of a flow (`elementTables/array`), by kind and element ID.
pub fn element_tables(flow: &Node) -> ElementTables<'_> {
    let mut out: ElementTables = HashMap::new();
    for t in flow.find("elementTables/array").map(Node::items).unwrap_or(&[]) {
        let kind = t.tag.strip_suffix("ElementTableDefinition").unwrap_or(&t.tag).to_owned();
        let m = t.child("array").map(Node::items).unwrap_or(&[]).iter().map(|e| (e.text("elementID"), e)).collect();
        out.insert(kind, m);
    }
    out
}

/// Element with children; no children gives an empty leaf (f2d `E`).
pub fn element(tag: &str, children: Vec<Node>) -> Node {
    if children.is_empty() { Node::leaf(tag, "") } else { Node::element(tag, children) }
}

/// Array element; an empty array is a leaf with the array flag (f2d `A`).
pub fn array(tag: &str, items: Vec<Node>) -> Node {
    let mut n = element(tag, items);
    n.array = true;
    n
}

/// Dorico's text for a position or duration (`"0"`, `"3/2"`).
pub fn pos(r: Ratio) -> String {
    r.to_string()
}

impl Node {
    /// Children of an `x/array` container, or of an array node itself (dorico-hp `array_of`).
    pub fn array_items(&self) -> &[Node] {
        match self.child("array") {
            Some(a) => &a.children,
            None => &self.children,
        }
    }

    /// Append a child, turning an empty leaf into an element first.
    pub fn push_child(&mut self, child: Node) {
        if self.value.is_some() {
            self.value = None;
            self.children.clear();
        }
        self.children.push(child);
    }

    /// Insert a child at `index`, turning an empty leaf into an element first.
    pub fn insert_child(&mut self, index: usize, child: Node) {
        if self.value.is_some() {
            self.value = None;
            self.children.clear();
        }
        let i = index.min(self.children.len());
        self.children.insert(i, child);
    }

    /// Remove matching children; with none left the node becomes an empty leaf. Returns how
    /// many were removed.
    pub fn remove_children(&mut self, mut pred: impl FnMut(&Node) -> bool) -> usize {
        if self.value.is_some() {
            return 0;
        }
        let before = self.children.len();
        self.children.retain(|c| !pred(c));
        let removed = before - self.children.len();
        if removed > 0 && self.children.is_empty() {
            self.value = Some("".into());
        }
        removed
    }

    /// Set a leaf child's value, adding the leaf at the end if missing.
    pub fn set_text(&mut self, tag: &str, value: &str) {
        match self.child_mut(tag) {
            Some(c) => {
                c.value = Some(value.into());
                c.children.clear();
            }
            None => self.push_child(Node::leaf(tag, value)),
        }
    }
}

// ---------------------------------------------------------------------------
// Property tables on events and elements
// ---------------------------------------------------------------------------

/// Property tables (`propertyTable/entries/entry{propertyType, value, context?}`).
///
/// "Unscoped" properties have no `context` and apply everywhere; scoped ones carry a layout /
/// block-instance context (f2d writes those for some layout-specific properties).
pub mod props {
    use super::{array, element};
    use crate::dtn::Node;

    pub const TABLE: &str = "propertyTable";

    /// `steamVariantList` value meaning "no layout / frame chain" in a property context.
    pub const NO_LAYOUT: &str = "steamVariantList:list: {int: -1}, {int: -1}, {bool: false}";

    /// Every entry of the node's property table (empty if none).
    pub fn entries(n: &Node) -> &[Node] {
        n.find("propertyTable/entries").map(|e| e.items()).unwrap_or(&[])
    }

    /// Value of an unscoped property (no `context`).
    pub fn get<'a>(n: &'a Node, ptype: &str) -> Option<&'a str> {
        entries(n)
            .iter()
            .find(|e| e.text("propertyType") == ptype && e.child("context").is_none())
            .map(|e| e.text("value"))
    }

    /// Integer value of an unscoped `"int: N"` property.
    pub fn get_int(n: &Node, ptype: &str) -> Option<i64> {
        get(n, ptype)?.strip_prefix("int: ")?.trim().parse().ok()
    }

    /// One property entry (f2d `prop`). With `offset`, a context entry for that property offset.
    pub fn entry(ptype: &str, value: &str, offset: Option<&str>) -> Node {
        let mut kids = vec![Node::leaf("propertyType", ptype), Node::leaf("value", value)];
        if let Some(off) = offset {
            kids.push(Node::element(
                "context",
                vec![
                    Node::leaf("layoutIDWithFrameChainID", NO_LAYOUT),
                    Node::leaf("blockInstanceID", "-1"),
                    Node::leaf("propertyOffset", &format!("string: \"{off}\"")),
                ],
            ));
        }
        Node::element("entry", kids)
    }

    /// A property table node (f2d `ptable`), empty entries allowed.
    pub fn table(entries: Vec<Node>) -> Node {
        element(TABLE, vec![array("entries", entries)])
    }

    /// Set (`Some`) or remove (`None`) an unscoped property. A missing table is created right
    /// after `secondaryEndOffset`, where Dorico puts it in every event seen so far.
    pub fn set(n: &mut Node, ptype: &str, value: Option<&str>) {
        if n.child(TABLE).is_none() {
            if value.is_none() {
                return;
            }
            let at =
                n.children.iter().position(|c| &*c.tag == "secondaryEndOffset").map_or(n.children.len(), |i| i + 1);
            n.insert_child(at, table(Vec::new()));
        }
        let t = n.child_mut(TABLE).expect("table exists");
        if t.child("entries").is_none() {
            t.push_child(array("entries", Vec::new()));
        }
        let entries = t.child_mut("entries").expect("entries exist");
        entries.remove_children(|e| e.text("propertyType") == ptype && e.child("context").is_none());
        if let Some(v) = value {
            entries.push_child(entry(ptype, v, None));
        }
    }
}

/// The standard head of an event (f2d `event_head`): eventID, position, secondaryPosition,
/// duration, secondaryEndOffset, propertyTable.
pub fn event_head(id: u64, position: Ratio, duration: Ratio, props: Vec<Node>) -> Vec<Node> {
    vec![
        Node::leaf("eventID", &id.to_string()),
        Node::leaf("position", &pos(position)),
        Node::leaf("secondaryPosition", "0"),
        Node::leaf("duration", &pos(duration)),
        Node::leaf("secondaryEndOffset", "0"),
        props::table(props),
    ]
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::dtn::{Document, decode, encode};

    fn ev() -> Node {
        Node::element(
            "NoteEventDefinition",
            vec![Node::leaf("eventID", "5"), Node::leaf("secondaryEndOffset", "0"), Node::leaf("pitch", "60")],
        )
    }

    #[test]
    fn empty_containers_stay_valid() {
        let mut a = array("events", vec![]);
        assert_eq!((a.value.as_deref(), a.array), (Some(""), true));
        a.push_child(Node::leaf("x", "1"));
        assert!(!a.is_leaf() && a.array);
        assert_eq!(a.remove_children(|_| true), 1);
        assert_eq!(a.value.as_deref(), Some(""));
        // still encodes (an element with zero children would not be valid DTN)
        let d = Document { root: Node::element("root", vec![a]), marker: 0 };
        assert_eq!(decode(&encode(&d)).unwrap(), d);
    }

    #[test]
    fn properties() {
        let mut e = ev();
        assert_eq!(props::get(&e, "kNoteVelocity"), None);
        props::set(&mut e, "kNoteVelocity", None); // no table made for a removal
        assert!(e.child("propertyTable").is_none());
        props::set(&mut e, "kNoteVelocity", Some("int: 90"));
        assert_eq!(e.children[2].tag.as_ref(), "propertyTable", "table goes after secondaryEndOffset");
        assert_eq!(props::get_int(&e, "kNoteVelocity"), Some(90));
        props::set(&mut e, "kNoteVelocity", Some("int: 70"));
        assert_eq!(props::entries(&e).len(), 1);
        assert_eq!(props::get_int(&e, "kNoteVelocity"), Some(70));
        // scoped entries are not unscoped values and are left alone
        let t = e.find_mut("propertyTable/entries").unwrap();
        t.push_child(props::entry("kNoteVelocity", "int: 1", Some("0:0:1:0")));
        props::set(&mut e, "kNoteVelocity", None);
        assert_eq!(props::get(&e, "kNoteVelocity"), None);
        assert_eq!(props::entries(&e).len(), 1);
    }

    #[test]
    fn heads_and_arrays() {
        let h = event_head(7, Ratio::new(3, 2), Ratio::int(1), vec![]);
        assert_eq!(h[1].value.as_deref(), Some("3/2"));
        assert_eq!(h[5].find("entries").unwrap().value.as_deref(), Some(""));
        let flow = Node::element("blocks", vec![Node::element("array", vec![Node::leaf("block", "")])]);
        assert_eq!(flow.array_items().len(), 1);
    }
}
