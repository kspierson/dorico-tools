//! `dorigit` command line. Same engine as the desktop app.

use anyhow::{Context, Result, bail};
use clap::{Parser, Subcommand};
use dorico_format::{Project, diff, dtn, xml};
use dorigit_core::listing::build as build_score;
use dorigit_core::variants::{BarRange, VariantStatus};
use dorigit_core::manifest::SnapshotKind;
use dorigit_core::store::{SnapshotOutcome, resolve_id};
use dorigit_core::{Settings, SnapshotInfo, Store};
use std::path::{Path, PathBuf};
use std::time::Duration;

#[derive(Parser)]
#[command(name = "dorigit", version, about = "Version control for Dorico projects")]
struct Cli {
    /// Settings file (default: <data dir>/settings.json, shared with the app)
    #[arg(long, global = true)]
    settings: Option<PathBuf>,
    /// History store directory (overrides settings)
    #[arg(long, global = true)]
    store: Option<PathBuf>,
    #[command(subcommand)]
    cmd: Cmd,
}

#[derive(Subcommand)]
enum Cmd {
    /// Musical listing of a project (one fact per line). Used as git textconv.
    Show { project: PathBuf },
    /// Musical diff of two .dorico files.
    Diff {
        old: PathBuf,
        new: PathBuf,
        #[arg(long)]
        json: bool,
        #[arg(long, default_value_t = 40)]
        max_per_part: usize,
    },
    /// Print the score (or scorelibrary) as XML.
    Dump {
        project: PathBuf,
        #[arg(default_value = "score")]
        part: String,
    },
    /// Check that every .dtn inside the given projects re-encodes byte-for-byte.
    Verify { projects: Vec<PathBuf> },
    /// Make `git diff` / `git log -p` show *.dorico changes musically in a repo.
    SetupGit {
        #[arg(default_value = ".")]
        repo: PathBuf,
    },
    /// Snapshot a .dorico file into the history store.
    Snapshot {
        project: PathBuf,
        /// Also mark as a milestone with this name (keeps playback state)
        #[arg(long)]
        milestone: Option<String>,
    },
    /// Import existing files (e.g. "Cue 2", "Cue 3") as history, in Dorico save order.
    Import { projects: Vec<PathBuf> },
    /// List project families in the store.
    Families,
    /// Show the history of a family (or of the family a .dorico file belongs to).
    Log { target: String },
    /// Musical diff between two snapshots (default: against its parent).
    Changes {
        target: String,
        id: String,
        #[arg(long)]
        against: Option<String>,
        #[arg(long)]
        json: bool,
    },
    /// Rebuild a snapshot as a new .dorico file.
    Restore {
        target: String,
        id: String,
        #[arg(long)]
        to: Option<PathBuf>,
    },
    /// Mark a snapshot as a milestone.
    Milestone { target: String, id: String, name: String },
    /// Watch folders and snapshot every save (foreground).
    Watch { dirs: Vec<PathBuf> },
    /// Preview merging two snapshots of a project: what combines automatically, what needs
    /// review, what conflicts (docs/MERGE.md §4). Nothing is written.
    MergePreview {
        target: String,
        ours: String,
        theirs: String,
        /// Base snapshot (default: their common ancestor)
        #[arg(long)]
        base: Option<String>,
        #[arg(long)]
        json: bool,
        /// Automatic items to list (the rest are counted)
        #[arg(long, default_value_t = 40)]
        max_auto: usize,
    },
    /// Merge preview of three .dorico files: BASE, OURS, THEIRS.
    MergePreviewFiles {
        base: PathBuf,
        ours: PathBuf,
        theirs: PathBuf,
        #[arg(long)]
        json: bool,
        #[arg(long, default_value_t = 40)]
        max_auto: usize,
    },
    /// A range of bars as MEI notation (what the app renders with Verovio).
    Notation {
        project: PathBuf,
        /// Flow id (see `dorigit show`; default: the first flow)
        #[arg(long)]
        flow: Option<String>,
        /// Bar indices, e.g. 1-8 (a pick-up counts as bar 1)
        #[arg(long, default_value = "1-8")]
        bars: String,
        /// Only these players (repeat)
        #[arg(long = "player")]
        players: Vec<String>,
    },
    /// Variants of a cue: make one, show the board, add notes (docs/MERGE.md §3).
    Variant {
        #[command(subcommand)]
        cmd: VariantCmd,
    },
}

