//! Print the playback setup (loaded plugins) of .dorico files.
//!   cargo run -p dorico-format --example playback_setup -- *.dorico
fn main() {
    for path in std::env::args().skip(1) {
        let p = dorico_format::Project::read(path.as_ref()).unwrap();
        let Some(e) = p.get(dorico_format::container::ENGINE_DATA) else {
            println!("{path}: no playback data");
            continue;
        };
        match dorico_format::playback::read_setup(&e.data) {
            Some(s) => {
                let inst: Vec<String> = s.instruments.iter().map(|p| format!("{} x{}", p.name, p.count)).collect();
                println!("{path}\n  {} MB, instruments: {}", e.data.len() / 1_000_000, inst.join(", "));
            }
            None => println!("{path}: unrecognised enginedata layout"),
        }
    }
}
