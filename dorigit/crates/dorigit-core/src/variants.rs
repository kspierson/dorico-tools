//! Variants (MERGE.md §3): named alternatives of a cue, e.g. "1m3 Chase [horns].dorico".
//!
//! - **Making one** copies the cue byte for byte next to it and starts the copy's history at
//!   the cue's latest snapshot, so the variant's branch forks from the main version.
//! - **Variant info** (name, optional bar range, notes, tags) is stored *in the history*: the
//!   family repository's `refs/dorigit/variants` points at a commit whose tree holds
//!   `variants.json`. It travels with push/fetch (SYNC.md) and backups. Each change is a new
//!   commit, so the info has its own history too.
//! - **The board** shows, per variant, the bars where it differs from the point it branched
//!   off (the merge base with its main version), and how much the main version has moved since.
//!
//! User choices (2026-10-31): files next to the cue; the section is both given (optional range)
//! and detected (always); notes travel with the history.

use crate::lock::lock_family;
use crate::manifest::SnapshotKind;
use crate::store::{SnapshotOutcome, Store, path_key};
use anyhow::{Context, Result, bail};
use dorico_format::diff::ScoreDiff;
use git2::{Oid, Repository, Signature};
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::{Path, PathBuf};

pub const VARIANTS_REF: &str = "refs/dorigit/variants";
const VARIANTS_FILE: &str = "variants.json";