#[derive(Subcommand)]
enum VariantCmd {
    /// Copy FILE to "<name> [NAME].dorico" beside it and start its history there.
    New {
        file: PathBuf,
        name: String,
        /// Bars the variant is about, e.g. 17-32 (optional; differences are detected anyway)
        #[arg(long)]
        bars: Option<String>,
        /// Flow the bars are in (default: any)
        #[arg(long)]
        flow: Option<String>,
    },
    /// Show every variant of a project and the bars where it differs.
    List {
        target: String,
        #[arg(long)]
        json: bool,
    },
    /// Change a variant's notes, tags, name or bars. VARIANT = its name or file name.
    Note {
        target: String,
        variant: String,
        #[arg(long)]
        notes: Option<String>,
        /// Replace the tags (repeat for several)
        #[arg(long = "tag")]
        tags: Vec<String>,
        #[arg(long)]
        rename: Option<String>,
        #[arg(long)]
        bars: Option<String>,
    },
}

/// "17-32" or "17" -> a bar range.
fn parse_bars(bars: &str, flow: Option<String>) -> Result<BarRange> {
    let (from, to) = bars.split_once('-').unwrap_or((bars, bars));
    if from.trim().is_empty() || to.trim().is_empty() {
        anyhow::bail!("bars look like 17-32");
    }
    Ok(BarRange { flow, from: from.trim().to_owned(), to: to.trim().to_owned() })
}

fn settings_path(cli: &Cli) -> PathBuf {
    cli.settings.clone().unwrap_or_else(|| dorigit_core::settings::default_data_dir().join("settings.json"))
}

fn open_store(cli: &Cli) -> Result<(Settings, Store)> {
    let mut s = Settings::load(&settings_path(cli));
    if let Some(dir) = &cli.store {
        s.store_dir = dir.clone();
    }
    let store = Store::open(&s.store_dir, s.playback.clone())?;
    Ok((s, store))
}

/// A family id, or a path to a .dorico file whose family we look up.
fn family_of(store: &Store, target: &str) -> Result<String> {
    let p = Path::new(target);
    if p.extension().is_some_and(|e| e.eq_ignore_ascii_case("dorico")) {
        return store.family_of_file(p)?.with_context(|| format!("{target} has no history yet"));
    }
    Ok(target.to_owned())
}

fn utc_time(ts: i64) -> String {
    // Dependency-free; the app shows local time.
    let days = ts.div_euclid(86_400);
    let secs = ts.rem_euclid(86_400);
    let z = days + 719_468;
    let era = z.div_euclid(146_097);
    let doe = z.rem_euclid(146_097);
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = if mp < 10 { mp + 3 } else { mp - 9 };
    let y = yoe + era * 400 + i64::from(m <= 2);
    format!("{y:04}-{m:02}-{d:02} {:02}:{:02}Z", secs / 3600, secs % 3600 / 60)
}

fn print_snapshot(s: &SnapshotInfo) {
    let marks: Vec<String> = s.milestones.iter().map(|m| format!("★ {}", m.name)).collect();
    let playback = if s.playback_stored { "♪" } else { " " };
    println!(
        "{} {} {playback} {:<36} {}{}",
        s.short_id,
        utc_time(s.time),
        s.file_name,
        s.summary.text,
        if marks.is_empty() { String::new() } else { format!("  {}", marks.join(" ")) }
    );
}

