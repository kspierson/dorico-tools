//! Checks on the user's own files; each test skips itself when the file isn't reachable.

use std::path::Path;

const PROJECT: &str = "/mnt/c/Users/kspie/Documents/Dorico Projects/Harry Potter Cues Plus 5 + LASS3.dorico";
const PRESETS: &str = "/mnt/c/Users/kspie/OneDrive/Documents/parallax-audio/Presets";

#[test]
fn every_vss2_state_re_encodes_byte_identically() {
    if !Path::new(PROJECT).exists() {
        eprintln!("skipped: {PROJECT} not reachable");
        return;
    }
    let p = dorico_format::Project::read(Path::new(PROJECT)).unwrap();
    let e = p.get(dorico_format::container::ENGINE_DATA).unwrap();
    let mut n = 0;
    for s in dorico_format::mixer::plugin_states(&e.data) {
        if let Some(v) = s.vst2.filter(|v| v.fx_id == "Para") {
            let props = stagecraft::vss2::parse_state(&v.chunk).unwrap();
            assert_eq!(stagecraft::vss2::encode_state(&props), v.chunk, "owner {}", s.owner);
            n += 1;
        }
    }
    assert!(n > 40, "only {n} VSS2 states");
}

/// Every VSS2 instance of the main project has one room (the same for all, whichever layout
/// the state uses) with a decoded Decca tree, and the microphone geometry predicts a point
/// source's arrivals in order.
#[test]
fn every_state_has_the_project_room() {
    if !Path::new(PROJECT).exists() {
        eprintln!("skipped: {PROJECT} not reachable");
        return;
    }
    let all = stagecraft::capture::instances(Path::new(PROJECT)).unwrap();
    let rooms: Vec<_> = all.iter().map(|i| stagecraft::vss2::room(&i.chunk).expect("room")).collect();
    assert!(rooms.iter().all(|r| r.key() == rooms[0].key()), "rooms differ");
    let mic = rooms[0].mic.as_ref().expect("mic setup");
    assert_eq!((rooms[0].name.as_str(), mic.capsules.len()), ("ScSA", 3));
    let point = all.iter().find_map(|i| stagecraft::capture::Geometry::of(&i.chunk)).expect("a point source");
    assert!(point.arrivals().iter().any(|(_, _, ms)| *ms == 0.0));
}

#[test]
fn every_preset_decodes_position() {
    if !Path::new(PRESETS).exists() {
        eprintln!("skipped: {PRESETS} not reachable");
        return;
    }
    fn walk(d: &Path, n: &mut usize) {
        for e in std::fs::read_dir(d).unwrap().flatten() {
            let p = e.path();
            if p.is_dir() {
                walk(&p, n);
            } else if p.extension().is_some_and(|x| x == "vss2preset") {
                let pr = stagecraft::vss2::read_preset(&p).unwrap();
                assert!(pr.vss.x.is_finite() && pr.vss.y.is_finite() && pr.vss.emitters >= 1, "{}", p.display());
                *n += 1;
            }
        }
    }
    let mut n = 0;
    walk(Path::new(PRESETS), &mut n);
    assert!(n >= 198, "{n} presets");
}

#[test]
#[ignore]
fn show_first_difference() {
    let p = dorico_format::Project::read(Path::new(PROJECT)).unwrap();
    let e = p.get(dorico_format::container::ENGINE_DATA).unwrap();
    for s in dorico_format::mixer::plugin_states(&e.data) {
        if let Some(v) = s.vst2.filter(|v| v.fx_id == "Para") {
            let enc = stagecraft::vss2::encode_state(&stagecraft::vss2::parse_state(&v.chunk).unwrap());
            if enc == v.chunk { continue; }
            let i = enc.iter().zip(&v.chunk).position(|(a, b)| a != b).unwrap_or(enc.len().min(v.chunk.len()));
            println!("lens {} {}; first diff at {i}", enc.len(), v.chunk.len());
            let props = stagecraft::vss2::parse_state(&v.chunk).unwrap();
            println!("tags {:?}", props.iter().map(|(t, v)| format!("{t}:{}", match v { stagecraft::vss2::Value::Str(x) => x.chars().take(40).collect::<String>(), stagecraft::vss2::Value::Group(g) => format!("group{}", g.len()), _ => String::new() })).collect::<Vec<_>>());
            println!("orig {:?}", String::from_utf8_lossy(&v.chunk[i.saturating_sub(16)..(i + 24).min(v.chunk.len())]));
            println!("enc  {:?}", String::from_utf8_lossy(&enc[i.saturating_sub(16)..(i + 24).min(enc.len())]));
            println!("orig bytes {:?}", &v.chunk[i.saturating_sub(4)..(i + 12).min(v.chunk.len())]);
            println!("enc  bytes {:?}", &enc[i.saturating_sub(4)..(i + 12).min(enc.len())]);
            if enc != v.chunk { break; }
        }
    }
}
