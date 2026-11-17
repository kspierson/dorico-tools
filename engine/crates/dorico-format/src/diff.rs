//! Listings and musical diffs of scores.
//!
//! - [`listing`]: a stable, line-per-fact text form for `git diff` (textconv).
//!   Was byte-identical to the retired Python prototype's `listing()`.
//! - [`diff`]: a structured, ID-matched comparison for the app UI, with
//!   [`render_text`] for the terminal.

use crate::model::{Event, OrderedMap, Score};
use crate::ratio::Ratio;
use serde::Serialize;
use std::collections::{BTreeSet, HashMap};

const LISTING_INFO: &[&str] = &["subtitle", "composer", "arranger", "lyricist", "copyright"];
/// Info fields that change on every save and say nothing about the music.
pub const NOISY_INFO: &[&str] = &["lastSavedDate", "filePath", "lastSavedVersion", "originalSourcePath"];

fn is_structural(e: &Event) -> bool {
    e.kind == "time signature" || e.kind == "barline"
}

fn props_suffix(p: &[String], sep: &str) -> String {
    if p.is_empty() { String::new() } else { format!("{sep}{{{}}}", p.join("; ")) }
}

pub fn listing(score: &Score) -> String {
    let mut out: Vec<String> = Vec::new();
    let title = score.info("title");
    out.push(format!("# {}", if title.is_empty() { "(untitled)" } else { title }));
    for k in LISTING_INFO {
        let v = score.info(k);
        if !v.is_empty() {
            out.push(format!("#   {k}: {v}"));
        }
    }
    out.push(format!("#   created with Dorico {}", score.info.get("createdVersion").unwrap_or("?")));
    out.push(String::new());
    out.push("## Players".into());
    for (_, name) in &score.players {
        out.push(format!("  {name}"));
    }
    for flow in &score.flows {
        out.push(String::new());
        out.push(format!("## Flow: {}", flow.name));
        let meters: Vec<String> = flow.meters.iter().map(|m| format!("{} @ bar {}", m.label, m.bar)).collect();
        out.push(format!("   meters: {}", meters.join(", ")));
        if let Some(v) = &flow.video {
            out.push(format!("   video: {v}"));
        }
        let mut last: Option<(&str, &str)> = None;
        for ev in flow.events.iter().filter(|e| !is_structural(e)) {
            let head = (ev.owner.as_str(), ev.lane.as_str());
            if last != Some(head) {
                let lane = if ev.lane.is_empty() { String::new() } else { format!(" [{}]", ev.lane) };
                out.push(format!("### {} > {}{lane}", flow.name, ev.owner));
                last = Some(head);
            }
            out.push(format!("  {:<16} {} {}{}", ev.where_, ev.kind, ev.text, props_suffix(&ev.props, "  ")));
        }
    }
    for (title, map) in [("Score options", &score.options), ("Layout settings", &score.layouts)] {
        out.push(String::new());
        out.push(format!("## {title}"));
        let mut items: Vec<(&str, &str)> = map.iter().collect();
        items.sort();
        for (k, v) in items {
            out.push(format!("  {k} = {v}"));
        }
    }
    out.push(String::new());
    out.join("\n")
}

// ---------------------------------------------------------------------------
// Structured diff
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum Change {
    Added,
    Removed,
    Modified,
}

