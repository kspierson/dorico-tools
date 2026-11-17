//! ID allocation from the score's `idGenerators`, and a check that the counters are ahead of
//! every ID in use.
//!
//! Each `idGenerators/<kind>` leaf holds the **next free** value for that kind (verified on the
//! test files: `event` = highest `eventID` + 1). New items take the counter and bump it, as
//! dorico-hp's Apply does. dorigit's merge (MERGE.md) also needs renumbering; that builds on this.

use crate::dtn::Node;
use anyhow::{Context, Result};
use std::collections::BTreeMap;

/// Which ID leaves belong to which counter. Only kinds whose IDs appear under one obvious tag
/// are listed; others (eventGroup, doodle, ...) are allocated but not checked.
pub const KIND_TAGS: &[(&str, &[&str])] = &[
    ("event", &["eventID"]),
    ("eventStream", &["streamID"]),
    ("block", &["blockID"]),
    ("blockInstance", &["blockInstanceID"]),
    ("instrument", &["instrumentID"]),
    ("player", &["playerID"]),
    ("layout", &["layoutID"]),
    ("flow", &["flowID"]),
    ("stave", &["staveID"]),
];

/// Take the next ID of a kind (`event`, `eventStream`, `block`, `blockInstance`, `eventGroup`, ...)
/// and advance the counter.
pub fn next_id(root: &mut Node, kind: &str) -> Result<u64> {
    let n = root.find_mut(&format!("idGenerators/{kind}")).with_context(|| format!("no idGenerators/{kind}"))?;
    let v: u64 =
        n.value.as_deref().unwrap_or("").parse().with_context(|| format!("idGenerators/{kind} is not a number"))?;
    n.value = Some((v + 1).to_string().into());
    Ok(v)
}

/// The counters as they are now (next free value per kind).
pub fn counters(root: &Node) -> BTreeMap<String, u64> {
    root.child("idGenerators")
        .map(|g| {
            g.items().iter().filter_map(|c| Some((c.tag.to_string(), c.value.as_deref()?.parse().ok()?))).collect()
        })
        .unwrap_or_default()
}

/// Highest ID in use per checked kind (see [`KIND_TAGS`]).
pub fn max_used(root: &Node) -> BTreeMap<&'static str, i64> {
    let mut by_tag: BTreeMap<&str, &'static str> = BTreeMap::new();
    for (kind, tags) in KIND_TAGS {
        for t in *tags {
            by_tag.insert(t, kind);
        }
    }
    let mut out = BTreeMap::new();
    root.walk(|n| {
        if let (Some(v), Some(kind)) = (n.value.as_deref(), by_tag.get(&*n.tag))
            && let Ok(i) = v.parse::<i64>()
        {
            let e = out.entry(*kind).or_insert(i);
            *e = (*e).max(i);
        }
    });
    out
}

/// Problems that would make new IDs collide: a counter at or below an ID already in use.
pub fn check(root: &Node) -> Vec<String> {
    let c = counters(root);
    max_used(root)
        .into_iter()
        .filter_map(|(kind, used)| match c.get(kind) {
            Some(&next) if (next as i64) > used => None,
            Some(&next) => Some(format!("idGenerators/{kind} is {next} but {kind} ID {used} is in use")),
            None => Some(format!("no idGenerators/{kind} counter ({kind} IDs up to {used} in use)")),
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn score() -> Node {
        Node::element(
            "score",
            vec![
                Node::element("idGenerators", vec![Node::leaf("event", "10"), Node::leaf("eventGroup", "3")]),
                Node::element("e", vec![Node::leaf("eventID", "9")]),
            ],
        )
    }

    #[test]
    fn allocates_and_checks() {
        let mut s = score();
        assert!(check(&s).is_empty());
        assert_eq!(next_id(&mut s, "event").unwrap(), 10);
        assert_eq!(next_id(&mut s, "event").unwrap(), 11);
        assert_eq!(counters(&s)["event"], 12);
        assert!(next_id(&mut s, "nope").is_err());
        s.find_mut("idGenerators/event").unwrap().value = Some("9".into());
        assert_eq!(check(&s), vec!["idGenerators/event is 9 but event ID 9 is in use".to_string()]);
    }
}
