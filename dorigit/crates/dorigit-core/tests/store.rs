//! Store behaviour on small synthetic Dorico projects.

use dorico_format::container::{ENGINE_DATA, Entry, ZipTime};
use dorico_format::{Document, Node, Project, dtn};
use dorigit_core::manifest::SnapshotKind;
use dorigit_core::policy::PlaybackReason;
use dorigit_core::store::{SnapshotOutcome, Store};
use dorigit_core::{PlaybackPolicy, SnapshotInfo};
use std::path::Path;

fn leaf(t: &str, v: &str) -> Node {
    Node::leaf(t, v)
}
fn el(t: &str, kids: Vec<Node>) -> Node {
    Node::element(t, kids)
}
fn arr(t: &str, kids: Vec<Node>) -> Node {
    let mut n = Node::element(t, kids);
    n.array = true;
    n
}

/// A one-note score: Flute, Flow 1, crotchet at `pitch`.
fn score(pitch: u8, saved: i64) -> Document {
    score_in(pitch, saved, "1700000000")
}

fn score_in(pitch: u8, saved: i64, created: &str) -> Document {
    let root = el(
        "kScore",
        vec![
            leaf("fileVersion", "1.1294"),
            el(
                "info",
                vec![
                    leaf("title", "Test Cue"),
                    leaf("createdDate", created),
                    leaf("createdVersion", "5.1.60"),
                    leaf("lastSavedDate", &saved.to_string()),
                    leaf("lastSavedVersion", "5.1.60"),
                ],
            ),
            el("scoreOptions", vec![el("engravingOptions", vec![leaf("noteDotGap", "1/2")])]),
            el(
                "scorePlayers",
                vec![arr("array", vec![el("scorePlayer", vec![leaf("playerID", "0"), leaf("displayName", "Flute")])])],
            ),
            el(
                "flows",
                vec![arr(
                    "array",
                    vec![el(
                        "flow",
                        vec![
                            leaf("flowID", "0"),
                            leaf("flowName", "Flow 1"),
                            el(
                                "flowPlayers",
                                vec![arr(
                                    "array",
                                    vec![el(
                                        "flowPlayer",
                                        vec![
                                            leaf("playerID", "0"),
                                            leaf("eventStreamID", "1"),
                                            arr(
                                                "flowPlayerInstruments",
                                                vec![el(
                                                    "flowPlayerInstrument",
                                                    vec![arr(
                                                        "voiceStreamInfos",
                                                        vec![el("voiceStreamInfo", vec![leaf("voiceStreamID", "3")])],
                                                    )],
                                                )],
                                            ),
                                        ],
                                    )],
                                )],
                            ),
                            el(
                                "blocks",
                                vec![arr(
                                    "array",
                                    vec![el(
                                        "block",
                                        vec![
                                            leaf("blockID", "0"),
                                            el(
                                                "events",
                                                vec![el(
                                                    "NoteEventDefinition",
                                                    vec![
                                                        leaf("eventID", "5"),
                                                        leaf("position", "0"),
                                                        leaf("duration", "1"),
                                                        leaf("pitch", &pitch.to_string()),
                                                    ],
                                                )],
                                            ),
                                        ],
                                    )],
                                )],
                            ),
                            el(
                                "blockInstances",
                                vec![arr(
                                    "array",
                                    vec![el(
                                        "blockInstance",
                                        vec![
                                            leaf("blockInstanceID", "1000"),
                                            leaf("blockID", "0"),
                                            leaf("streamID", "3"),
                                            leaf("position", "0"),
                                        ],
                                    )],
                                )],
                            ),
                            el(
                                "eventStreams",
                                vec![arr(
                                    "array",
                                    vec![el(
                                        "eventStream",
                                        vec![leaf("streamID", "3"), leaf("eventStreamType", "kVoiceStream")],
                                    )],
                                )],
                            ),
                        ],
                    )],
                )],
            ),
        ],
    );
    Document { root, marker: 7 }
}

fn entry(name: &str, data: Vec<u8>) -> Entry {
    Entry { name: name.into(), data, is_dir: false, time: ZipTime(2024, 10, 13, 23, 20, 0), deflated: true }
}

fn opaque(seed: u8, kb: usize) -> Vec<u8> {
    (0..kb * 1024).map(|i| (i as u8).wrapping_mul(31).wrapping_add(seed)).collect()
}

