//! Where things are, in one place for every tool.
//!
//! - [`host`]: are we on Windows, in WSL, on macOS or plain Linux?
//! - [`to_host`] / [`to_windows`]: convert between Windows paths (`C:\…`,
//!   `\\wsl.localhost\<distro>\…`) and the paths this process can open (`/mnt/c/…`).
//! - [`dorico_installs`] / [`dorico_install`]: the Dorico program folders (factory data).
//! - [`user_home`], [`dorico_appdata`], [`documents`], [`dorico_projects`]: the user's
//!   Windows profile and Dorico's per-user data.
//! - [`corpus`]: the test corpora listed in `engine/tests/corpus.toml`.
//!
//! Every lookup can be overridden with an environment variable (see each function), so tests
//! and other machines never need code changes.

use std::path::{Path, PathBuf};

pub mod corpus;

/// The kind of machine we run on.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Host {
    Windows,
    /// WSL, with the distribution name (for `\\wsl.localhost\<distro>\…` paths).
    Wsl {
        distro: String,
    },
    Mac,
    Linux,
}

pub fn host() -> Host {
    if cfg!(windows) {
        return Host::Windows;
    }
    if cfg!(target_os = "macos") {
        return Host::Mac;
    }
    if let Ok(distro) = std::env::var("WSL_DISTRO_NAME") {
        return Host::Wsl { distro };
    }
    let release = std::fs::read_to_string("/proc/sys/kernel/osrelease").unwrap_or_default();
    if release.to_ascii_lowercase().contains("microsoft") {
        let distro = std::fs::read_to_string("/etc/os-release")
            .ok()
            .and_then(|s| s.lines().find_map(|l| l.strip_prefix("NAME=").map(|v| v.trim_matches('"').to_owned())))
            .unwrap_or_else(|| "Ubuntu".into());
        return Host::Wsl { distro };
    }
    Host::Linux
}

/// Turn a path written for Windows into one this process can open.
///
/// In WSL: `C:\Users\x` → `/mnt/c/Users/x`, `\\wsl.localhost\Distro\home\x` (or `\\wsl$\…`) →
/// `/home/x`. On other hosts the path is returned unchanged (with `\` kept).
pub fn to_host(path: &str) -> PathBuf {
    match host() {
        Host::Wsl { .. } => PathBuf::from(windows_to_wsl(path)),
        _ => PathBuf::from(path),
    }
}

/// Turn a path this process uses into the form Windows programs (Dorico) understand.
///
/// In WSL: `/mnt/c/Users/x` → `C:\Users\x`, `/home/x` → `\\wsl.localhost\<distro>\home\x`.
/// On Windows the path is returned as is. Elsewhere there is no Windows form: `None`.
pub fn to_windows(path: &Path) -> Option<String> {
    match host() {
        Host::Windows => Some(path.to_string_lossy().into_owned()),
        Host::Wsl { distro } => Some(wsl_to_windows(&path.to_string_lossy(), &distro)),
        _ => None,
    }
}

/// Pure string conversion behind [`to_host`] (exposed for tests and tools).
pub fn windows_to_wsl(path: &str) -> String {
    let p = path.replace('\\', "/");
    for prefix in ["//wsl.localhost/", "//wsl$/"] {
        if let Some(rest) = p.strip_prefix(prefix) {
            // drop the distro name
            return match rest.split_once('/') {
                Some((_, tail)) => format!("/{tail}"),
                None => "/".into(),
            };
        }
    }
    let b = p.as_bytes();
    if b.len() >= 2 && b[1] == b':' && b[0].is_ascii_alphabetic() {
        let drive = (b[0] as char).to_ascii_lowercase();
        let rest = p[2..].trim_start_matches('/');
        return if rest.is_empty() { format!("/mnt/{drive}") } else { format!("/mnt/{drive}/{rest}") };
    }
    p
}

