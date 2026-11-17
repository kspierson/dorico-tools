//! dorigit desktop app (Tauri 2).
//!
//! Thin layer over `dorigit-core`: commands for the UI, a folder watcher that
//! snapshots on every Dorico save (results are pushed to the UI as `activity`
//! events), and a tray icon so watching continues while the window is closed.
//! Settings are shared with the CLI: `<data dir>/settings.json`.
//! Diagnostics go to `<data dir>/dorigit.log`.
//!
//! Flags: `--hidden` starts in the tray without showing the window (for start-on-login).
//! Env: `DORIGIT_DATA_DIR` overrides the data dir (settings, default store, log).

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use dorico_format::diff::ScoreDiff;
use dorigit_core::manifest::SnapshotKind;
use dorigit_core::store::{FamilyMeta, RestoreOutcome, SnapshotOutcome};
use dorigit_core::merge::Preview as MergePreview;
use dorigit_core::notation::{DiffNotation, Request as NotationRequest};
use dorigit_core::variants::{BarRange, Variant, VariantStatus};
use dorigit_core::watch::{self, FolderWatcher};
use dorigit_core::{Settings, SnapshotInfo, Store};
use serde::Serialize;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};
use std::time::Duration;
use tauri::menu::{Menu, MenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Emitter, Manager, State, WindowEvent};
use tauri_plugin_opener::OpenerExt;

type CmdResult<T> = Result<T, String>;

/// Append a line to <data dir>/dorigit.log (best effort).
fn log(msg: &str) {
    use std::io::Write;
    let dir = dorigit_core::settings::default_data_dir();
    let _ = std::fs::create_dir_all(&dir);
    if let Ok(mut f) = std::fs::OpenOptions::new().create(true).append(true).open(dir.join("dorigit.log")) {
        let t = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0);
        let _ = writeln!(f, "{t} {msg}");
    }
}

fn err(e: impl Into<anyhow::Error>) -> String {
    format!("{:#}", e.into())
}

struct Inner {
    settings: Settings,
    settings_path: PathBuf,
    store: Arc<Store>,
    watcher: Option<FolderWatcher>,
    watching: Vec<String>,
    watch_errors: Vec<String>,
}

struct AppState(Mutex<Inner>);

impl AppState {
    fn store(&self) -> Arc<Store> {
        self.0.lock().unwrap().store.clone()
    }
}

#[derive(Serialize)]
struct Status {
    settings: Settings,
    settings_path: String,
    watching: Vec<String>,
    watch_errors: Vec<String>,
    version: &'static str,
}

/// Pushed to the UI whenever the watcher handles a save.
#[derive(Serialize, Clone)]
#[serde(tag = "type", rename_all = "snake_case")]
enum Activity {
    Snapshot { path: String, outcome: SnapshotOutcome },
    Error { path: String, message: String },
}

#[derive(Serialize)]
struct FamilyView {
    #[serde(flatten)]
    meta: FamilyMeta,
    size: u64,
}

#[derive(Serialize)]
struct ImportItem {
    path: String,
    outcome: Option<SnapshotOutcome>,
    error: Option<String>,
}

fn status_of(inner: &Inner) -> Status {
    Status {
        settings: inner.settings.clone(),
        settings_path: inner.settings_path.to_string_lossy().into(),
        watching: inner.watching.clone(),
        watch_errors: inner.watch_errors.clone(),
        version: env!("CARGO_PKG_VERSION"),
    }
}