/// enginedata with a mixer XML listing `instruments`, followed by opaque plugin state.
fn engine_with(instruments: &[&str], seed: u8, kb: usize) -> Vec<u8> {
    let mut xml = String::from("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<mixer id=\"1\"><instruments>");
    for name in instruments {
        xml.push_str(&format!("<instrument id=\"2\" name=\"{name}\" uid=\"UID-{name}\"></instrument>"));
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
    out.extend(opaque(seed, kb));
    out
}

/// Write a .dorico with the given pitch, save time and playback blob (seeded bytes of `engine_kb` KB).
fn write_project(path: &Path, pitch: u8, saved: i64, engine_seed: u8, engine_kb: usize) -> Vec<u8> {
    write_with(path, score(pitch, saved), opaque(engine_seed, engine_kb))
}

fn write_with(path: &Path, score: Document, engine: Vec<u8>) -> Vec<u8> {
    let score = dtn::encode(&score);
    let lib = dtn::encode(&Document { root: el("kScoreLibrary", vec![leaf("fileVersion", "1.1294")]), marker: 7 });
    let p = Project {
        entries: vec![
            Entry {
                name: "META-INF/".into(),
                data: vec![],
                is_dir: true,
                time: ZipTime(2024, 10, 13, 23, 20, 0),
                deflated: true,
            },
            entry("META-INF/container.xml", b"<container/>".to_vec()),
            entry("score.dtn", score.clone()),
            entry("scorelibrary.dtn", lib),
            entry(ENGINE_DATA, engine),
        ],
    };
    p.write(path).unwrap();
    score
}

fn created(o: SnapshotOutcome) -> SnapshotInfo {
    match o {
        SnapshotOutcome::Created { snapshot } => snapshot,
        other => panic!("expected a new snapshot, got {other:?}"),
    }
}

#[test]
fn snapshot_history_policy_and_restore() {
    let tmp = tempfile::tempdir().unwrap();
    let store = Store::open(tmp.path().join("store"), PlaybackPolicy::default()).unwrap();
    let work = tmp.path().join("work");
    std::fs::create_dir_all(&work).unwrap();
    let cue = work.join("Cue.dorico");

    // 1st save: big playback, nothing to borrow from yet -> kept
    write_project(&cue, 60, 1_700_000_100, 1, 3 * 1024);
    let s1 = created(store.snapshot_file(&cue, SnapshotKind::Auto, None).unwrap());
    assert!(s1.playback_stored);
    assert_eq!(s1.playback_reason, PlaybackReason::FirstInHistory);
    assert_eq!(s1.summary.text, "first snapshot");

    // same content again -> no new snapshot
    assert!(matches!(store.snapshot_file(&cue, SnapshotKind::Auto, None).unwrap(), SnapshotOutcome::Unchanged { .. }));

    // 2nd save: note C4 -> D4, playback bytes changed -> playback skipped
    let score2 = write_project(&cue, 62, 1_700_000_200, 2, 3 * 1024);
    let s2 = created(store.snapshot_file(&cue, SnapshotKind::Auto, None).unwrap());
    assert!(!s2.playback_stored);
    assert_eq!(s2.playback_reason, PlaybackReason::Skipped);
    assert_eq!(s2.playback_borrow_from.as_deref(), Some(s1.id.as_str()));
    assert_eq!(s2.parents, vec![s1.id.clone()]);
    assert_eq!(s2.summary.music_changes, 1, "{:?}", s2.summary);
    let d = store.diff(&s2.family, None, &s2.id).unwrap();
    let change = &d.flows[0].owners[0].changes[0];
    assert_eq!(change.owner, "Flute");
    assert_eq!(change.details, vec!["C4 crotchet -> D4 crotchet"]);

    // restore s2: score bytes identical, playback borrowed from s1
    let dest = Store::restore_path(&work, "Cue.dorico", &s2.short_id);
    let r = store.restore(&s2.family, &s2.id, &dest).unwrap();
    assert_eq!(r.playback_from.as_deref(), Some(s1.id.as_str()));
    let restored = Project::read(&dest).unwrap();
    assert!(restored.get("score.dtn").unwrap().data == score2);
    assert_eq!(restored.entries.len(), 5);
    assert!(store.restore(&s2.family, &s2.id, &dest).is_err(), "restore must never overwrite");

    // saving the restored file continues from the restored snapshot (pending fork)
    write_project(&dest, 64, 1_700_000_300, 3, 3 * 1024);
    let s3 = created(store.snapshot_file(&dest, SnapshotKind::Auto, None).unwrap());
    assert_eq!(s3.parents, vec![s2.id.clone()]);
    assert!(!s3.playback_stored, "same setup: borrow instead of storing again");
    assert_eq!(s3.playback_borrow_from.as_deref(), Some(s1.id.as_str()));

    // "Save As" a new file: forks from the family's latest snapshot
    let alt = work.join("Cue - darker ending.dorico");
    write_project(&alt, 59, 1_700_000_400, 4, 3 * 1024);
    let s4 = created(store.snapshot_file(&alt, SnapshotKind::Auto, None).unwrap());
    assert_eq!(s4.parents, vec![s3.id.clone()]);

    // milestone: tagged and keeps playback even though it's big
    write_project(&cue, 65, 1_700_000_500, 5, 3 * 1024);
    let s5 = created(store.snapshot_file(&cue, SnapshotKind::Manual, Some("Sent to orchestrator")).unwrap());
    assert!(s5.playback_stored);
    assert_eq!(s5.playback_reason, PlaybackReason::Milestone);
    assert_eq!(s5.milestones[0].name, "Sent to orchestrator");
    assert_eq!(s5.parents, vec![s2.id.clone()], "Cue.dorico's branch continues from s2");

    // history, families
    let all = store.snapshots(&s1.family).unwrap();
    assert_eq!(all.len(), 5);
    assert_eq!(all[0].id, s5.id, "newest first");
    let fams = store.families().unwrap();
    assert_eq!(fams.len(), 1);
    assert_eq!(fams[0].files.len(), 3);
    assert_eq!(store.family_of_file(&alt).unwrap().as_deref(), Some(s1.family.as_str()));

    // small playback is kept automatically
    let tiny = work.join("Tiny.dorico");
    write_project(&tiny, 60, 1_700_000_600, 9, 16);
    let st = created(store.snapshot_file(&tiny, SnapshotKind::Auto, None).unwrap());
    write_project(&tiny, 61, 1_700_000_700, 10, 16);
    let st2 = created(store.snapshot_file(&tiny, SnapshotKind::Auto, None).unwrap());
    assert!(st.playback_stored && st2.playback_stored);
    assert_eq!(st2.playback_reason, PlaybackReason::Small);
}

#[test]
fn playback_kept_when_plugin_setup_changes() {
    let tmp = tempfile::tempdir().unwrap();
    let store = Store::open(tmp.path().join("store"), PlaybackPolicy::default()).unwrap();
    let cue = tmp.path().join("Setup.dorico");
    let created_date = "1600000000";

    write_with(&cue, score_in(60, 1, created_date), engine_with(&["Kontakt", "Kontakt"], 1, 3 * 1024));
    let a = created(store.snapshot_file(&cue, SnapshotKind::Auto, None).unwrap());
    assert_eq!(a.playback_reason, PlaybackReason::FirstInHistory);

    // plugin internals re-saved, same plugins -> skipped
    write_with(&cue, score_in(61, 2, created_date), engine_with(&["Kontakt", "Kontakt"], 2, 3 * 1024));
    let b = created(store.snapshot_file(&cue, SnapshotKind::Auto, None).unwrap());
    assert_eq!(b.playback_reason, PlaybackReason::Skipped);
    assert!(b.playback_setup_changes.is_empty());

    // Virtual Sound Stage added -> kept, and described
    write_with(&cue, score_in(62, 3, created_date), engine_with(&["Kontakt", "Kontakt", "VSS"], 3, 3 * 1024));
    let c = created(store.snapshot_file(&cue, SnapshotKind::Auto, None).unwrap());
    assert_eq!(c.playback_reason, PlaybackReason::SetupChanged);
    assert_eq!(c.playback_setup_changes, vec!["+1 VSS"]);

    // next save borrows from c (same setup), not from a
    write_with(&cue, score_in(63, 4, created_date), engine_with(&["Kontakt", "Kontakt", "VSS"], 4, 3 * 1024));
    let d = created(store.snapshot_file(&cue, SnapshotKind::Auto, None).unwrap());
    assert_eq!(d.playback_borrow_from.as_deref(), Some(c.id.as_str()));
}

#[test]
fn writes_wait_for_another_process_holding_the_family_lock() {
    let tmp = tempfile::tempdir().unwrap();
    let mut store = Store::open(tmp.path().join("store"), PlaybackPolicy::default()).unwrap();
    store.lock_timeout = std::time::Duration::from_millis(200);
    let cue = tmp.path().join("Cue.dorico");
    write_project(&cue, 60, 1_700_000_100, 1, 4);
    let s1 = created(store.snapshot_file(&cue, SnapshotKind::Auto, None).unwrap());

    // another program (a second Store on the same folder stands in for it) holds the lock
    let other = Store::open(tmp.path().join("store"), PlaybackPolicy::default()).unwrap();
    let held = other.lock_family(&s1.family).unwrap();
    write_project(&cue, 62, 1_700_000_200, 1, 4);
    let err = store.snapshot_file(&cue, SnapshotKind::Auto, None).unwrap_err().to_string();
    assert!(err.contains("busy"), "{err}");
    assert!(store.add_milestone(&s1.family, &s1.id, "v1").is_err());
    assert_eq!(store.snapshots(&s1.family).unwrap().len(), 1, "reads still work while locked");

    // released: the waiting write goes through
    drop(held);
    let s2 = created(store.snapshot_file(&cue, SnapshotKind::Auto, None).unwrap());
    assert_eq!(s2.parents, vec![s1.id]);
}

#[test]
fn branch_names_are_machine_independent_and_old_ones_migrate() {
    let tmp = tempfile::tempdir().unwrap();
    let root = tmp.path().join("store");
    let store = Store::open(&root, PlaybackPolicy::default()).unwrap();
    let a = tmp.path().join("studio").join("1m3 Chase.dorico");
    let b = tmp.path().join("laptop copy").join("1m3 Chase.dorico");
    std::fs::create_dir_all(a.parent().unwrap()).unwrap();
    std::fs::create_dir_all(b.parent().unwrap()).unwrap();

    // named after the file, not its folder
    write_project(&a, 60, 1_700_000_100, 1, 4);
    let s1 = created(store.snapshot_file(&a, SnapshotKind::Auto, None).unwrap());
    assert_eq!(s1.branches, vec!["1m3-chase"]);
    // a different file with the same name on this machine gets a numbered branch
    write_project(&b, 62, 1_700_000_200, 1, 4);
    let s2 = created(store.snapshot_file(&b, SnapshotKind::Auto, None).unwrap());
    assert_eq!(s2.branches, vec!["1m3-chase-2"]);

    // simulate a store made before 2026-10-31: branch "1m3-chase-<path hash>" in refs and family.json
    let repo = git2::Repository::open_bare(root.join(format!("{}.git", s1.family))).unwrap();
    let fam_path = root.join(format!("{}.git", s1.family)).join("family.json");
    let mut fam: serde_json::Value = serde_json::from_slice(&std::fs::read(&fam_path).unwrap()).unwrap();
    let key_a = fam["files"].as_object().unwrap().iter().find(|(_, v)| *v == "1m3-chase").unwrap().0.clone();
    let hash = git2::Oid::hash_object(git2::ObjectType::Blob, key_a.as_bytes()).unwrap().to_string();
    let legacy = format!("1m3-chase-{}", &hash[..6]);
    repo.find_reference("refs/heads/1m3-chase")
        .unwrap()
        .rename(&format!("refs/heads/{legacy}"), false, "test: old name")
        .unwrap();
    fam["files"][&key_a] = serde_json::Value::String(legacy.clone());
    std::fs::write(&fam_path, serde_json::to_vec(&fam).unwrap()).unwrap();

    assert_eq!(store.migrate().unwrap(), 1);
    assert_eq!(store.migrate().unwrap(), 0, "migration runs once");
    // (opening a store also migrates; covered by the call above)
    let names: Vec<String> =
        store.snapshots(&s1.family).unwrap().into_iter().flat_map(|s| s.branches).collect::<Vec<_>>();
    assert!(names.contains(&"1m3-chase".to_owned()) && !names.contains(&legacy), "{names:?}");

    // history continues on the migrated branch
    write_project(&a, 64, 1_700_000_300, 1, 4);
    let s3 = created(store.snapshot_file(&a, SnapshotKind::Auto, None).unwrap());
    assert_eq!(s3.branches, vec!["1m3-chase"]);
    assert_eq!(s3.parents, vec![s1.id]);
}

#[test]
fn variants_fork_from_the_main_version_and_report_their_bars() {
    use dorigit_core::variants::BarRange;
    let tmp = tempfile::tempdir().unwrap();
    let root = tmp.path().join("store");
    let store = Store::open(&root, PlaybackPolicy::default()).unwrap();
    let cue = tmp.path().join("1m3 Chase.dorico");
    write_project(&cue, 60, 1_700_000_100, 1, 4);
    let s1 = created(store.snapshot_file(&cue, SnapshotKind::Auto, None).unwrap());

    // make a variant: exact copy beside the cue, history starting at the cue's snapshot
    let range = BarRange { flow: None, from: "1".into(), to: "1".into() };
    let (path, v) = store.new_variant(&cue, "horns", Some(range)).unwrap();
    assert_eq!(path, tmp.path().join("1m3 Chase [horns].dorico"));
    assert_eq!(std::fs::read(&path).unwrap(), std::fs::read(&cue).unwrap());
    assert_eq!((v.branch.as_str(), v.base_branch.as_str()), ("1m3-chase-horns", "1m3-chase"));
    assert_eq!(v.base_snapshot, s1.id);
    assert!(store.new_variant(&cue, "horns", None).is_err(), "never overwrites");
    assert!(store.new_variant(&cue, "a/b", None).is_err());

    // nothing changed yet
    let board = store.variant_board(&s1.family).unwrap();
    assert_eq!(board.len(), 1);
    assert_eq!(board[0].music_changes, 0);
    assert_eq!(board[0].fork_point.as_deref(), Some(s1.id.as_str()));

    // the variant changes its note; the main version changes too
    write_project(&path, 67, 1_700_000_200, 1, 4);
    let sv = created(store.snapshot_file(&path, SnapshotKind::Auto, None).unwrap());
    assert_eq!(sv.parents, vec![s1.id.clone()]);
    write_project(&cue, 62, 1_700_000_300, 1, 4);
    store.snapshot_file(&cue, SnapshotKind::Auto, None).unwrap();

    let b = &store.variant_board(&s1.family).unwrap()[0];
    assert_eq!(b.music_changes, 1);
    assert_eq!(b.main_changes_since, 1);
    assert_eq!(b.differs.len(), 1);
    assert_eq!((b.differs[0].ranges[0].from.as_str(), b.differs[0].ranges[0].to.as_str()), ("1", "1"));
    assert_eq!(b.differs[0].ranges[0].players, vec!["Flute"]);
    assert!(b.outside_range.is_empty());

    // notes and tags live in the history (refs/dorigit/variants), each change a commit
    let u = store
        .update_variant(&s1.family, &v.branch, None, None, Some("director prefers"), Some(vec!["fav".into()]))
        .unwrap();
    assert_eq!((u.notes.as_str(), u.tags.clone()), ("director prefers", vec!["fav".to_owned()]));
    let repo = git2::Repository::open_bare(root.join(format!("{}.git", s1.family))).unwrap();
    let meta = repo.find_reference("refs/dorigit/variants").unwrap().peel_to_commit().unwrap();
    assert_eq!(meta.parent_count(), 1);
    assert_eq!(store.variants(&s1.family).unwrap()[0].notes, "director prefers");
}

#[test]
fn notation_of_a_change_colours_old_and_new_notes() {
    let tmp = tempfile::tempdir().unwrap();
    let store = Store::open(tmp.path().join("store"), PlaybackPolicy::default()).unwrap();
    let cue = tmp.path().join("Cue.dorico");
    write_project(&cue, 60, 1_700_000_100, 1, 4);
    store.snapshot_file(&cue, SnapshotKind::Auto, None).unwrap();
    write_project(&cue, 62, 1_700_000_200, 1, 4);
    let s2 = created(store.snapshot_file(&cue, SnapshotKind::Auto, None).unwrap());
    let flow = store.diff(&s2.family, None, &s2.id).unwrap().flows[0].flow_id.clone();

    let n = store.notation_diff(&s2.family, None, &s2.id, &flow).unwrap();
    assert_eq!(n.players, vec!["Flute"]);
    let (before, after) = (n.before.unwrap(), n.after.unwrap());
    let changed = dorigit_core::notation::CHANGED;
    assert!(before.contains(&format!(r#"<note pname="c" oct="4" dur="4" color="{changed}"/>"#)), "{before}");
    assert!(after.contains(&format!(r#"<note pname="d" oct="4" dur="4" color="{changed}"/>"#)), "{after}");
    assert!(after.starts_with("<?xml") && after.contains("<staffDef n=\"1\""));
}

/// Real data: ET test file A, then D (one note moved up an octave) saved over it.
#[test]
fn notation_of_a_real_edit() {
    let dir = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../../engine/tests/dorico-files");
    let (a, d) = (
        dir.join("ET The Flying Theme mASTER A-rebuilt.dorico"),
        dir.join("ET The Flying Theme mASTER D-note-edit.dorico"),
    );
    if !a.exists() || !d.exists() {
        eprintln!("skipped: ET test files not present");
        return;
    }
    let tmp = tempfile::tempdir().unwrap();
    let store = Store::open(tmp.path().join("store"), PlaybackPolicy::default()).unwrap();
    let cue = tmp.path().join("ET.dorico");
    std::fs::copy(&a, &cue).unwrap();
    store.snapshot_file(&cue, SnapshotKind::Auto, None).unwrap();
    std::fs::copy(&d, &cue).unwrap();
    let s2 = created(store.snapshot_file(&cue, SnapshotKind::Auto, None).unwrap());
    let diff = store.diff(&s2.family, None, &s2.id).unwrap();
    let flow = diff.flows.iter().find(|f| f.total > 0).unwrap();
    let n = store.notation_diff(&s2.family, None, &s2.id, &flow.flow_id).unwrap();
    assert_eq!(n.players.len(), 1, "{:?}", n.players);
    let changed = dorigit_core::notation::CHANGED;
    let (before, after) = (n.before.unwrap(), n.after.unwrap());
    assert_eq!(before.matches(changed).count(), 1, "one note coloured before");
    assert_eq!(after.matches(changed).count(), 1, "one note coloured after");
    if let Ok(out) = std::env::var("DORIGIT_NOTATION_OUT") {
        std::fs::write(format!("{out}/before.mei"), &before).unwrap();
        std::fs::write(format!("{out}/after.mei"), &after).unwrap();
    }
}

/// The user's divisi reference file with IA / IB edits (research/make_merge_tests.py).
#[test]
fn merge_preview_divisi_pairs() {
    use dorigit_core::merge::{Outcome, preview};
    let dir = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../research/refs");
    let read = |p: std::path::PathBuf| dorigit_core::listing::build(&Project::read(&p).unwrap().score().unwrap().root);
    let base_path = dir.join("ref-dynamics-divisi.dorico");
    if !base_path.exists() || !dir.join("merge/merge-A-IA.dorico").exists() {
        eprintln!("skipped: reference files not present");
        return;
    }
    let base = read(base_path);
    let f = |n: &str| read(dir.join(format!("merge/merge-{n}.dorico")));
    let (a, b, c, d) = (f("A-IA"), f("B-IB"), f("C-IA-other"), f("D-dynamic"));

    let ab = preview(&base, &a, &b);
    assert_eq!((ab.counts.review, ab.counts.conflict, ab.counts.auto), (2, 0, 0), "IA vs IB: review");
    assert!(ab.items.iter().all(|i| i.bar == "5"));
    let ac = preview(&base, &a, &c);
    assert_eq!((ac.counts.conflict, ac.counts.review), (1, 0), "same note, different pitch: conflict");
    assert_eq!(ac.items[0].outcome, Outcome::Conflict);
    let ad = preview(&base, &a, &d);
    assert_eq!((ad.counts.auto, ad.counts.conflict, ad.counts.review), (2, 0, 0), "different bars: automatic");
    let aa = preview(&base, &a, &a);
    assert_eq!((aa.counts.same, aa.counts.conflict), (1, 0), "identical change on both sides");
}

#[test]
fn merge_preview_of_a_variant_and_its_main_version() {
    let tmp = tempfile::tempdir().unwrap();
    let store = Store::open(tmp.path().join("store"), PlaybackPolicy::default()).unwrap();
    let cue = tmp.path().join("Cue.dorico");
    write_project(&cue, 60, 1_700_000_100, 1, 4);
    store.snapshot_file(&cue, SnapshotKind::Auto, None).unwrap();
    let (vpath, _) = store.new_variant(&cue, "alt", None).unwrap();
    write_project(&vpath, 64, 1_700_000_200, 1, 4);
    let sv = created(store.snapshot_file(&vpath, SnapshotKind::Auto, None).unwrap());
    write_project(&cue, 67, 1_700_000_300, 1, 4);
    let sm = created(store.snapshot_file(&cue, SnapshotKind::Auto, None).unwrap());

    let p = store.merge_preview(&sm.family, &sm.id, &sv.id, None).unwrap();
    assert_eq!(p.counts.conflict, 1, "{p:#?}");
    assert!(p.integrity.is_empty() || p.integrity.iter().all(|i| !i.is_empty()));
    let text = dorigit_core::merge::render_text(&p, 10);
    assert!(text.contains("C4 crotchet -> G4 crotchet") && text.contains("C4 crotchet -> E4 crotchet"), "{text}");
}