/// Bars a variant is meant to be about, as you'd say them ("17"-"32", optionally in one flow).
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct BarRange {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub flow: Option<String>,
    pub from: String,
    pub to: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Variant {
    /// The variant file's branch (stable id).
    pub branch: String,
    /// What you called it: "horns".
    pub name: String,
    pub file_name: String,
    /// Branch of the version it was made from.
    pub base_branch: String,
    /// Snapshot it was made from.
    pub base_snapshot: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub bars: Option<BarRange>,
    #[serde(default)]
    pub notes: String,
    #[serde(default)]
    pub tags: Vec<String>,
    /// Unix seconds.
    pub created: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
struct VariantFile {
    variants: Vec<Variant>,
}

/// A run of bars where a variant differs, within one flow.
#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct DiffRange {
    pub from: String,
    pub to: String,
    pub changes: usize,
    /// Players touched, in score order.
    pub players: Vec<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct FlowRanges {
    pub flow: String,
    pub ranges: Vec<DiffRange>,
}

#[derive(Debug, Clone, Serialize)]
pub struct VariantStatus {
    pub variant: Variant,
    /// The variant's latest snapshot (None if its branch is missing).
    pub tip: Option<String>,
    /// Where that snapshot's file was (to open it in Dorico).
    pub path: Option<String>,
    /// Where it branched off its main version (merge base).
    pub fork_point: Option<String>,
    /// The main version's latest snapshot (for a merge preview).
    pub main_tip: Option<String>,
    /// Bars that differ from the fork point, per flow (detected).
    pub differs: Vec<FlowRanges>,
    pub music_changes: usize,
    /// Musical changes on the main version since the fork point.
    pub main_changes_since: usize,
    /// Detected bars outside the given range, e.g. ["Flow 1 b.40-41"].
    pub outside_range: Vec<String>,
}

/// Group a diff's musical changes into bar ranges per flow (adjacent bars merge).
pub fn ranges(d: &ScoreDiff) -> Vec<FlowRanges> {
    let mut out = Vec::new();
    for f in &d.flows {
        let mut changes: Vec<(&dorico_format::diff::EventChange, &str)> = Vec::new();
        for o in &f.owners {
            for c in &o.changes {
                changes.push((c, o.owner.as_str()));
            }
        }
        changes.sort_by_key(|(c, _)| c.position);
        let mut ranges: Vec<(i128, DiffRange)> = Vec::new();
        for (c, owner) in changes {
            let label = bar_label(&c.where_);
            let num = c.bar.unwrap_or(i128::MIN);
            match ranges.last_mut() {
                Some((last, r)) if c.bar.is_some() && num - *last <= 1 => {
                    *last = num;
                    r.to = label;
                    r.changes += 1;
                    if !r.players.iter().any(|p| p == owner) {
                        r.players.push(owner.to_owned());
                    }
                }
                _ => ranges.push((
                    num,
                    DiffRange { from: label.clone(), to: label, changes: 1, players: vec![owner.to_owned()] },
                )),
            }
        }
        if !ranges.is_empty() {
            out.push(FlowRanges { flow: f.name.clone(), ranges: ranges.into_iter().map(|(_, r)| r).collect() });
        }
    }
    out
}

/// "bar 35a beat 2+1/2" -> "35a"; anything else as is.
fn bar_label(where_: &str) -> String {
    where_.strip_prefix("bar ").and_then(|r| r.split(' ').next()).unwrap_or(where_).to_owned()
}

/// Leading number of a bar label ("35a" -> 35).
fn bar_number(label: &str) -> Option<i64> {
    let digits: String = label.chars().take_while(|c| c.is_ascii_digit()).collect();
    digits.parse().ok()
}

fn outside(range: &BarRange, detected: &[FlowRanges]) -> Vec<String> {
    let (Some(lo), Some(hi)) = (bar_number(&range.from), bar_number(&range.to)) else { return Vec::new() };
    let mut out = Vec::new();
    for f in detected {
        let same_flow = range.flow.as_deref().is_none_or(|n| n == f.flow);
        for r in &f.ranges {
            let (a, b) = (bar_number(&r.from).unwrap_or(lo), bar_number(&r.to).unwrap_or(hi));
            if !same_flow || a < lo || b > hi {
                let bars = if r.from == r.to { format!("b.{}", r.from) } else { format!("b.{}-{}", r.from, r.to) };
                out.push(format!("{} {bars}", f.flow));
            }
        }
    }
    out
}

/// "1m3 Chase.dorico" + "horns" -> "1m3 Chase [horns].dorico" beside it.
pub fn variant_path(main: &Path, name: &str) -> PathBuf {
    let stem = main.file_stem().map(|s| s.to_string_lossy().to_string()).unwrap_or_default();
    main.with_file_name(format!("{stem} [{name}].dorico"))
}

fn check_name(name: &str) -> Result<()> {
    let name = name.trim();
    if name.is_empty() {
        bail!("a variant needs a name");
    }
    if let Some(c) = name.chars().find(|c| r#"/\:*?"<>|[]"#.contains(*c) || c.is_control()) {
        bail!("a variant name can't contain '{c}'");
    }
    Ok(())
}

fn read_variants(repo: &Repository) -> Result<(VariantFile, Option<Oid>)> {
    let Ok(id) = repo.refname_to_id(VARIANTS_REF) else { return Ok((VariantFile::default(), None)) };
    let commit = repo.find_commit(id)?;
    let bytes = crate::store::read_path(repo, &commit.tree()?, VARIANTS_FILE)?;
    Ok((serde_json::from_slice(&bytes).context("reading variants.json")?, Some(id)))
}

fn write_variants(repo: &Repository, file: &VariantFile, parent: Option<Oid>, message: &str) -> Result<()> {
    let blob = repo.blob(&serde_json::to_vec_pretty(file)?)?;
    let mut tb = repo.treebuilder(None)?;
    tb.insert(VARIANTS_FILE, blob, 0o100644)?;
    let tree = repo.find_tree(tb.write()?)?;
    let sig = Signature::now("dorigit", "dorigit@localhost")?;
    let parent = parent.map(|p| repo.find_commit(p)).transpose()?;
    let parents: Vec<&git2::Commit> = parent.iter().collect();
    let id = repo.commit(None, &sig, &sig, message, &tree, &parents)?;
    repo.reference(VARIANTS_REF, id, true, message)?;
    Ok(())
}

impl Store {
    /// Make a variant of `main`: copy it to "<stem> [<name>].dorico" beside it, start its
    /// history at `main`'s latest snapshot and record the variant. Never overwrites.
    pub fn new_variant(&self, main: &Path, name: &str, bars: Option<BarRange>) -> Result<(PathBuf, Variant)> {
        check_name(name)?;
        let name = name.trim();
        let dest = variant_path(main, name);
        if dest.exists() {
            bail!("{} already exists", dest.display());
        }
        // make sure the main version's latest state is in the history
        let (family, base) = match self.snapshot_file(main, SnapshotKind::Manual, None)? {
            SnapshotOutcome::Created { snapshot } => (snapshot.family, snapshot.id),
            SnapshotOutcome::Unchanged { family, id } => (family, id),
        };
        let base_branch = self.load_family(&family)?.files.get(&path_key(main)).cloned().context("main file has no branch")?;

        fs::copy(main, &dest).with_context(|| format!("writing {}", dest.display()))?;
        {
            let _lock = lock_family(&self.repo_dir(&family), self.lock_timeout)?;
            let mut meta = self.load_family(&family)?;
            meta.pending_forks.insert(path_key(&dest), base.clone());
            self.save_family(&meta)?;
        }
        // identical content: the variant's branch simply starts at the main version's snapshot
        self.snapshot_file(&dest, SnapshotKind::Manual, None)?;
        let branch = self.load_family(&family)?.files.get(&path_key(&dest)).cloned().context("variant has no branch")?;

        let variant = Variant {
            branch,
            name: name.to_owned(),
            file_name: dest.file_name().map(|s| s.to_string_lossy().to_string()).unwrap_or_default(),
            base_branch,
            base_snapshot: base,
            bars,
            notes: String::new(),
            tags: Vec::new(),
            created: std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.as_secs() as i64)
                .unwrap_or(0),
        };
        let _lock = lock_family(&self.repo_dir(&family), self.lock_timeout)?;
        let repo = self.repo(&family)?;
        let (mut file, parent) = read_variants(&repo)?;
        file.variants.retain(|v| v.branch != variant.branch);
        file.variants.push(variant.clone());
        write_variants(&repo, &file, parent, &format!("variant \"{name}\" of {}", variant.base_branch))?;
        Ok((dest, variant))
    }

    /// All variants recorded in a family.
    pub fn variants(&self, family: &str) -> Result<Vec<Variant>> {
        Ok(read_variants(&self.repo(family)?)?.0.variants)
    }

    /// Change a variant's name, range, notes or tags (`None` = keep).
    pub fn update_variant(
        &self,
        family: &str,
        branch: &str,
        name: Option<&str>,
        bars: Option<Option<BarRange>>,
        notes: Option<&str>,
        tags: Option<Vec<String>>,
    ) -> Result<Variant> {
        if let Some(n) = name {
            check_name(n)?;
        }
        let _lock = lock_family(&self.repo_dir(family), self.lock_timeout)?;
        let repo = self.repo(family)?;
        let (mut file, parent) = read_variants(&repo)?;
        let v = file.variants.iter_mut().find(|v| v.branch == branch).context("no such variant")?;
        if let Some(n) = name {
            v.name = n.trim().to_owned();
        }
        if let Some(b) = bars {
            v.bars = b;
        }
        if let Some(n) = notes {
            v.notes = n.to_owned();
        }
        if let Some(t) = tags {
            v.tags = t;
        }
        let out = v.clone();
        write_variants(&repo, &file, parent, &format!("update variant \"{}\"", out.name))?;
        Ok(out)
    }

    /// The variant board for a family: every variant with the bars where it differs.
    pub fn variant_board(&self, family: &str) -> Result<Vec<VariantStatus>> {
        let repo = self.repo(family)?;
        let mut out = Vec::new();
        for v in read_variants(&repo)?.0.variants {
            let tip = repo.refname_to_id(&format!("refs/heads/{}", v.branch)).ok();
            let main = repo.refname_to_id(&format!("refs/heads/{}", v.base_branch)).ok();
            let base_snapshot = Oid::from_str(&v.base_snapshot).ok();
            let fork = match (tip, main) {
                (Some(t), Some(m)) => repo.merge_base(t, m).ok().or(base_snapshot),
                _ => base_snapshot,
            };
            let path = tip.and_then(|t| self.manifest(family, &t.to_string()).ok()).map(|m| m.source.path);
            let mut status = VariantStatus {
                tip: tip.map(|t| t.to_string()),
                path,
                fork_point: fork.map(|f| f.to_string()),
                main_tip: main.map(|m| m.to_string()),
                differs: Vec::new(),
                music_changes: 0,
                main_changes_since: 0,
                outside_range: Vec::new(),
                variant: v,
            };
            if let (Some(t), Some(f)) = (tip, fork) {
                if t != f {
                    let (a, b) = (self.score_at(&repo, f)?, self.score_at(&repo, t)?);
                    let d = crate::tidy::diff(&a, &b);
                    status.music_changes = d.music_changes();
                    status.differs = ranges(&d);
                }
                if let Some(m) = main.filter(|m| *m != f) {
                    let (a, b) = (self.score_at(&repo, f)?, self.score_at(&repo, m)?);
                    status.main_changes_since = crate::tidy::diff(&a, &b).music_changes();
                }
            }
            if let Some(r) = &status.variant.bars {
                status.outside_range = outside(r, &status.differs);
            }
            out.push(status);
        }
        Ok(out)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn names_and_paths() {
        assert_eq!(
            variant_path(Path::new("/m/1m3 Chase.dorico"), "horns"),
            PathBuf::from("/m/1m3 Chase [horns].dorico")
        );
        assert!(check_name("strings only").is_ok());
        assert!(check_name("a/b").is_err());
        assert!(check_name("  ").is_err());
        assert_eq!(bar_label("bar 35a beat 2+1/2"), "35a");
        assert_eq!(bar_number("35a"), Some(35));
    }

    #[test]
    fn outside_given_range() {
        let r = BarRange { flow: None, from: "17".into(), to: "32".into() };
        let f = |from: &str, to: &str| DiffRange { from: from.into(), to: to.into(), changes: 1, players: vec![] };
        let detected = vec![FlowRanges { flow: "1m3".into(), ranges: vec![f("17", "20"), f("40", "41")] }];
        assert_eq!(outside(&r, &detected), vec!["1m3 b.40-41"]);
    }
}