/// (Re)start the folder watcher according to the current settings.
fn restart_watcher(app: &AppHandle, inner: &mut Inner) {
    inner.watcher = None;
    inner.watching.clear();
    inner.watch_errors.clear();
    if !inner.settings.auto_snapshot || inner.settings.watch_dirs.is_empty() {
        return;
    }
    let store = inner.store.clone();
    let app2 = app.clone();
    let result = watch::watch(
        &inner.settings.watch_dirs,
        inner.settings.ignore.clone(),
        inner.settings.store_dir.clone(),
        Duration::from_millis(inner.settings.settle_ms),
        move |path| {
            let p = path.to_string_lossy().to_string();
            let activity = match store.snapshot_file(&path, SnapshotKind::Auto, None) {
                Ok(outcome) => {
                    log(&format!(
                        "snapshot {p}: {}",
                        match &outcome {
                            SnapshotOutcome::Created { snapshot } => snapshot.summary.text.clone(),
                            SnapshotOutcome::Unchanged { .. } => "unchanged".into(),
                        }
                    ));
                    Activity::Snapshot { path: p, outcome }
                }
                Err(e) => {
                    log(&format!("snapshot failed {p}: {e:#}"));
                    Activity::Error { path: p, message: format!("{e:#}") }
                }
            };
            let _ = app2.emit("activity", activity);
        },
    );
    match result {
        Ok(w) => {
            inner.watching = w.watching.iter().map(|d| d.to_string_lossy().to_string()).collect();
            inner.watch_errors = w.errors.clone();
            inner.watcher = Some(w);
        }
        Err(e) => inner.watch_errors.push(format!("{e:#}")),
    }
    log(&format!("watching {:?}; errors {:?}", inner.watching, inner.watch_errors));
}

#[tauri::command]
fn status(state: State<AppState>) -> Status {
    log("ui: status requested");
    status_of(&state.0.lock().unwrap())
}

#[tauri::command]
fn save_settings(app: AppHandle, state: State<AppState>, settings: Settings) -> CmdResult<Status> {
    let mut inner = state.0.lock().unwrap();
    settings.save(&inner.settings_path).map_err(err)?;
    inner.store = Arc::new(Store::open(&settings.store_dir, settings.playback.clone()).map_err(err)?);
    inner.settings = settings;
    restart_watcher(&app, &mut inner);
    Ok(status_of(&inner))
}

#[tauri::command]
fn families(state: State<AppState>) -> CmdResult<Vec<FamilyView>> {
    let store = state.store();
    let fams = store.families().map_err(err)?;
    Ok(fams.into_iter().map(|meta| FamilyView { size: store.family_size(&meta.id), meta }).collect())
}

#[tauri::command]
async fn snapshots(state: State<'_, AppState>, family: String) -> CmdResult<Vec<SnapshotInfo>> {
    let store = state.store();
    tauri::async_runtime::spawn_blocking(move || store.snapshots(&family).map_err(err)).await.map_err(err)?
}

#[tauri::command]
async fn diff(state: State<'_, AppState>, family: String, old: Option<String>, new: String) -> CmdResult<ScoreDiff> {
    let store = state.store();
    tauri::async_runtime::spawn_blocking(move || store.diff(&family, old.as_deref(), &new).map_err(err))
        .await
        .map_err(err)?
}

/// PNG bytes of the snapshot's first-page thumbnail (empty if none).
#[tauri::command]
fn thumbnail(state: State<AppState>, family: String, id: String) -> CmdResult<tauri::ipc::Response> {
    let bytes = state.store().thumbnail(&family, &id).map_err(err)?.unwrap_or_default();
    Ok(tauri::ipc::Response::new(bytes))
}

#[tauri::command]
async fn restore(
    app: AppHandle,
    state: State<'_, AppState>,
    family: String,
    id: String,
    open: bool,
) -> CmdResult<RestoreOutcome> {
    let (store, restore_dir) = {
        let inner = state.0.lock().unwrap();
        (inner.store.clone(), inner.settings.restore_dir.clone())
    };
    let outcome = tauri::async_runtime::spawn_blocking(move || -> anyhow::Result<RestoreOutcome> {
        let m = store.manifest(&family, &id)?;
        let dir = restore_dir.unwrap_or_else(|| {
            Path::new(&m.source.path).parent().map(Path::to_path_buf).unwrap_or_else(std::env::temp_dir)
        });
        let dest = Store::restore_path(&dir, &m.source.file_name, &id[..7]);
        store.restore(&family, &id, &dest)
    })
    .await
    .map_err(err)?
    .map_err(err)?;
    if open {
        app.opener().open_path(outcome.path.to_string_lossy(), None::<&str>).map_err(err)?;
    }
    Ok(outcome)
}

