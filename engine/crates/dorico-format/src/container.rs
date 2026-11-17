//! The `.dorico` container: a zip (OCF layout) of score, library and extras.

use crate::dtn::{self, Document};
use crate::xml;
use anyhow::{Context, Result, bail};
use serde::{Deserialize, Serialize};
use std::io::{Cursor, Read, Seek, Write};
use std::path::Path;
use zip::write::SimpleFileOptions;
use zip::{CompressionMethod, DateTime, ZipArchive, ZipWriter};

pub const SCORE: &str = "score";
pub const SCORE_LIBRARY: &str = "scorelibrary";
pub const ENGINE_DATA: &str = "supplementary_data/vstaudioengine/enginedata";
pub const PREVIEW_PNG: &str = "supplementary_data/preview/preview.png";
pub const PREVIEW_PDF: &str = "supplementary_data/preview/preview.pdf";

/// Zip timestamp, kept so rebuilt files match the original.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct ZipTime(pub u16, pub u8, pub u8, pub u8, pub u8, pub u8);

#[derive(Debug, Clone)]
pub struct Entry {
    pub name: String,
    pub data: Vec<u8>,
    pub is_dir: bool,
    pub time: ZipTime,
    pub deflated: bool,
}

#[derive(Debug, Clone, Default)]
pub struct Project {
    pub entries: Vec<Entry>,
}

impl Project {
    pub fn read(path: &Path) -> Result<Project> {
        let bytes = std::fs::read(path).with_context(|| format!("reading {}", path.display()))?;
        Self::from_bytes(&bytes).with_context(|| format!("opening {}", path.display()))
    }

    pub fn from_bytes(bytes: &[u8]) -> Result<Project> {
        Self::from_reader(Cursor::new(bytes))
    }

    pub fn from_reader(r: impl Read + Seek) -> Result<Project> {
        let mut zip = ZipArchive::new(r).context("not a zip / .dorico file")?;
        let mut entries = Vec::with_capacity(zip.len());
        for i in 0..zip.len() {
            let mut f = zip.by_index(i)?;
            let t = f.last_modified().unwrap_or_default();
            let mut data = Vec::with_capacity(f.size() as usize);
            f.read_to_end(&mut data)?;
            entries.push(Entry {
                name: f.name().to_owned(),
                is_dir: f.is_dir(),
                time: ZipTime(t.year(), t.month(), t.day(), t.hour(), t.minute(), t.second()),
                deflated: f.compression() != CompressionMethod::Stored,
                data,
            });
        }
        Ok(Project { entries })
    }

    pub fn get(&self, name: &str) -> Option<&Entry> {
        self.entries.iter().find(|e| e.name == name)
    }

    /// Load `score` or `scorelibrary`, whether stored as `.dtn` or `.xml`.
    pub fn document(&self, part: &str) -> Result<Document> {
        if let Some(e) = self.get(&format!("{part}.dtn")) {
            return dtn::decode(&e.data).with_context(|| format!("decoding {part}.dtn"));
        }
        if let Some(e) = self.get(&format!("{part}.xml")) {
            return xml::from_xml(&e.data).with_context(|| format!("parsing {part}.xml"));
        }
        bail!("project has no {part}.dtn or {part}.xml")
    }

    pub fn score(&self) -> Result<Document> {
        self.document(SCORE)
    }

    pub fn write(&self, path: &Path) -> Result<()> {
        let bytes = self.to_bytes()?;
        std::fs::write(path, bytes).with_context(|| format!("writing {}", path.display()))
    }

    pub fn to_bytes(&self) -> Result<Vec<u8>> {
        let mut zip = ZipWriter::new(Cursor::new(Vec::new()));
        for e in &self.entries {
            let ZipTime(y, mo, d, h, mi, s) = e.time;
            let time = DateTime::from_date_and_time(y, mo, d, h, mi, s).unwrap_or_default();
            let opts = SimpleFileOptions::default()
                .compression_method(if e.deflated { CompressionMethod::Deflated } else { CompressionMethod::Stored })
                .last_modified_time(time)
                .large_file(e.data.len() > u32::MAX as usize / 2);
            if e.is_dir && !e.deflated {
                zip.add_directory(e.name.trim_end_matches('/'), opts)?;
            } else if e.is_dir {
                // Dorico writes folders as empty *deflated* entries (2-byte stream); add_directory
                // would store them, so write the folder as an empty file named "x/" instead.
                let name = format!("{}/", e.name.trim_end_matches('/'));
                zip.start_file(name, opts)?;
            } else {
                zip.start_file(e.name.as_str(), opts)?;
                zip.write_all(&e.data)?;
            }
        }
        Ok(zip.finish()?.into_inner())
    }
}

/// Quick check that a file on disk is a complete, readable .dorico (used by
/// the watcher to wait until Dorico has finished writing).
pub fn is_complete(path: &Path) -> bool {
    std::fs::File::open(path)
        .ok()
        .and_then(|f| ZipArchive::new(std::io::BufReader::new(f)).ok())
        .is_some_and(|z| z.file_names().any(|n| n.starts_with("score.")))
}