#[derive(Debug, Clone, Serialize)]
pub struct FieldChange {
    pub key: String,
    pub old: String,
    pub new: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct PlayerChange {
    pub change: Change,
    pub old: Option<String>,
    pub new: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct EventChange {
    pub change: Change,
    pub owner: String,
    pub lane: String,
    pub kind: String,
    #[serde(rename = "where")]
    pub where_: String,
    pub bar: Option<i128>,
    pub position: Ratio,
    /// what the event is (new version for added/modified, old for removed)
    pub text: String,
    /// for modified events: human-readable list of what changed
    pub details: Vec<String>,
    pub props: Vec<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct OwnerChanges {
    pub owner: String,
    pub changes: Vec<EventChange>,
}

#[derive(Debug, Clone, Serialize)]
pub struct FlowDiff {
    pub flow_id: String,
    pub name: String,
    pub old_name: Option<String>,
    pub change: Change,
    pub meters: Option<(Vec<String>, Vec<String>)>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub video: Option<(String, String)>,
    pub owners: Vec<OwnerChanges>,
    pub total: usize,
}

#[derive(Debug, Clone, Serialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum SettingChange {
    Value { path: String, old: Option<String>, new: Option<String> },
    ItemAdded { path: String, name: String },
    ItemRemoved { path: String, name: String },
}

#[derive(Debug, Clone, Serialize)]
pub struct ScoreDiff {
    pub old_title: String,
    pub new_title: String,
    pub old_saved: Option<i64>,
    pub new_saved: Option<i64>,
    pub info: Vec<FieldChange>,
    pub players: Vec<PlayerChange>,
    pub flows: Vec<FlowDiff>,
    pub options: Vec<SettingChange>,
    pub layouts: Vec<SettingChange>,
}

impl ScoreDiff {
    /// Number of musical changes (events, players, flows, info).
    pub fn music_changes(&self) -> usize {
        self.info.len()
            + self.players.len()
            + self.flows.iter().map(|f| if f.change == Change::Modified { f.total } else { 1 }).sum::<usize>()
    }
    pub fn setting_changes(&self) -> usize {
        self.options.len() + self.layouts.len()
    }
    pub fn is_empty(&self) -> bool {
        self.music_changes() == 0 && self.setting_changes() == 0
    }
    /// One-line summary, e.g. "12 note changes in 3 players; 2 option changes".
    pub fn summary(&self) -> String {
        let mut parts = Vec::new();
        let events: usize = self.flows.iter().filter(|f| f.change == Change::Modified).map(|f| f.total).sum();
        if events > 0 {
            let owners: BTreeSet<&str> =
                self.flows.iter().flat_map(|f| f.owners.iter().map(|o| o.owner.as_str())).collect();
            parts.push(format!("{events} change{} in {} part{}", plural(events), owners.len(), plural(owners.len())));
        }
        let added = self.flows.iter().filter(|f| f.change == Change::Added).count();
        let removed = self.flows.iter().filter(|f| f.change == Change::Removed).count();
        if added > 0 {
            parts.push(format!("{added} flow{} added", plural(added)));
        }
        if removed > 0 {
            parts.push(format!("{removed} flow{} removed", plural(removed)));
        }
        if !self.players.is_empty() {
            parts.push(format!("{} player change{}", self.players.len(), plural(self.players.len())));
        }
        if !self.info.is_empty() {
            parts.push("project info".into());
        }
        let s = self.setting_changes();
        if s > 0 {
            parts.push(format!("{s} setting{}", plural(s)));
        }
        if parts.is_empty() { "no musical changes".into() } else { parts.join("; ") }
    }
}

fn plural(n: usize) -> &'static str {
    if n == 1 { "" } else { "s" }
}

pub fn diff(a: &Score, b: &Score) -> ScoreDiff {
    let mut info = Vec::new();
    let keys: BTreeSet<&str> = a.info.keys().chain(b.info.keys()).collect();
    for k in keys {
        if NOISY_INFO.contains(&k) {
            continue;
        }
        let (va, vb) = (a.info(k), b.info(k));
        if va != vb {
            info.push(FieldChange { key: k.into(), old: va.into(), new: vb.into() });
        }
    }

    let mut players = Vec::new();
    let mut ids: Vec<&str> = Vec::new();
    for (id, _) in a.players.iter().chain(&b.players) {
        if !ids.contains(&id.as_str()) {
            ids.push(id);
        }
    }
    for id in ids {
        match (a.player_name(id), b.player_name(id)) {
            (None, Some(n)) => players.push(PlayerChange { change: Change::Added, old: None, new: Some(n.into()) }),
            (Some(o), None) => players.push(PlayerChange { change: Change::Removed, old: Some(o.into()), new: None }),
            (Some(o), Some(n)) if o != n => {
                players.push(PlayerChange { change: Change::Modified, old: Some(o.into()), new: Some(n.into()) })
            }
            _ => {}
        }
    }

    let order: HashMap<&str, i64> = b.players.iter().enumerate().map(|(i, (_, n))| (n.as_str(), i as i64)).collect();
    let mut flows = Vec::new();
    let mut flow_ids: Vec<&str> = Vec::new();
    for f in a.flows.iter().chain(&b.flows) {
        if !flow_ids.contains(&f.flow_id.as_str()) {
            flow_ids.push(&f.flow_id);
        }
    }
    for fid in flow_ids {
        let fa = a.flows.iter().find(|f| f.flow_id == fid);
        let fb = b.flows.iter().find(|f| f.flow_id == fid);
        match (fa, fb) {
            (None, Some(f)) => flows.push(FlowDiff {
                flow_id: fid.into(),
                name: f.name.clone(),
                old_name: None,
                change: Change::Added,
                meters: None,
                video: None,
                owners: Vec::new(),
                total: f.events.len(),
            }),
            (Some(f), None) => flows.push(FlowDiff {
                flow_id: fid.into(),
                name: f.name.clone(),
                old_name: None,
                change: Change::Removed,
                meters: None,
                video: None,
                owners: Vec::new(),
                total: f.events.len(),
            }),
            (Some(fa), Some(fb)) => {
                let changes = event_changes(&fa.events, &fb.events, &order);
                let ma: Vec<String> = fa.meters.iter().map(|m| m.label.clone()).collect();
                let mb: Vec<String> = fb.meters.iter().map(|m| m.label.clone()).collect();
                let meters = (ma != mb).then_some((ma, mb));
                let none = || "none".to_owned();
                let video = (fa.video != fb.video)
                    .then(|| (fa.video.clone().unwrap_or_else(none), fb.video.clone().unwrap_or_else(none)));
                if changes.is_empty() && meters.is_none() && video.is_none() && fa.name == fb.name {
                    continue;
                }
                let total = changes.len();
                let mut owners: Vec<OwnerChanges> = Vec::new();
                for c in changes {
                    match owners.iter_mut().find(|o| o.owner == c.owner) {
                        Some(o) => o.changes.push(c),
                        None => owners.push(OwnerChanges { owner: c.owner.clone(), changes: vec![c] }),
                    }
                }
                flows.push(FlowDiff {
                    flow_id: fid.into(),
                    name: fb.name.clone(),
                    old_name: (fa.name != fb.name).then(|| fa.name.clone()),
                    change: Change::Modified,
                    meters,
                    video,
                    owners,
                    total,
                });
            }
            (None, None) => unreachable!(),
        }
    }

    ScoreDiff {
        old_title: a.info("title").into(),
        new_title: b.info("title").into(),
        old_saved: a.info("lastSavedDate").parse().ok(),
        new_saved: b.info("lastSavedDate").parse().ok(),
        info,
        players,
        flows,
        options: setting_changes(&a.options, &b.options),
        layouts: setting_changes(&a.layouts, &b.layouts),
    }
}

fn event_changes(ea: &[Event], eb: &[Event], order: &HashMap<&str, i64>) -> Vec<EventChange> {
    let mut ma: HashMap<&str, &Event> =
        ea.iter().filter(|e| !is_structural(e)).map(|e| (e.event_id.as_str(), e)).collect();
    let mut mb: HashMap<&str, &Event> =
        eb.iter().filter(|e| !is_structural(e)).map(|e| (e.event_id.as_str(), e)).collect();

    // An item deleted and re-entered identically gets a new ID: not a change.
    type Sig<'a> = (&'a str, &'a str, &'a str, Ratio, &'a str, &'a [String]);
    fn sig(e: &Event) -> Sig<'_> {
        (&e.owner, &e.lane, &e.kind, e.position, &e.text, &e.props)
    }
    let mut only_a: Vec<&str> = ma.keys().filter(|k| !mb.contains_key(*k)).copied().collect();
    let mut only_b: Vec<&str> = mb.keys().filter(|k| !ma.contains_key(*k)).copied().collect();
    only_a.sort();
    only_b.sort();
    let mut pool: HashMap<Sig, Vec<&str>> = HashMap::new();
    for id in &only_b {
        pool.entry(sig(mb[id])).or_default().push(id);
    }
    for id in only_a {
        if let Some(twin) = pool.get_mut(&sig(ma[id])).and_then(Vec::pop) {
            mb.remove(twin);
            ma.remove(id);
        }
    }

    let mut ids: Vec<&str> = ma.keys().chain(mb.keys()).copied().collect::<BTreeSet<_>>().into_iter().collect();
    ids.sort();
    let mut rows = Vec::new();
    for id in ids {
        let mk = |change, e: &Event, details: Vec<String>| EventChange {
            change,
            owner: e.owner.clone(),
            lane: e.lane.clone(),
            kind: e.kind.clone(),
            where_: e.where_.clone(),
            bar: e.bar,
            position: e.position,
            text: e.text.clone(),
            details,
            props: e.props.clone(),
        };
        match (ma.get(id), mb.get(id)) {
            (None, Some(y)) => rows.push(mk(Change::Added, y, Vec::new())),
            (Some(x), None) => rows.push(mk(Change::Removed, x, Vec::new())),
            (Some(x), Some(y)) => {
                let mut bits = Vec::new();
                if x.owner != y.owner || x.lane != y.lane {
                    bits.push(format!("moved {} {} -> {} {}", x.owner, x.lane, y.owner, y.lane).trim().to_owned());
                }
                if x.position != y.position {
                    bits.push(format!("moved {} -> {}", x.where_, y.where_));
                }
                if x.text != y.text {
                    bits.push(format!("{} -> {}", x.text, y.text));
                }
                let gone: Vec<&str> = x.props.iter().filter(|p| !y.props.contains(p)).map(String::as_str).collect();
                let new: Vec<&str> = y.props.iter().filter(|p| !x.props.contains(p)).map(String::as_str).collect();
                if !gone.is_empty() {
                    bits.push(format!("removed {}", gone.join("; ")));
                }
                if !new.is_empty() {
                    bits.push(format!("added {}", new.join("; ")));
                }
                if !bits.is_empty() {
                    let mut row = mk(Change::Modified, y, bits);
                    if x.text != y.text {
                        row.text = String::new();
                    }
                    rows.push(row);
                }
            }
            (None, None) => {}
        }
    }
    rows.sort_by(|p, q| {
        let rank = |r: &EventChange| order.get(r.owner.as_str()).copied().unwrap_or(-1);
        (rank(p), p.position, &p.lane, &p.kind, &p.text).cmp(&(rank(q), q.position, &q.lane, &q.kind, &q.text))
    });
    rows
}