#[tauri::command]
async fn snapshot_now(
    state: State<'_, AppState>,
    path: String,
    milestone: Option<String>,
) -> CmdResult<SnapshotOutcome> {
    let store = state.store();
    tauri::async_runtime::spawn_blocking(move || {
        let kind = if milestone.is_some() { SnapshotKind::Manual } else { SnapshotKind::Auto };
        store.snapshot_file(Path::new(&path), kind, milestone.as_deref()).map_err(err)
    })
    .await
    .map_err(err)?
}

/// Before/after notation (MEI) of one flow's changed bars (`notation.rs`).
#[tauri::command]
async fn notation_diff(
    state: State<'_, AppState>,
    family: String,
    old: Option<String>,
    new: String,
    flow_id: String,
) -> CmdResult<DiffNotation> {
    let store = state.store();
    tauri::async_runtime::spawn_blocking(move || {
        store.notation_diff(&family, old.as_deref(), &new, &flow_id).map_err(err)
    })
    .await
    .map_err(err)?
}

/// Notation (MEI) of a bar range of one snapshot.
#[tauri::command]
async fn notation(state: State<'_, AppState>, family: String, id: String, request: NotationRequest) -> CmdResult<String> {
    let store = state.store();
    tauri::async_runtime::spawn_blocking(move || store.notation(&family, &id, &request).map_err(err))
        .await
        .map_err(err)?
}

/// Merge preview of two snapshots (base: their common ancestor unless given).
#[tauri::command]
async fn merge_preview(
    state: State<'_, AppState>,
    family: String,
    ours: String,
    theirs: String,
    base: Option<String>,
) -> CmdResult<MergePreview> {
    let store = state.store();
    tauri::async_runtime::spawn_blocking(move || {
        store.merge_preview(&family, &ours, &theirs, base.as_deref()).map_err(err)
    })
    .await
    .map_err(err)?
}

#[tauri::command]
async fn variant_board(state: State<'_, AppState>, family: String) -> CmdResult<Vec<VariantStatus>> {
    let store = state.store();
    tauri::async_runtime::spawn_blocking(move || store.variant_board(&family).map_err(err)).await.map_err(err)?
}

#[derive(Serialize)]
struct NewVariant {
    path: String,
    variant: Variant,
}

#[tauri::command]
async fn new_variant(
    state: State<'_, AppState>,
    path: String,
    name: String,
    bars: Option<BarRange>,
) -> CmdResult<NewVariant> {
    let store = state.store();
    tauri::async_runtime::spawn_blocking(move || {
        let (p, variant) = store.new_variant(Path::new(&path), &name, bars).map_err(err)?;
        Ok(NewVariant { path: p.to_string_lossy().into_owned(), variant })
    })
    .await
    .map_err(err)?
}

/// `bars`: send `clear_bars: true` to remove the given range.
#[tauri::command]
#[allow(clippy::too_many_arguments)]
fn update_variant(
    state: State<AppState>,
    family: String,
    branch: String,
    name: Option<String>,
    notes: Option<String>,
    tags: Option<Vec<String>>,
    bars: Option<BarRange>,
    clear_bars: Option<bool>,
) -> CmdResult<Variant> {
    let bars = if clear_bars == Some(true) { Some(None) } else { bars.map(Some) };
    state.store().update_variant(&family, &branch, name.as_deref(), bars, notes.as_deref(), tags).map_err(err)
}

#[tauri::command]
fn add_milestone(state: State<AppState>, family: String, id: String, name: String) -> CmdResult<()> {
    state.store().add_milestone(&family, &id, &name).map_err(err)
}