fn print_board(board: &[VariantStatus]) {
    if board.is_empty() {
        println!("no variants yet (dorigit variant new <file> <name>)");
    }
    for b in board {
        let v = &b.variant;
        let given = v.bars.as_ref().map(|r| format!("  [about b.{}-{}]", r.from, r.to)).unwrap_or_default();
        let tags = if v.tags.is_empty() { String::new() } else { format!("  #{}", v.tags.join(" #")) };
        println!("{}  ({}, from {}){given}{tags}", v.name, v.file_name, v.base_branch);
        if b.tip.is_none() {
            println!("    (its file has no history on this machine yet)");
        } else if b.differs.is_empty() {
            println!("    same as where it started");
        }
        for f in &b.differs {
            let ranges: Vec<String> = f
                .ranges
                .iter()
                .map(|r| {
                    let bars = if r.from == r.to { format!("b.{}", r.from) } else { format!("b.{}-{}", r.from, r.to) };
                    format!("{bars} ({}: {})", r.changes, r.players.join(", "))
                })
                .collect();
            println!("    {}: {}", f.flow, ranges.join("; "));
        }
        if !b.outside_range.is_empty() {
            println!("    ! also changed outside its bars: {}", b.outside_range.join(", "));
        }
        if b.main_changes_since > 0 {
            println!("    main version has {} change(s) since this variant started", b.main_changes_since);
        }
        if !v.notes.is_empty() {
            println!("    notes: {}", v.notes);
        }
    }
}

fn print_outcome(path: &Path, o: &SnapshotOutcome) {
    match o {
        SnapshotOutcome::Created { snapshot } => print_snapshot(snapshot),
        SnapshotOutcome::Unchanged { id, .. } => println!("{} unchanged (same as {})", path.display(), &id[..7]),
    }
}

