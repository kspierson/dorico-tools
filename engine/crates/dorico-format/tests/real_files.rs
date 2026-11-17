//! Tests against real Dorico projects. Opt-in, because the files are personal:
//!
//!   DORICO_SAMPLES="/mnt/c/Users/<you>/Documents/Dorico Projects" cargo test -p dorico-format --release
//!
//! (Until 2026-10-30 a third test compared listings with dorigit's Python prototype; the
//! prototype is retired and listings are now pinned by the golden tests, engine/tests/golden.)

use dorico_format::{Project, dtn, xml};
use std::path::PathBuf;

fn samples() -> Vec<PathBuf> {
    let Ok(dir) = std::env::var("DORICO_SAMPLES") else {
        eprintln!("DORICO_SAMPLES not set; skipping real-file tests");
        return Vec::new();
    };
    let mut files: Vec<PathBuf> = std::fs::read_dir(dir)
        .expect("DORICO_SAMPLES is not a directory")
        .filter_map(|e| e.ok().map(|e| e.path()))
        .filter(|p| p.extension().is_some_and(|x| x == "dorico") && p.is_file())
        .collect();
    files.sort();
    files
}

#[test]
fn dtn_round_trips_byte_for_byte() {
    let mut checked = 0;
    for path in samples() {
        let project = Project::read(&path).unwrap();
        for e in project.entries.iter().filter(|e| e.name.ends_with(".dtn")) {
            let doc = dtn::decode(&e.data).unwrap_or_else(|err| panic!("{}: {}: {err:#}", path.display(), e.name));
            assert!(dtn::encode(&doc) == e.data, "{} {}: binary round trip differs", path.display(), e.name);
            let text = xml::to_xml(&doc, true);
            let again = xml::from_xml(text.as_bytes()).unwrap();
            assert!(dtn::encode(&again) == e.data, "{} {}: XML round trip differs", path.display(), e.name);
            checked += 1;
        }
    }
    eprintln!("round-tripped {checked} DTN files");
}

#[test]
fn zip_rebuild_preserves_entries() {
    for path in samples().into_iter().take(3) {
        let p = Project::read(&path).unwrap();
        let again = Project::from_bytes(&p.to_bytes().unwrap()).unwrap();
        assert_eq!(p.entries.len(), again.entries.len());
        for (a, b) in p.entries.iter().zip(&again.entries) {
            assert_eq!(a.name, b.name);
            assert!(a.data == b.data, "{}: {} differs", path.display(), a.name);
            assert_eq!(a.time, b.time);
            assert_eq!((a.is_dir, a.deflated), (b.is_dir, b.deflated), "{}: {} kind differs", path.display(), a.name);
        }
    }
}
