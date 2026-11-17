//! dorigit's diff: the shared diff (`dorico_format::diff`) with two kinds of noise removed.
//!
//! 1. **Player renames.** The shared diff matches events by player name, so renaming a player
//!    (or Dorico 5 writing "B{@flat@}" where Dorico 4 wrote "B Flat") makes every one of its
//!    notes look "moved". The rename is reported once (in `players`); event changes whose only
//!    difference is that move are dropped.
//! 2. **Re-saved in a newer Dorico** (STATUS B11, from the Rite of Spring 4.3 vs 5.1 saves).
//!    When the newer version was saved by a newer Dorico (major.minor), format-only changes are
//!    hidden: options/layout values that appear or disappear (new defaults), new info fields
//!    (`originator`, `resolveMarkdown`), `EventMuted` true -> kAlways, and the glissando
//!    playback type Dorico 5 adds. One info line replaces them:
//!    "Re-saved in Dorico: 4.3.30 -> 5.1.60 (N format-only changes hidden)".
//!
//! Real musical changes made in the same save are kept.

use dorico_format::Score;
use dorico_format::diff::{self, Change, FieldChange, ScoreDiff, SettingChange};

pub const RESAVED_KEY: &str = "Re-saved in Dorico";

/// Diff two listings and tidy the result (see the module docs).
pub fn diff(a: &Score, b: &Score) -> ScoreDiff {
    let mut d = diff::diff(a, b);
    let old = a.info.get("lastSavedVersion").unwrap_or("");
    let new = b.info.get("lastSavedVersion").unwrap_or("");
    tidy(&mut d, old, new);
    d
}

/// "5.1.60" -> (5, 1).
fn major_minor(v: &str) -> Option<(u32, u32)> {
    let mut it = v.split('.');
    Some((it.next()?.trim().parse().ok()?, it.next()?.trim().parse().ok()?))
}

/// Event-detail bits that a newer Dorico writes on its own.
fn upgrade_bit(bit: &str) -> bool {
    matches!(
        bit,
        "removed EventMuted=true" | "added EventMuted=kAlways" | "added GlissandoPlaybackType=kChromatic"
    )
}

