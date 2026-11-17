//! Merge preview (MERGE.md §4, milestone M1): what combining two versions with a common base
//! would do, region by region. Read-only: nothing is written (applying comes with the engine's
//! edit layer, M2).
//!
//! Each side is diffed against the base (dorigit's tidied diff). Every change is put in a
//! **lane** (§4.1) and a **region** `(flow, player, stave/voice, bar)` (§4.2), then the two
//! sides are compared per region (§4.3, stricter than git):
//!
//! | Outcome | When |
//! |---|---|
//! | `Same` | both sides made the identical change (applied once) |
//! | `Auto` | only one side touched the region |
//! | `Review` | combinable but maybe a creative decision: other voice / divisi stave of the same bar; music on one side and engraving on the other; neighbouring bars of the same player |
//! | `Conflict` | both sides changed the same region differently; both changed the same option or player; both restructured a flow |
//!
//! Structure changes (bars inserted/removed) are detected and reported; re-mapping positions
//! through them is milestone M4, so later bars of a restructured flow are compared as they are.

use crate::tidy;
use dorico_format::Score;
use dorico_format::diff::{Change, EventChange, ScoreDiff, SettingChange};
use serde::Serialize;
use std::collections::{BTreeMap, BTreeSet};

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Outcome {
    Conflict,
    Review,
    Auto,
    Same,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Lane {
    Structure,
    Music,
    Orchestration,
    Engraving,
    Settings,
    Playback,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Side {
    Ours,
    Theirs,
    Both,
}

/// One row of the preview: a region and what each side did there.
#[derive(Debug, Clone, Serialize)]
pub struct Item {
    pub outcome: Outcome,
    pub lane: Lane,
    pub side: Side,
    pub flow: String,
    /// Player name, "(global)" or "" for project-wide items.
    pub owner: String,
    /// "voice 1", "stave 2", or "" (one stave, one voice).
    pub voice: String,
    /// Bar label ("17", "35a"), or "" when not bar-based.
    pub bar: String,
    /// What our side did there (one line per change).
    pub ours: Vec<String>,
    /// What their side did there.
    pub theirs: Vec<String>,
    /// Why this outcome (for review/conflict).
    pub reason: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct StructureNote {
    pub flow: String,
    pub side: Side,
    pub text: String,
}

#[derive(Debug, Clone, Serialize, Default)]
pub struct Counts {
    pub conflict: usize,
    pub review: usize,
    pub auto: usize,
    pub same: usize,
}

#[derive(Debug, Clone, Serialize)]
pub struct Preview {
    pub items: Vec<Item>,
    pub structure: Vec<StructureNote>,
    pub counts: Counts,
    /// Problems found by the ID checker in either version (would break an apply).
    pub integrity: Vec<String>,
}

// ---------------------------------------------------------------------------------------

/// Properties that only affect engraving (positions, placement, visibility, stems…).
fn engraving_prop(p: &str) -> bool {
    p.contains("(layout-specific)")
        || ["Dx", "Dy", "Offset", "Placement", "Visibility", "Direction", "Stem", "Beam", "Position", "Hidden"]
            .iter()
            .any(|k| p.split('=').next().is_some_and(|name| name.contains(k)))
}

fn playback_prop(p: &str) -> bool {
    let name = p.split('=').next().unwrap_or("");
    name.contains("Muted") || name.contains("Velocity") || name.contains("Playback")
}

/// Lane of one event change.
fn lane_of(c: &EventChange, owner: &str) -> Lane {
    if owner.starts_with('(') {
        return match c.kind.as_str() {
            "marker" => Lane::Structure,
            "break" | "condensation label" | "condensing change" | "frame break" | "system break" => Lane::Engraving,
            _ => Lane::Structure,
        };
    }
    if matches!(c.kind.as_str(), "break" | "condensation label" | "condensing change" | "bracket and barline change") {
        return Lane::Engraving;
    }
    if c.change == Change::Modified {
        // only property changes: engraving or playback if all of them are
        let props: Vec<&str> = c
            .details
            .iter()
            .flat_map(|d| {
                d.strip_prefix("removed ").or_else(|| d.strip_prefix("added ")).map(|r| r.split("; ").collect::<Vec<_>>())
            })
            .flatten()
            .collect();
        let only_props = c.details.iter().all(|d| d.starts_with("removed ") || d.starts_with("added "));
        if only_props && !props.is_empty() {
            if props.iter().all(|p| engraving_prop(p)) {
                return Lane::Engraving;
            }
            if props.iter().all(|p| playback_prop(p)) {
                return Lane::Playback;
            }
        }
    }
    Lane::Music
}

fn bar_label(where_: &str) -> String {
    where_.strip_prefix("bar ").and_then(|r| r.split(' ').next()).unwrap_or("").to_owned()
}

fn describe(c: &EventChange) -> String {
    let at = c.where_.replace("bar ", "b.");
    match c.change {
        Change::Added => format!("{at}: added {} {}", c.kind, c.text).trim_end().to_owned(),
        Change::Removed => format!("{at}: removed {} {}", c.kind, c.text).trim_end().to_owned(),
        Change::Modified => format!("{at}: {} {}", c.kind, c.details.join("; ")),
    }
}

/// Drop Dorico's internal element numbers ("slurElementID=104"): the same slur gets different
/// numbers in two versions.
fn without_ids(s: &str) -> String {
    s.split(' ').filter(|w| !w.contains("ElementID=")).collect::<Vec<_>>().join(" ").replace(", ,", ",")
}

/// A change's identity for "both sides did the same thing".
fn signature(c: &EventChange) -> String {
    format!(
        "{:?}|{}|{}|{}|{}|{}",
        c.change,
        c.lane,
        c.kind,
        c.position,
        without_ids(&c.text),
        c.details.iter().map(|d| without_ids(d)).collect::<Vec<_>>().join("; ")
    )
}

#[derive(Default)]
struct Bucket<'a> {
    ours: Vec<&'a EventChange>,
    theirs: Vec<&'a EventChange>,
}

/// (flow name, owner, voice/lane, bar number, bar label, lane)
type Key = (String, String, String, i128, String, Lane);
/// Per (flow, owner): which side touched which (voice, bar number, lane).
type Touched = BTreeMap<(String, String), Vec<(Side, String, i128, Lane)>>;

fn collect<'a>(d: &'a ScoreDiff, ours: bool, buckets: &mut BTreeMap<Key, Bucket<'a>>) {
    for f in d.flows.iter().filter(|f| f.change == Change::Modified) {
        for o in &f.owners {
            for c in &o.changes {
                let lane = lane_of(c, &o.owner);
                let key = (
                    f.name.clone(),
                    o.owner.clone(),
                    c.lane.clone(),
                    c.bar.unwrap_or(-1),
                    bar_label(&c.where_),
                    lane,
                );
                let b = buckets.entry(key).or_default();
                if ours {
                    b.ours.push(c);
                } else {
                    b.theirs.push(c);
                }
            }
        }
    }
}

/// Preview merging `ours` and `theirs`, both descended from `base`.
pub fn preview(base: &Score, ours: &Score, theirs: &Score) -> Preview {
    let d_ours = tidy::diff(base, ours);
    let d_theirs = tidy::diff(base, theirs);
    let mut items = Vec::new();
    let mut structure = Vec::new();

    // --- structure: flows added/removed, bars inserted/removed --------------------------
    for (d, side, score) in [(&d_ours, Side::Ours, ours), (&d_theirs, Side::Theirs, theirs)] {
        for f in &d.flows {
            match f.change {
                Change::Added => structure.push(StructureNote { flow: f.name.clone(), side, text: "flow added".into() }),
                Change::Removed => {
                    structure.push(StructureNote { flow: f.name.clone(), side, text: "flow removed".into() })
                }
                Change::Modified => {}
            }
        }
        for bf in &base.flows {
            let Some(sf) = score.flows.iter().find(|x| x.flow_id == bf.flow_id) else { continue };
            let (nb, ns) = (bf.bars.len(), sf.bars.len());
            let starts_differ = bf.bars.iter().zip(&sf.bars).any(|(a, b)| a.start != b.start);
            if nb != ns || starts_differ {
                let text = if ns > nb {
                    format!("{} bar{} added ({nb} -> {ns})", ns - nb, if ns - nb == 1 { "" } else { "s" })
                } else if ns < nb {
                    format!("{} bar{} removed ({nb} -> {ns})", nb - ns, if nb - ns == 1 { "" } else { "s" })
                } else {
                    "bar lengths changed (time signatures)".to_owned()
                };
                structure.push(StructureNote { flow: sf.name.clone(), side, text });
            }
        }
    }
    let restructured = |side: Side, flow: &str| structure.iter().any(|s| s.side == side && s.flow == flow);
    let flows: BTreeSet<String> = structure.iter().map(|s| s.flow.clone()).collect();
    for flow in flows {
        if restructured(Side::Ours, &flow) && restructured(Side::Theirs, &flow) {
            items.push(Item {
                outcome: Outcome::Conflict,
                lane: Lane::Structure,
                side: Side::Both,
                flow: flow.clone(),
                owner: "(global)".into(),
                voice: String::new(),
                bar: String::new(),
                ours: structure.iter().filter(|s| s.side == Side::Ours && s.flow == flow).map(|s| s.text.clone()).collect(),
                theirs: structure
                    .iter()
                    .filter(|s| s.side == Side::Theirs && s.flow == flow)
                    .map(|s| s.text.clone())
                    .collect(),
                reason: "both versions changed this flow's bars: choose whose structure to keep".into(),
            });
        }
    }

    // --- events, by region ---------------------------------------------------------------
    let mut buckets: BTreeMap<Key, Bucket> = BTreeMap::new();
    collect(&d_ours, true, &mut buckets);
    collect(&d_theirs, false, &mut buckets);

    // which bars each side touched per (flow, owner) and lane: for review rules
    let mut touched: Touched = BTreeMap::new();
    for ((flow, owner, voice, num, _, lane), b) in &buckets {
        for (side, list) in [(Side::Ours, &b.ours), (Side::Theirs, &b.theirs)] {
            if !list.is_empty() {
                touched.entry((flow.clone(), owner.clone())).or_default().push((side, voice.clone(), *num, *lane));
            }
        }
    }

    for ((flow, owner, voice, num, bar, lane), b) in &buckets {
        let line = |v: &[&EventChange]| v.iter().map(|c| describe(c)).collect::<Vec<_>>();
        let base_item = |outcome, side, ours: Vec<String>, theirs: Vec<String>, reason: String| Item {
            outcome,
            lane: *lane,
            side,
            flow: flow.clone(),
            owner: owner.clone(),
            voice: voice.clone(),
            bar: bar.clone(),
            ours,
            theirs,
            reason,
        };
        // identical changes on both sides are applied once; the rest decide the outcome
        let st: BTreeSet<String> = b.theirs.iter().map(|c| signature(c)).collect();
        let so: BTreeSet<String> = b.ours.iter().map(|c| signature(c)).collect();
        let shared: Vec<&EventChange> = b.ours.iter().copied().filter(|c| st.contains(&signature(c))).collect();
        let ours_rest: Vec<&EventChange> = b.ours.iter().copied().filter(|c| !st.contains(&signature(c))).collect();
        let theirs_rest: Vec<&EventChange> = b.theirs.iter().copied().filter(|c| !so.contains(&signature(c))).collect();
        if !shared.is_empty() {
            items.push(base_item(Outcome::Same, Side::Both, line(&shared), line(&shared), String::new()));
        }
        match (ours_rest.is_empty(), theirs_rest.is_empty()) {
            (true, true) => {}
            (false, false) => items.push(base_item(
                Outcome::Conflict,
                Side::Both,
                line(&ours_rest),
                line(&theirs_rest),
                "both versions changed this bar differently".into(),
            )),
            (ours_none, _) => {
                let (side, other) = if ours_none { (Side::Theirs, Side::Ours) } else { (Side::Ours, Side::Theirs) };
                let others = touched.get(&(flow.clone(), owner.clone())).map(Vec::as_slice).unwrap_or(&[]);
                let global = owner.starts_with('(');
                let same_bar_other_voice =
                    others.iter().any(|(s, v, n, l)| *s == other && *n == *num && v != voice && *l == *lane);
                let same_bar_other_lane =
                    others.iter().any(|(s, v, n, l)| *s == other && *n == *num && v == voice && *l != *lane);
                let neighbour = others.iter().any(|(s, _, n, l)| *s == other && (*n - *num).abs() == 1 && *l == *lane);
                let (outcome, reason) = if !global && same_bar_other_voice {
                    (
                        Outcome::Review,
                        format!(
                            "the other version changed another voice/stave of {owner} in this bar (e.g. divisi IA/IB): confirm they belong together"
                        ),
                    )
                } else if !global && same_bar_other_lane {
                    (
                        Outcome::Review,
                        "the other version changed something else here (music vs engraving/playback): check they still fit"
                            .to_owned(),
                    )
                } else if !global && neighbour && *lane == Lane::Music {
                    (
                        Outcome::Review,
                        "the other version changed a neighbouring bar of this player (ties, slurs, hairpins may join them)"
                            .to_owned(),
                    )
                } else {
                    (Outcome::Auto, String::new())
                };
                let (o, t) = if ours_none { (Vec::new(), line(&theirs_rest)) } else { (line(&ours_rest), Vec::new()) };
                items.push(base_item(outcome, side, o, t, reason));
            }
        }
    }

    // --- players (orchestration) ---------------------------------------------------------
    let players = |d: &ScoreDiff| -> BTreeMap<String, String> {
        d.players
            .iter()
            .map(|p| {
                let key = p.old.clone().or_else(|| p.new.clone()).unwrap_or_default();
                let what = match p.change {
                    Change::Added => format!("added {}", p.new.as_deref().unwrap_or("")),
                    Change::Removed => format!("removed {}", p.old.as_deref().unwrap_or("")),
                    Change::Modified => {
                        format!("renamed to {}", p.new.as_deref().unwrap_or(""))
                    }
                };
                (key, what)
            })
            .collect()
    };
    let (po, pt) = (players(&d_ours), players(&d_theirs));
    for name in po.keys().chain(pt.keys()).collect::<BTreeSet<_>>() {
        let (a, b) = (po.get(name), pt.get(name));
        let (outcome, side, reason) = match (a, b) {
            (Some(x), Some(y)) if x == y => (Outcome::Same, Side::Both, String::new()),
            (Some(_), Some(_)) => (Outcome::Conflict, Side::Both, "both versions changed this player differently".into()),
            (Some(_), None) => (Outcome::Auto, Side::Ours, String::new()),
            _ => (Outcome::Auto, Side::Theirs, String::new()),
        };
        items.push(Item {
            outcome,
            lane: Lane::Orchestration,
            side,
            flow: String::new(),
            owner: name.clone(),
            voice: String::new(),
            bar: String::new(),
            ours: a.cloned().into_iter().collect(),
            theirs: b.cloned().into_iter().collect(),
            reason,
        });
    }

    // --- settings (options; layouts are engraving) --------------------------------------
    for (lane, pick) in [
        (Lane::Settings, (|d: &ScoreDiff| d.options.clone()) as fn(&ScoreDiff) -> Vec<SettingChange>),
        (Lane::Engraving, |d: &ScoreDiff| d.layouts.clone()),
    ] {
        let as_map = |list: Vec<SettingChange>| -> BTreeMap<String, String> {
            list.into_iter()
                .map(|s| match s {
                    SettingChange::Value { path, old, new } => {
                        (path, format!("{} -> {}", old.unwrap_or_default(), new.unwrap_or_default()))
                    }
                    SettingChange::ItemAdded { path, name } => (path, format!("added {name}")),
                    SettingChange::ItemRemoved { path, name } => (path, format!("removed {name}")),
                })
                .collect()
        };
        let (so, st) = (as_map(pick(&d_ours)), as_map(pick(&d_theirs)));
        for path in so.keys().chain(st.keys()).collect::<BTreeSet<_>>() {
            let (a, b) = (so.get(path), st.get(path));
            let (outcome, side, reason) = match (a, b) {
                (Some(x), Some(y)) if x == y => (Outcome::Same, Side::Both, String::new()),
                (Some(_), Some(_)) => {
                    (Outcome::Conflict, Side::Both, "both versions changed this setting differently".into())
                }
                (Some(_), None) => (Outcome::Auto, Side::Ours, String::new()),
                _ => (Outcome::Auto, Side::Theirs, String::new()),
            };
            items.push(Item {
                outcome,
                lane,
                side,
                flow: String::new(),
                owner: path.clone(),
                voice: String::new(),
                bar: String::new(),
                ours: a.cloned().into_iter().collect(),
                theirs: b.cloned().into_iter().collect(),
                reason,
            });
        }
    }

    items.sort_by(|a, b| (a.outcome, &a.flow, a.lane, &a.owner).cmp(&(b.outcome, &b.flow, b.lane, &b.owner)));
    let mut counts = Counts::default();
    for i in &items {
        match i.outcome {
            Outcome::Conflict => counts.conflict += 1,
            Outcome::Review => counts.review += 1,
            Outcome::Auto => counts.auto += 1,
            Outcome::Same => counts.same += 1,
        }
    }
    Preview { items, structure, counts, integrity: Vec::new() }
}

/// Plain-text report (CLI).
pub fn render_text(p: &Preview, max_auto: usize) -> String {
    let mut out = String::new();
    let c = &p.counts;
    out.push_str(&format!(
        "Merge preview: {} conflict{}, {} to review, {} automatic, {} identical on both sides\n",
        c.conflict,
        if c.conflict == 1 { "" } else { "s" },
        c.review,
        c.auto,
        c.same
    ));
    for s in &p.structure {
        out.push_str(&format!("  structure ({:?}): {}: {}\n", s.side, s.flow, s.text));
    }
    for i in &p.integrity {
        out.push_str(&format!("  ! {i}\n"));
    }
    let mut autos = 0;
    for i in &p.items {
        if i.outcome == Outcome::Same {
            continue; // counted above; applied once
        }
        if i.outcome == Outcome::Auto {
            autos += 1;
            if autos > max_auto {
                continue;
            }
        }
        let place = [i.flow.as_str(), i.owner.as_str(), i.voice.as_str()]
            .iter()
            .filter(|s| !s.is_empty())
            .copied()
            .collect::<Vec<_>>()
            .join(" / ");
        let bar = if i.bar.is_empty() { String::new() } else { format!(" b.{}", i.bar) };
        out.push_str(&format!("\n[{:?}] {:?} · {place}{bar} ({:?})\n", i.outcome, i.lane, i.side));
        if !i.reason.is_empty() {
            out.push_str(&format!("    why: {}\n", i.reason));
        }
        for l in &i.ours {
            out.push_str(&format!("    ours:   {l}\n"));
        }
        for l in &i.theirs {
            out.push_str(&format!("    theirs: {l}\n"));
        }
    }
    if autos > max_auto {
        out.push_str(&format!("\n... and {} more automatic\n", autos - max_auto));
    }
    out
}
