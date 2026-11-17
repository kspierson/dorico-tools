//! Read every project of the corpus (engine/tests/corpus.toml) into the model. Opt-in, because
//! the files are personal:  DORICO_REAL_FILES=1 cargo test -p dorico-model --release --test real_files

use dorico_format::Project;
use dorico_paths::corpus::Corpus;

#[test]
fn every_project_reads() {
    if std::env::var("DORICO_REAL_FILES").is_err() {
        eprintln!("DORICO_REAL_FILES not set; skipping");
        return;
    }
    let c = Corpus::load().unwrap();
    let mut files = c.dorico_files("projects");
    files.extend(c.dorico_files("test_files"));
    let mut notes = 0;
    for f in &files {
        let s = dorico_model::read_project(&Project::read(f).unwrap()).unwrap();
        for flow in &s.flows {
            assert!(!flow.bars.is_empty(), "{}: no bars", f.display());
            // bars tile the flow without gaps
            for w in flow.bars.windows(2) {
                assert_eq!(w[0].start + w[0].length, w[1].start, "{}: gap between bars", f.display());
            }
            assert!(flow.bars.last().map(|b| b.start + b.length >= flow.length).unwrap());
            notes += flow.parts.iter().flat_map(|p| &p.voices).map(|v| v.notes.len()).sum::<usize>();
        }
    }
    eprintln!("read {} projects, {notes} notes", files.len());
}

/// The user's reference file for bar numbers and repeats (finale2dorico Round 7 reference,
/// re-saved 2026-10-29 with a pick-up, a primary bar-number change at bar 2 (-> 30), a
/// subordinate change at bar 8, repeats, endings, segno/coda). Copied to
/// engine/tests/dorico-files/reference/ (git-ignored: it carries Dorico library data).
#[test]
fn reference_bar_numbers_and_repeats() {
    let Ok(c) = Corpus::load() else { return };
    let Some(dir) = c.get("test_files") else { return };
    let f = dir.join("reference/bars-numbers-repeats.dorico");
    if !f.is_file() {
        eprintln!("{} missing; skipping", f.display());
        return;
    }
    let s = dorico_model::read_project(&Project::read(&f).unwrap()).unwrap();
    let flow = &s.flows[0];
    let labels: Vec<&str> = flow.bars.iter().map(|b| b.label.as_str()).collect();
    assert_eq!(&labels[..10], ["0", "1", "30", "31", "32", "33", "34", "35", "35a", "35b"]);
    assert_eq!(flow.bar_number_changes.len(), 2);
    let kinds: Vec<&str> = flow.repeats.iter().map(|r| r.kind.as_str()).collect();
    assert_eq!(kinds, ["ending", "segno", "jump", "jump", "coda"]);
    let barlines: Vec<&str> = flow.barlines.iter().map(|b| b.kind.as_str()).collect();
    assert_eq!(barlines, ["kEndAndStartRepeat", "kEndRepeat", "kDouble"]);
}