/// Changed settings; whole added/removed array items are reported once.
fn setting_changes(da: &OrderedMap, db: &OrderedMap) -> Vec<SettingChange> {
    fn prefixes(path: &str) -> Vec<String> {
        let parts: Vec<&str> = path.split('/').collect();
        let mut out = Vec::new();
        for (i, p) in parts.iter().enumerate() {
            if p.ends_with(']') {
                out.push(parts[..=i].join("/"));
            }
        }
        out
    }
    let items = |d: &OrderedMap| -> BTreeSet<String> { d.keys().flat_map(prefixes).collect() };
    let (ia, ib) = (items(da), items(db));
    let keys: BTreeSet<&str> = da.keys().chain(db.keys()).collect();
    let mut out = Vec::new();
    let mut reported: BTreeSet<String> = BTreeSet::new();
    for k in keys {
        let (va, vb) = (da.get(k), db.get(k));
        if va == vb {
            continue;
        }
        let whole = prefixes(k).into_iter().find(|p| ia.contains(p) != ib.contains(p));
        if let Some(whole) = whole {
            if reported.insert(whole.clone()) {
                let in_a = ia.contains(&whole);
                let side = if in_a { da } else { db };
                let name = side
                    .iter()
                    .find(|(x, _)| x.starts_with(&format!("{whole}/")) && x.ends_with("Name"))
                    .map(|(_, v)| v.to_owned())
                    .unwrap_or_default();
                out.push(if in_a {
                    SettingChange::ItemRemoved { path: whole, name }
                } else {
                    SettingChange::ItemAdded { path: whole, name }
                });
            }
            continue;
        }
        out.push(SettingChange::Value { path: k.into(), old: va.map(Into::into), new: vb.map(Into::into) });
    }
    out
}

