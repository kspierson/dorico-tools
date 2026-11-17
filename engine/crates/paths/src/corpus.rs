//! Test corpora (`engine/tests/corpus.toml`): the user's projects, Finale archive, HP
//! captures and the shared Dorico test files. Tests read these and never write to them.
//!
//! The file is found through `DORICO_CORPUS_FILE`, else at its place in this repo. Each
//! `[corpus]` entry can be overridden with `DORICO_<NAME>` (e.g. `DORICO_PROJECTS`).
//! Relative paths are relative to the repo root.

use anyhow::{Context, Result};
use serde::Deserialize;
use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

#[derive(Debug, Deserialize)]
struct File {
    corpus: BTreeMap<String, toml::Value>,
}

/// Loaded corpus locations. Paths are host paths (converted from Windows form if needed).
#[derive(Debug, Clone)]
pub struct Corpus {
    pub root: PathBuf,
    entries: BTreeMap<String, PathBuf>,
}

/// The repo root (three levels above this crate's folder, `engine/crates/paths`).
pub fn repo_root() -> PathBuf {
    let here = Path::new(env!("CARGO_MANIFEST_DIR"));
    here.ancestors().nth(3).map(Path::to_path_buf).unwrap_or_else(|| here.to_path_buf())
}

impl Corpus {
    pub fn load() -> Result<Corpus> {
        let root = repo_root();
        let file = std::env::var("DORICO_CORPUS_FILE")
            .map(PathBuf::from)
            .unwrap_or_else(|_| root.join("engine/tests/corpus.toml"));
        let text = std::fs::read_to_string(&file).with_context(|| format!("reading {}", file.display()))?;
        Self::parse(&text, root)
    }

    fn parse(text: &str, root: PathBuf) -> Result<Corpus> {
        let f: File = toml::from_str(text).context("parsing corpus.toml")?;
        let mut entries = BTreeMap::new();
        let resolve = |s: &str| {
            let p = crate::to_host(s);
            if p.is_absolute() { p } else { root.join(p) }
        };
        for (k, v) in &f.corpus {
            if let toml::Value::String(s) = v {
                let s = std::env::var(format!("DORICO_{}", k.to_ascii_uppercase())).unwrap_or_else(|_| s.clone());
                entries.insert(k.clone(), resolve(&s));
            }
        }
        // [corpus.projects_used]: file names inside `projects`
        if let (Some(toml::Value::Table(used)), Some(projects)) =
            (f.corpus.get("projects_used"), entries.get("projects").cloned())
        {
            for (k, v) in used {
                if let Some(s) = v.as_str() {
                    entries.insert(k.clone(), projects.join(s));
                }
            }
        }
        Ok(Corpus { root, entries })
    }

    /// A corpus path by name (`projects`, `finale_scores`, `test_files`, `hp_main`, ...).
    pub fn get(&self, name: &str) -> Option<&Path> {
        self.entries.get(name).map(PathBuf::as_path)
    }

    /// A corpus path only if it exists on this machine (tests skip when it doesn't).
    pub fn available(&self, name: &str) -> Option<&Path> {
        self.get(name).filter(|p| p.exists())
    }

    pub fn names(&self) -> impl Iterator<Item = &str> {
        self.entries.keys().map(String::as_str)
    }

    /// `.dorico` files directly inside a corpus folder, sorted (empty if the folder is missing).
    pub fn dorico_files(&self, name: &str) -> Vec<PathBuf> {
        let Some(dir) = self.available(name) else { return Vec::new() };
        let mut files: Vec<PathBuf> =
            std::fs::read_dir(dir).map(|rd| rd.flatten().map(|e| e.path()).collect()).unwrap_or_default();
        files.retain(|p| p.is_file() && p.extension().is_some_and(|x| x == "dorico"));
        files.sort();
        files
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_and_resolves() {
        let c = Corpus::parse(
            "[corpus]\nprojects = '/x/Dorico Projects'\ntest_files = 'engine/tests/dorico-files'\n\
             [corpus.projects_used]\nmain = 'A.dorico'\n",
            PathBuf::from("/repo"),
        )
        .unwrap();
        assert_eq!(c.get("test_files").unwrap(), Path::new("/repo/engine/tests/dorico-files"));
        assert_eq!(c.get("main").unwrap(), Path::new("/x/Dorico Projects/A.dorico"));
        assert!(c.get("nope").is_none());
    }

    #[test]
    fn repo_corpus_file_loads() {
        let c = Corpus::load().unwrap();
        assert!(c.get("projects").is_some() && c.get("test_files").is_some());
    }
}