#[tauri::command]
fn remove_milestone(state: State<AppState>, family: String, id: String, name: String) -> CmdResult<()> {
    state.store().remove_milestone(&family, &id, &name).map_err(err)
}

#[tauri::command]
async fn import_files(state: State<'_, AppState>, paths: Vec<String>) -> CmdResult<Vec<ImportItem>> {
    let store = state.store();
    tauri::async_runtime::spawn_blocking(move || {
        let paths: Vec<PathBuf> = paths.into_iter().map(PathBuf::from).collect();
        store
            .import(&paths)
            .into_iter()
            .map(|(p, r)| {
                let path = p.to_string_lossy().to_string();
                match r {
                    Ok(o) => ImportItem { path, outcome: Some(o), error: None },
                    Err(e) => ImportItem { path, outcome: None, error: Some(format!("{e:#}")) },
                }
            })
            .collect()
    })
    .await
    .map_err(err)
}

#[tauri::command]
fn open_path(app: AppHandle, path: String) -> CmdResult<()> {
    app.opener().open_path(path, None::<&str>).map_err(err)
}

#[tauri::command]
fn reveal(app: AppHandle, path: String) -> CmdResult<()> {
    app.opener().reveal_item_in_dir(path).map_err(err)
}

fn show_main(app: &AppHandle) {
    if let Some(w) = app.get_webview_window("main") {
        let _ = w.show();
        let _ = w.unminimize();
        let _ = w.set_focus();
    }
}

fn main() {
    let start_hidden = std::env::args().any(|a| a == "--hidden");
    log(&format!("starting dorigit {} (hidden: {start_hidden})", env!("CARGO_PKG_VERSION")));
    let settings_path = dorigit_core::settings::default_data_dir().join("settings.json");
    let settings = Settings::load(&settings_path);
    if !settings_path.exists() {
        let _ = settings.save(&settings_path);
    }
    let store =
        Arc::new(Store::open(&settings.store_dir, settings.playback.clone()).expect("cannot open history store"));

    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| show_main(app)))
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .manage(AppState(Mutex::new(Inner {
            settings,
            settings_path,
            store,
            watcher: None,
            watching: Vec::new(),
            watch_errors: Vec::new(),
        })))
        .setup(move |app| {
            let handle = app.handle().clone();
            if !start_hidden {
                show_main(&handle);
            }
            {
                let state = app.state::<AppState>();
                let mut inner = state.0.lock().unwrap();
                restart_watcher(&handle, &mut inner);
            }

            let show = MenuItem::with_id(app, "show", "Open dorigit", true, None::<&str>)?;
            let quit = MenuItem::with_id(app, "quit", "Quit (stop watching)", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&show, &quit])?;
            let mut tray = TrayIconBuilder::with_id("main").tooltip("dorigit: watching Dorico projects").menu(&menu);
            if let Some(icon) = app.default_window_icon() {
                tray = tray.icon(icon.clone());
            }
            tray.on_menu_event(|app, event| match event.id.as_ref() {
                "show" => show_main(app),
                "quit" => app.exit(0),
                _ => {}
            })
            .on_tray_icon_event(|tray, event| {
                if let TrayIconEvent::Click { button: MouseButton::Left, button_state: MouseButtonState::Up, .. } =
                    event
                {
                    show_main(tray.app_handle());
                }
            })
            .build(app)?;
            Ok(())
        })
        .on_window_event(|window, event| {
            // Closing the window keeps dorigit running in the tray so saves are still captured.
            if let WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                let _ = window.hide();
            }
        })
        .invoke_handler(tauri::generate_handler![
            status,
            save_settings,
            families,
            snapshots,
            diff,
            thumbnail,
            restore,
            snapshot_now,
            add_milestone,
            remove_milestone,
            import_files,
            variant_board,
            merge_preview,
            notation_diff,
            notation,
            new_variant,
            update_variant,
            open_path,
            reveal,
        ])
        .run(tauri::generate_context!())
        .expect("error while running dorigit");
}