// ---------------------------------------------------------------------------
// Text rendering
// ---------------------------------------------------------------------------

fn fmt_date(ts: Option<i64>) -> String {
    match ts {
        // UTC; the app formats in local time
        Some(t) => {
            let days = t.div_euclid(86_400);
            let secs = t.rem_euclid(86_400);
            let (y, m, d) = civil_from_days(days);
            format!("{y:04}-{m:02}-{d:02} {:02}:{:02} UTC", secs / 3600, secs % 3600 / 60)
        }
        None => "?".into(),
    }
}

/// Days since 1970-01-01 -> (year, month, day). Howard Hinnant's algorithm.
fn civil_from_days(z: i64) -> (i64, u32, u32) {
    let z = z + 719_468;
    let era = z.div_euclid(146_097);
    let doe = z.rem_euclid(146_097);
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = (doy - (153 * mp + 2) / 5 + 1) as u32;
    let m = if mp < 10 { mp + 3 } else { mp - 9 } as u32;
    (yoe + era * 400 + i64::from(m <= 2), m, d)
}

pub fn render_text(d: &ScoreDiff, max_per_owner: usize, max_settings: usize) -> String {
    let mut out = vec![format!(
        "Comparing '{}' (saved {}) -> '{}' (saved {})",
        d.old_title,
        fmt_date(d.old_saved),
        d.new_title,
        fmt_date(d.new_saved)
    )];
    for c in &d.info {
        out.push(format!("  info: {}: {:?} -> {:?}", c.key, c.old, c.new));
    }
    for p in &d.players {
        out.push(match p.change {
            Change::Added => format!("  + player added: {}", p.new.as_deref().unwrap_or("")),
            Change::Removed => format!("  - player removed: {}", p.old.as_deref().unwrap_or("")),
            Change::Modified => {
                format!("  ~ player renamed: {} -> {}", p.old.as_deref().unwrap_or(""), p.new.as_deref().unwrap_or(""))
            }
        });
    }
    for f in &d.flows {
        match f.change {
            Change::Added => out.push(format!("\n+ Flow added: {} ({} events)", f.name, f.total)),
            Change::Removed => out.push(format!("\n- Flow removed: {}", f.name)),
            Change::Modified => {
                let title = match &f.old_name {
                    Some(o) => format!("{o} -> {}", f.name),
                    None => f.name.clone(),
                };
                out.push(format!("\nFlow: {title}  ({} change{})", f.total, plural(f.total)));
                if let Some((ma, mb)) = &f.meters {
                    out.push(format!("  ~ meters: {} -> {}", ma.join(", "), mb.join(", ")));
                }
                if let Some((va, vb)) = &f.video {
                    out.push(format!("  ~ video: {va}\n        -> {vb}"));
                }
                for o in &f.owners {
                    out.push(format!("  {}", o.owner));
                    for c in o.changes.iter().take(max_per_owner) {
                        out.push(format!("    {}", event_line(c)));
                    }
                    if o.changes.len() > max_per_owner {
                        out.push(format!("    ... and {} more", o.changes.len() - max_per_owner));
                    }
                }
            }
        }
    }
    for (label, list) in [("Score options", &d.options), ("Layout settings", &d.layouts)] {
        if list.is_empty() {
            continue;
        }
        out.push(format!("\n{label}: {} change{}", list.len(), plural(list.len())));
        for s in list.iter().take(max_settings) {
            out.push(format!("  {}", setting_line(s)));
        }
        if list.len() > max_settings {
            out.push(format!("  ... and {} more", list.len() - max_settings));
        }
    }
    if out.len() == 1 {
        out.push("No musical changes found (only save metadata differs).".into());
    }
    out.join("\n") + "\n"
}