pub fn tidy(d: &mut ScoreDiff, old_version: &str, new_version: &str) {
    let upgraded = match (major_minor(old_version), major_minor(new_version)) {
        (Some(a), Some(b)) => b > a,
        _ => false,
    };
    let renames: Vec<(String, String)> = d
        .players
        .iter()
        .filter(|p| p.change == Change::Modified)
        .filter_map(|p| Some((p.old.clone()?, p.new.clone()?)))
        .collect();
    let mut hidden = 0usize;

    for f in &mut d.flows {
        for o in &mut f.owners {
            o.changes.retain_mut(|c| {
                if c.change != Change::Modified {
                    return true;
                }
                let lane = c.lane.clone();
                c.details.retain(|bit| {
                    let rename = renames
                        .iter()
                        .any(|(old, new)| *bit == format!("moved {old} {lane} -> {new} {lane}").trim());
                    let upgrade = upgraded && upgrade_bit(bit);
                    if upgrade && !rename {
                        hidden += 1;
                    }
                    !rename && !upgrade
                });
                !c.details.is_empty()
            });
        }
        f.owners.retain(|o| !o.changes.is_empty());
        if f.change == Change::Modified {
            f.total = f.owners.iter().map(|o| o.changes.len()).sum();
        }
    }
    d.flows.retain(|f| {
        f.change != Change::Modified || f.total > 0 || f.meters.is_some() || f.video.is_some() || f.old_name.is_some()
    });

    if upgraded {
        let new_default = |s: &SettingChange| matches!(s, SettingChange::Value { old: None, .. } | SettingChange::Value { new: None, .. });
        for list in [&mut d.options, &mut d.layouts] {
            let before = list.len();
            list.retain(|s| !new_default(s));
            hidden += before - list.len();
        }
        let before = d.info.len();
        d.info.retain(|i| !(i.old.is_empty() && matches!(i.key.as_str(), "originator" | "resolveMarkdown")));
        hidden += before - d.info.len();
        d.info.push(FieldChange {
            key: RESAVED_KEY.to_owned(),
            old: old_version.to_owned(),
            new: format!(
                "{new_version} ({hidden} format-only change{} hidden)",
                if hidden == 1 { "" } else { "s" }
            ),
        });
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use dorico_format::diff::{EventChange, FlowDiff, OwnerChanges, PlayerChange};
    use dorico_format::ratio::Ratio;

    fn change(details: &[&str], lane: &str) -> EventChange {
        EventChange {
            change: Change::Modified,
            owner: "Clarinet (B{@flat@})".into(),
            lane: lane.into(),
            kind: "note".into(),
            where_: "bar 1 beat 1".into(),
            bar: Some(1),
            position: Ratio::ZERO,
            text: "C4 crotchet".into(),
            details: details.iter().map(|s| s.to_string()).collect(),
            props: vec![],
        }
    }

    fn sample() -> ScoreDiff {
        ScoreDiff {
            old_title: String::new(),
            new_title: String::new(),
            old_saved: None,
            new_saved: None,
            info: vec![FieldChange { key: "originator".into(), old: String::new(), new: "kDorico".into() }],
            players: vec![PlayerChange {
                change: Change::Modified,
                old: Some("Clarinet (B Flat)".into()),
                new: Some("Clarinet (B{@flat@})".into()),
            }],
            flows: vec![FlowDiff {
                flow_id: "0".into(),
                name: "1m1".into(),
                old_name: None,
                change: Change::Modified,
                meters: None,
                video: None,
                owners: vec![OwnerChanges {
                    owner: "Clarinet (B{@flat@})".into(),
                    changes: vec![
                        // only renamed: dropped
                        change(&["moved Clarinet (B Flat) voice 1 -> Clarinet (B{@flat@}) voice 1"], "voice 1"),
                        // renamed and the pitch changed: kept, without the move
                        change(
                            &["moved Clarinet (B Flat) voice 1 -> Clarinet (B{@flat@}) voice 1", "C4 crotchet -> D4 crotchet"],
                            "voice 1",
                        ),
                        // upgrade-only
                        change(&["removed EventMuted=true", "added EventMuted=kAlways"], "voice 1"),
                    ],
                }],
                total: 3,
            }],
            options: vec![
                SettingChange::Value { path: "a/new".into(), old: None, new: Some("true".into()) },
                SettingChange::Value { path: "a/changed".into(), old: Some("1".into()), new: Some("2".into()) },
            ],
            layouts: vec![],
        }
    }

    #[test]
    fn renames_are_not_moves() {
        let mut d = sample();
        tidy(&mut d, "5.1.60", "5.1.60"); // same version: only the rename tidy applies
        let c = &d.flows[0].owners[0].changes;
        assert_eq!(c.len(), 2);
        assert_eq!(c[0].details, vec!["C4 crotchet -> D4 crotchet"]);
        assert_eq!(d.flows[0].total, 2);
        assert_eq!(d.options.len(), 2);
        assert!(d.info.iter().all(|i| i.key != RESAVED_KEY));
    }

    #[test]
    fn newer_dorico_hides_format_only_changes() {
        let mut d = sample();
        tidy(&mut d, "4.3.30", "5.1.60");
        assert_eq!(d.flows[0].total, 1, "only the real pitch change is left");
        assert_eq!(d.options.len(), 1, "the changed value stays, the new default goes");
        let line = d.info.iter().find(|i| i.key == RESAVED_KEY).unwrap();
        assert_eq!(line.old, "4.3.30");
        assert_eq!(line.new, "5.1.60 (4 format-only changes hidden)");
        assert_eq!(d.info.len(), 1, "originator hidden");
    }

    #[test]
    fn older_or_unknown_versions_change_nothing() {
        let mut d = sample();
        tidy(&mut d, "5.1.60", "4.3.30");
        assert_eq!(d.options.len(), 2);
        let mut d = sample();
        tidy(&mut d, "", "5.1.60");
        assert_eq!(d.options.len(), 2);
    }
}