fn main() -> Result<()> {
    let cli = Cli::parse();
    match &cli.cmd {
        Cmd::Show { project } => {
            let p = Project::read(project)?;
            print!("{}", diff::listing(&build_score(&p.score()?.root)));
        }
        Cmd::Diff { old, new, json, max_per_part } => {
            let a = build_score(&Project::read(old)?.score()?.root);
            let b = build_score(&Project::read(new)?.score()?.root);
            let d = dorigit_core::tidy::diff(&a, &b);
            if *json {
                println!("{}", serde_json::to_string_pretty(&d)?);
            } else {
                print!("{}", diff::render_text(&d, *max_per_part, 30));
            }
        }
        Cmd::Dump { project, part } => {
            print!("{}", xml::to_xml(&Project::read(project)?.document(part)?, false));
        }
        Cmd::Verify { projects } => {
            let mut bad = 0;
            for path in projects {
                let p = Project::read(path)?;
                for e in p.entries.iter().filter(|e| e.name.ends_with(".dtn")) {
                    let ok = dtn::decode(&e.data)
                        .map(|doc| {
                            dtn::encode(&doc) == e.data
                                && xml::from_xml(xml::to_xml(&doc, true).as_bytes())
                                    .map(|d| dtn::encode(&d) == e.data)
                                    .unwrap_or(false)
                        })
                        .unwrap_or(false);
                    bad += usize::from(!ok);
                    println!("{} {} :: {}", if ok { "ok  " } else { "FAIL" }, path.display(), e.name);
                }
            }
            if bad > 0 {
                bail!("{bad} file(s) failed");
            }
        }
        Cmd::SetupGit { repo } => setup_git(repo)?,
        Cmd::Snapshot { project, milestone } => {
            let (_, store) = open_store(&cli)?;
            let kind = if milestone.is_some() { SnapshotKind::Manual } else { SnapshotKind::Auto };
            print_outcome(project, &store.snapshot_file(project, kind, milestone.as_deref())?);
        }
        Cmd::Import { projects } => {
            let (_, store) = open_store(&cli)?;
            for (p, r) in store.import(projects) {
                match r {
                    Ok(o) => print_outcome(&p, &o),
                    Err(e) => eprintln!("{}: {e:#}", p.display()),
                }
            }
        }
        Cmd::Families => {
            let (_, store) = open_store(&cli)?;
            for f in store.families()? {
                println!(
                    "{:<14} {:<40} {:>4} snapshots  {:>6.1} MB  {} file(s)",
                    f.id,
                    f.display_name,
                    f.snapshot_count,
                    store.family_size(&f.id) as f64 / 1e6,
                    f.files.len()
                );
            }
        }
        Cmd::Log { target } => {
            let (_, store) = open_store(&cli)?;
            for s in store.snapshots(&family_of(&store, target)?)? {
                print_snapshot(&s);
            }
        }
        Cmd::Changes { target, id, against, json } => {
            let (_, store) = open_store(&cli)?;
            let fam = family_of(&store, target)?;
            let snaps = store.snapshots(&fam)?;
            let id = resolve_id(&snaps, id)?;
            let against = against.as_deref().map(|a| resolve_id(&snaps, a)).transpose()?;
            let d = store.diff(&fam, against.as_deref(), &id)?;
            if *json {
                println!("{}", serde_json::to_string_pretty(&d)?);
            } else {
                print!("{}", diff::render_text(&d, 40, 30));
            }
        }
        Cmd::Restore { target, id, to } => {
            let (settings, store) = open_store(&cli)?;
            let fam = family_of(&store, target)?;
            let snaps = store.snapshots(&fam)?;
            let id = resolve_id(&snaps, id)?;
            let snap = snaps.iter().find(|s| s.id == id).unwrap();
            let dest = match to {
                Some(p) => p.clone(),
                None => {
                    let dir = settings.restore_dir.clone().unwrap_or_else(|| {
                        Path::new(&snap.path).parent().map(Path::to_path_buf).unwrap_or_else(|| PathBuf::from("."))
                    });
                    Store::restore_path(&dir, &snap.file_name, &snap.short_id)
                }
            };
            let r = store.restore(&fam, &id, &dest)?;
            println!("wrote {}", r.path.display());
            if let Some(from) = r.playback_from {
                println!("  playback state borrowed from snapshot {}", &from[..7]);
            }
            if !r.omitted.is_empty() {
                println!("  not restored (Dorico regenerates them): {}", r.omitted.join(", "));
            }
        }
        Cmd::Milestone { target, id, name } => {
            let (_, store) = open_store(&cli)?;
            let fam = family_of(&store, target)?;
            let id = resolve_id(&store.snapshots(&fam)?, id)?;
            store.add_milestone(&fam, &id, name)?;
            println!("marked {} as '{name}'", &id[..7]);
        }
        Cmd::MergePreview { target, ours, theirs, base, json, max_auto } => {
            let (_, store) = open_store(&cli)?;
            let fam = family_of(&store, target)?;
            let snaps = store.snapshots(&fam)?;
            let (o, t) = (resolve_id(&snaps, ours)?, resolve_id(&snaps, theirs)?);
            let b = base.as_deref().map(|b| resolve_id(&snaps, b)).transpose()?;
            let p = store.merge_preview(&fam, &o, &t, b.as_deref())?;
            if *json {
                println!("{}", serde_json::to_string_pretty(&p)?);
            } else {
                print!("{}", dorigit_core::merge::render_text(&p, *max_auto));
            }
        }
        Cmd::MergePreviewFiles { base, ours, theirs, json, max_auto } => {
            let read = |p: &PathBuf| -> Result<_> { Ok(build_score(&Project::read(p)?.score()?.root)) };
            let p = dorigit_core::merge::preview(&read(base)?, &read(ours)?, &read(theirs)?);
            if *json {
                println!("{}", serde_json::to_string_pretty(&p)?);
            } else {
                print!("{}", dorigit_core::merge::render_text(&p, *max_auto));
            }
        }
        Cmd::Notation { project, flow, bars, players } => {
            let p = Project::read(project)?;
            let doc = p.score()?;
            let flow_id = match flow {
                Some(f) => f.clone(),
                None => doc.root.find("flows/array").and_then(|a| a.items().first()).map(|f| f.text("flowID").to_owned()).unwrap_or_default(),
            };
            let (a, b) = bars.split_once('-').unwrap_or((bars, bars));
            let req = dorigit_core::notation::Request {
                flow_id,
                from_bar: a.trim().parse()?,
                to_bar: b.trim().parse()?,
                players: (!players.is_empty()).then(|| players.clone()),
                highlights: Vec::new(),
            };
            print!("{}", dorigit_core::notation::render(&doc.root, &req)?);
        }
        Cmd::Variant { cmd } => {
            let (_, store) = open_store(&cli)?;
            match cmd {
                VariantCmd::New { file, name, bars, flow } => {
                    let range = bars.as_deref().map(|b| parse_bars(b, flow.clone())).transpose()?;
                    let (path, _) = store.new_variant(file, name, range)?;
                    println!("made {}", path.display());
                }
                VariantCmd::List { target, json } => {
                    let board = store.variant_board(&family_of(&store, target)?)?;
                    if *json {
                        println!("{}", serde_json::to_string_pretty(&board)?);
                    } else {
                        print_board(&board);
                    }
                }
                VariantCmd::Note { target, variant, notes, tags, rename, bars } => {
                    let fam = family_of(&store, target)?;
                    let v = store
                        .variants(&fam)?
                        .into_iter()
                        .find(|v| v.name == *variant || v.file_name == *variant || v.branch == *variant)
                        .with_context(|| format!("no variant called {variant}"))?;
                    let range = bars.as_deref().map(|b| parse_bars(b, None)).transpose()?;
                    let tags = (!tags.is_empty()).then(|| tags.clone());
                    store.update_variant(&fam, &v.branch, rename.as_deref(), range.map(Some), notes.as_deref(), tags)?;
                    print_board(&store.variant_board(&fam)?.into_iter().filter(|b| b.variant.branch == v.branch).collect::<Vec<_>>());
                }
            }
        }
        Cmd::Watch { dirs } => {
            let (settings, store) = open_store(&cli)?;
            let dirs = if dirs.is_empty() { settings.watch_dirs.clone() } else { dirs.clone() };
            let store = std::sync::Arc::new(store);
            let s2 = store.clone();
            let w = dorigit_core::watch::watch(
                &dirs,
                settings.ignore.clone(),
                settings.store_dir.clone(),
                Duration::from_millis(settings.settle_ms),
                move |p| match s2.snapshot_file(&p, SnapshotKind::Auto, None) {
                    Ok(o) => print_outcome(&p, &o),
                    Err(e) => eprintln!("{}: {e:#}", p.display()),
                },
            )?;
            for d in &w.watching {
                println!("watching {}", d.display());
            }
            for e in &w.errors {
                eprintln!("cannot watch {e}");
            }
            loop {
                std::thread::sleep(Duration::from_secs(3600));
            }
        }
    }
    Ok(())
}

fn setup_git(repo: &Path) -> Result<()> {
    let attrs = repo.join(".gitattributes");
    let line = "*.dorico diff=dorico merge=binary -text";
    let existing = std::fs::read_to_string(&attrs).unwrap_or_default();
    if !existing.lines().any(|l| l.trim() == line) {
        let sep = if existing.is_empty() || existing.ends_with('\n') { "" } else { "\n" };
        std::fs::write(&attrs, format!("{existing}{sep}{line}\n"))?;
    }
    let exe = std::env::current_exe()?.to_string_lossy().replace('\\', "/");
    for (k, v) in [
        ("diff.dorico.textconv", format!("\"{exe}\" show")),
        ("diff.dorico.cachetextconv", "true".into()),
        ("diff.dorico.xfuncname", "^### .*$".into()),
    ] {
        let st = std::process::Command::new("git").arg("-C").arg(repo).args(["config", k, &v]).status()?;
        if !st.success() {
            bail!("git config {k} failed");
        }
    }
    println!("git diff / log -p / show now render *.dorico musically in {}", repo.display());
    Ok(())
}