pub fn event_line(c: &EventChange) -> String {
    let lane = if c.lane.is_empty() { String::new() } else { format!(" [{}]", c.lane) };
    match c.change {
        Change::Added => format!("+ {}{lane} added {} {}{}", c.where_, c.kind, c.text, props_suffix(&c.props, " ")),
        Change::Removed => format!("- {}{lane} removed {} {}{}", c.where_, c.kind, c.text, props_suffix(&c.props, " ")),
        Change::Modified => {
            let what = if c.text.is_empty() { c.kind.clone() } else { format!("{} {}", c.kind, c.text) };
            format!("~ {}{lane} {what}: {}", c.where_, c.details.join(", "))
        }
    }
}

pub fn setting_line(s: &SettingChange) -> String {
    match s {
        SettingChange::Value { path, old, new } => {
            format!("{path}: {} -> {}", old.as_deref().unwrap_or("(none)"), new.as_deref().unwrap_or("(none)"))
        }
        SettingChange::ItemAdded { path, name } => {
            format!("+ added {path}{}", if name.is_empty() { String::new() } else { format!(" ({name})") })
        }
        SettingChange::ItemRemoved { path, name } => {
            format!("- removed {path}{}", if name.is_empty() { String::new() } else { format!(" ({name})") })
        }
    }
}