/// Pure string conversion behind [`to_windows`] (exposed for tests and tools).
pub fn wsl_to_windows(path: &str, distro: &str) -> String {
    if let Some(rest) = path.strip_prefix("/mnt/") {
        let (drive, tail) = rest.split_once('/').unwrap_or((rest, ""));
        if drive.len() == 1 && drive.as_bytes()[0].is_ascii_alphabetic() {
            return format!("{}:\\{}", drive.to_ascii_uppercase(), tail.replace('/', "\\"));
        }
    }
    format!("\\\\wsl.localhost\\{distro}{}", path.replace('/', "\\"))
}

// ---------------------------------------------------------------------------
// Dorico program folders
// ---------------------------------------------------------------------------

/// A Dorico program folder (holds `instruments.xml` and the other factory data).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DoricoInstall {
    pub dir: PathBuf,
    /// Major version from the folder name (`Dorico5` → 5), if it has one.
    pub version: Option<u32>,
}

fn program_files() -> Vec<PathBuf> {
    match host() {
        Host::Windows => {
            let pf = std::env::var("ProgramFiles").unwrap_or_else(|_| r"C:\Program Files".into());
            vec![PathBuf::from(pf).join("Steinberg")]
        }
        Host::Wsl { .. } => vec![PathBuf::from("/mnt/c/Program Files/Steinberg")],
        Host::Mac => vec![PathBuf::from("/Applications")],
        Host::Linux => Vec::new(),
    }
}

fn version_of(name: &str) -> Option<u32> {
    let digits: String = name.trim_start_matches("Dorico").trim().chars().take_while(|c| c.is_ascii_digit()).collect();
    digits.parse().ok()
}

/// Every Dorico install found, newest major version first.
///
/// `DORICO_INSTALL` (a folder, Windows or host form) is listed first when set.
pub fn dorico_installs() -> Vec<DoricoInstall> {
    let mut out = Vec::new();
    if let Ok(dir) = std::env::var("DORICO_INSTALL") {
        let dir = to_host(&dir);
        if dir.join("instruments.xml").is_file() {
            let version = dir.file_name().and_then(|n| version_of(&n.to_string_lossy()));
            out.push(DoricoInstall { dir, version });
        }
    }
    let mut found = Vec::new();
    for base in program_files() {
        let Ok(rd) = std::fs::read_dir(&base) else { continue };
        for e in rd.flatten() {
            let name = e.file_name().to_string_lossy().into_owned();
            if !name.starts_with("Dorico") {
                continue;
            }
            // macOS keeps the data inside the app bundle
            let dir = if name.ends_with(".app") { e.path().join("Contents/Resources") } else { e.path() };
            if dir.join("instruments.xml").is_file() {
                found.push(DoricoInstall { dir, version: version_of(name.trim_end_matches(".app")) });
            }
        }
    }
    found.sort_by(|a, b| b.version.cmp(&a.version).then(a.dir.cmp(&b.dir)));
    for f in found {
        if !out.iter().any(|o| o.dir == f.dir) {
            out.push(f);
        }
    }
    out
}

/// The install to use: `DORICO_INSTALL` if set, else the given major version, else the newest.
pub fn dorico_install(version: Option<u32>) -> Option<DoricoInstall> {
    let all = dorico_installs();
    if std::env::var("DORICO_INSTALL").is_ok() {
        return all.into_iter().next();
    }
    match version {
        Some(v) => all.into_iter().find(|i| i.version == Some(v)),
        None => all.into_iter().next(),
    }
}

// ---------------------------------------------------------------------------
// The user's Windows profile
// ---------------------------------------------------------------------------

/// The user's home folder as this process sees it (`C:\Users\x` → `/mnt/c/Users/x` in WSL).
///
/// Override with `DORICO_USER_HOME`. In WSL the Windows profile is the folder under
/// `/mnt/c/Users` that has Steinberg data (first by name if several).
pub fn user_home() -> Option<PathBuf> {
    if let Ok(h) = std::env::var("DORICO_USER_HOME") {
        return Some(to_host(&h));
    }
    match host() {
        Host::Windows => std::env::var("USERPROFILE").ok().map(PathBuf::from),
        Host::Wsl { .. } => {
            let mut users: Vec<PathBuf> = std::fs::read_dir("/mnt/c/Users")
                .ok()?
                .flatten()
                .map(|e| e.path())
                .filter(|p| p.join("AppData/Roaming/Steinberg").is_dir())
                .collect();
            users.sort();
            users.into_iter().next()
        }
        Host::Mac | Host::Linux => std::env::var("HOME").ok().map(PathBuf::from),
    }
}

/// Dorico's per-user data for a major version (expression maps in `EndpointConfigs`,
/// preferences, user library). Windows: `%APPDATA%\Steinberg\Dorico N`;
/// macOS: `~/Library/Preferences/Dorico N`. Override with `DORICO_APPDATA`.
pub fn dorico_appdata(version: u32) -> Option<PathBuf> {
    if let Ok(p) = std::env::var("DORICO_APPDATA") {
        return Some(to_host(&p));
    }
    let home = user_home()?;
    let p = match host() {
        Host::Mac => home.join(format!("Library/Preferences/Dorico {version}")),
        _ => home.join(format!("AppData/Roaming/Steinberg/Dorico {version}")),
    };
    p.is_dir().then_some(p)
}

/// The user's Documents folder. Override with `DORICO_DOCUMENTS`.
pub fn documents() -> Option<PathBuf> {
    if let Ok(p) = std::env::var("DORICO_DOCUMENTS") {
        return Some(to_host(&p));
    }
    Some(user_home()?.join("Documents"))
}

/// Dorico's default project folder, `Documents/Dorico Projects`. Override with `DORICO_PROJECTS`.
pub fn dorico_projects() -> Option<PathBuf> {
    if let Ok(p) = std::env::var("DORICO_PROJECTS") {
        return Some(to_host(&p));
    }
    Some(documents()?.join("Dorico Projects"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn windows_wsl_round_trip() {
        assert_eq!(windows_to_wsl(r"C:\Users\kspie\Documents"), "/mnt/c/Users/kspie/Documents");
        assert_eq!(windows_to_wsl(r"G:\Scores"), "/mnt/g/Scores");
        assert_eq!(windows_to_wsl("D:"), "/mnt/d");
        assert_eq!(windows_to_wsl(r"\\wsl.localhost\Ubuntu-26.04\home\ken\x.dorico"), "/home/ken/x.dorico");
        assert_eq!(windows_to_wsl(r"\\wsl$\Ubuntu\tmp"), "/tmp");
        assert_eq!(windows_to_wsl("/already/posix"), "/already/posix");

        assert_eq!(wsl_to_windows("/mnt/c/Users/kspie", "U"), r"C:\Users\kspie");
        assert_eq!(wsl_to_windows("/mnt/g/", "U"), r"G:\");
        assert_eq!(
            wsl_to_windows("/home/ken/a b.dorico", "Ubuntu-26.04"),
            r"\\wsl.localhost\Ubuntu-26.04\home\ken\a b.dorico"
        );
        // /mnt/<not a drive> is a normal Linux path
        assert_eq!(wsl_to_windows("/mnt/wslg/x", "U"), r"\\wsl.localhost\U\mnt\wslg\x");
        for p in ["/mnt/c/Program Files/Steinberg", "/home/ken/dev"] {
            assert_eq!(windows_to_wsl(&wsl_to_windows(p, "U")), p);
        }
    }

    #[test]
    fn versions_from_folder_names() {
        assert_eq!(version_of("Dorico5"), Some(5));
        assert_eq!(version_of("Dorico 6"), Some(6));
        assert_eq!(version_of("Dorico3.5"), Some(3));
        assert_eq!(version_of("Dorico"), None);
    }
}
