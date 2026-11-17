//! `doricokit._native`: the engine crates seen from Python.
//!
//! This is the temporary bridge of Project S (PLANNED_WORK.md §2.4): Python tools call the one
//! Rust implementation through it until they are ported, then it is removed (S14).
//!
//! Trees cross the boundary as plain Python objects of the classes `doricokit.format` defines
//! (`Node`, `Document`), because the Python tools edit trees in place (`node.value = ...`,
//! `node.children.append(...)`). Rust does all the parsing and writing; Python only holds the
//! data. Tag and value strings are shared Python objects, one per distinct string, as in the
//! old pure-Python decoder.

use dorico_format::container::{Entry, Project, ZipTime};
use dorico_format::dtn::{self, Document, Node, Str};
use dorico_format::ratio::{Ratio, TICKS_PER_CROTCHET};
use dorico_format::{ids, xml};
use pyo3::exceptions::{PyTypeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyDict, PyList, PyString, PyTuple};
use pyo3::{IntoPyObjectExt, intern};
use std::collections::HashMap;
use std::path::{Path, PathBuf};

fn err(e: anyhow::Error) -> PyErr {
    PyValueError::new_err(format!("{e:#}"))
}

// ---------------------------------------------------------------------------
// Rust tree -> Python objects
// ---------------------------------------------------------------------------

struct ToPy<'py> {
    py: Python<'py>,
    node_cls: Bound<'py, PyAny>,
    strings: HashMap<usize, Bound<'py, PyString>>,
}

impl<'py> ToPy<'py> {
    fn string(&mut self, s: &Str) -> Bound<'py, PyString> {
        // decode() shares one Arc per distinct table string; key on its address
        let key = s.as_ptr() as usize;
        self.strings.entry(key).or_insert_with(|| PyString::new(self.py, s)).clone()
    }

    fn node(&mut self, n: &Node) -> PyResult<Bound<'py, PyAny>> {
        let tag = self.string(&n.tag);
        let (value, children) = match &n.value {
            Some(v) => (self.string(v).into_any(), self.py.None().into_bound(self.py)),
            None => {
                let kids = n.children.iter().map(|c| self.node(c)).collect::<PyResult<Vec<_>>>()?;
                (self.py.None().into_bound(self.py), PyList::new(self.py, kids)?.into_any())
            }
        };
        self.node_cls.call1((tag, value, n.array, children))
    }
}

fn doc_to_py<'py>(
    py: Python<'py>,
    doc: &Document,
    node_cls: Bound<'py, PyAny>,
    doc_cls: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let mut b = ToPy { py, node_cls, strings: HashMap::new() };
    let root = b.node(&doc.root)?;
    doc_cls.call1((root, doc.marker))
}

// ---------------------------------------------------------------------------
// Python objects -> Rust tree
// ---------------------------------------------------------------------------

struct FromPy {
    strings: HashMap<String, Str>,
}

impl FromPy {
    fn string(&mut self, s: &Bound<'_, PyAny>) -> PyResult<Str> {
        let s = s.cast::<PyString>().map_err(|_| PyTypeError::new_err("Node.tag and Node.value must be str"))?;
        let s = s.to_str()?;
        if let Some(v) = self.strings.get(s) {
            return Ok(v.clone());
        }
        let v: Str = s.into();
        self.strings.insert(s.to_owned(), v.clone());
        Ok(v)
    }

    /// Same rule as the old Python encoder: a node with `children` (even an empty list) is an
    /// element; otherwise it is a leaf and must have a `value`.
    fn node(&mut self, o: &Bound<'_, PyAny>) -> PyResult<Node> {
        let py = o.py();
        let tag = self.string(&o.getattr(intern!(py, "tag"))?)?;
        let array = o.getattr(intern!(py, "array"))?.is_truthy()?;
        let children = o.getattr(intern!(py, "children"))?;
        if !children.is_none() {
            let mut kids = Vec::new();
            for c in children.try_iter()? {
                kids.push(self.node(&c?)?);
            }
            return Ok(Node { tag, value: None, array, children: kids });
        }
        let value = o.getattr(intern!(py, "value"))?;
        if value.is_none() {
            return Err(PyValueError::new_err(format!("node <{tag}> has neither a value nor children")));
        }
        Ok(Node { tag, value: Some(self.string(&value)?), array, children: Vec::new() })
    }
}

fn doc_from_py(doc: &Bound<'_, PyAny>) -> PyResult<Document> {
    let py = doc.py();
    let root = FromPy { strings: HashMap::new() }.node(&doc.getattr(intern!(py, "root"))?)?;
    let marker: u8 = doc.getattr(intern!(py, "marker"))?.extract()?;
    Ok(Document { root, marker })
}

// ---------------------------------------------------------------------------
// DTN and XML
// ---------------------------------------------------------------------------

/// Decode `score.dtn` / `scorelibrary.dtn` bytes into `doc_cls(node_cls(...), marker)`.
#[pyfunction]
fn dtn_decode<'py>(
    py: Python<'py>,
    data: &[u8],
    node_cls: Bound<'py, PyAny>,
    doc_cls: Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let doc = py.detach(|| dtn::decode(data)).map_err(err)?;
    doc_to_py(py, &doc, node_cls, &doc_cls)
}

#[pyfunction]
fn dtn_encode<'py>(py: Python<'py>, doc: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyBytes>> {
    let d = doc_from_py(doc)?;
    let bytes = py.detach(|| dtn::encode(&d));
    Ok(PyBytes::new(py, &bytes))
}

#[pyfunction]
#[pyo3(signature = (doc, with_marker = true))]
fn xml_write(py: Python<'_>, doc: &Bound<'_, PyAny>, with_marker: bool) -> PyResult<String> {
    let d = doc_from_py(doc)?;
    Ok(py.detach(|| xml::to_xml(&d, with_marker)))
}

#[pyfunction]
fn xml_read<'py>(
    py: Python<'py>,
    data: &[u8],
    node_cls: Bound<'py, PyAny>,
    doc_cls: Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let doc = py.detach(|| xml::from_xml(data)).map_err(err)?;
    doc_to_py(py, &doc, node_cls, &doc_cls)
}

// ---------------------------------------------------------------------------
// positions and IDs
// ---------------------------------------------------------------------------

/// Parse a Dorico position/duration (`"81/4"`, `"3"`, `"1.5"`) to `(numerator, denominator)`;
/// invalid text gives `(0, 1)`, like the tools' lenient `frac()`.
#[pyfunction]
fn ratio_parse(s: &str) -> (i128, i128) {
    let r = Ratio::parse(s);
    (r.numer(), r.denom())
}

/// Dorico's text for `n/d` (`"3/2"`, `"2"`), reduced.
#[pyfunction]
fn ratio_format(n: i128, d: i128) -> PyResult<String> {
    if d == 0 {
        return Err(PyValueError::new_err("zero denominator"));
    }
    Ok(Ratio::new(n, d).to_string())
}

#[pyfunction]
fn ratio_to_ticks(n: i128, d: i128) -> PyResult<i128> {
    if d == 0 {
        return Err(PyValueError::new_err("zero denominator"));
    }
    Ok(Ratio::new(n, d).to_ticks())
}

/// Problems with `idGenerators` (counters at or below IDs in use); empty when fine.
#[pyfunction]
fn ids_check(py: Python<'_>, doc: &Bound<'_, PyAny>) -> PyResult<Vec<String>> {
    let d = doc_from_py(doc)?;
    Ok(py.detach(|| ids::check(&d.root)))
}

// ---------------------------------------------------------------------------
// read model
// ---------------------------------------------------------------------------

/// The read model (engine/crates/dorico-model) of a `.dorico` file's bytes, as JSON text.
#[pyfunction]
fn model_json(py: Python<'_>, data: &[u8]) -> PyResult<String> {
    py.detach(|| -> anyhow::Result<String> {
        let p = Project::from_bytes(data)?;
        let s = dorico_model::read_project(&p)?;
        Ok(serde_json::to_string(&s)?)
    })
    .map_err(err)
}

/// dorigit's listing model (`dorico_format::model`: flows, events with owner/lane/bar/beat,
/// flattened options) of a `.dorico` file's bytes, as JSON text.
#[pyfunction]
fn listing_json(py: Python<'_>, data: &[u8]) -> PyResult<String> {
    py.detach(|| -> anyhow::Result<String> {
        let p = Project::from_bytes(data)?;
        let s = dorico_format::model::build_score(&p.score()?.root);
        Ok(serde_json::to_string(&s)?)
    })
    .map_err(err)
}

// ---------------------------------------------------------------------------
// .dorico container (zip)
// ---------------------------------------------------------------------------

/// Entries as `(name, data, is_dir, (y, mo, d, h, mi, s), deflated)` tuples, in zip order.
#[pyfunction]
fn zip_read<'py>(py: Python<'py>, data: &[u8]) -> PyResult<Bound<'py, PyList>> {
    let p = py.detach(|| Project::from_bytes(data)).map_err(err)?;
    let items = p
        .entries
        .iter()
        .map(|e| {
            let ZipTime(y, mo, d, h, mi, s) = e.time;
            (e.name.as_str(), PyBytes::new(py, &e.data), e.is_dir, (y, mo, d, h, mi, s), e.deflated)
                .into_bound_py_any(py)
        })
        .collect::<PyResult<Vec<_>>>()?;
    PyList::new(py, items)
}

/// One zip entry as Python sees it: `(name, data, is_dir, (y, mo, d, h, mi, s), deflated)`.
type PyEntry = (String, Vec<u8>, bool, (u16, u8, u8, u8, u8, u8), bool);

/// Build a zip from entries shaped like [`zip_read`]'s.
#[pyfunction]
fn zip_write<'py>(py: Python<'py>, entries: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyBytes>> {
    let mut out = Vec::new();
    for item in entries.try_iter()? {
        let t = item?;
        let t = t.cast::<PyTuple>().map_err(|_| PyTypeError::new_err("zip entries must be tuples"))?;
        let (name, data, is_dir, time, deflated): PyEntry = t.extract()?;
        let (y, mo, d, h, mi, s) = time;
        out.push(Entry { name, data, is_dir, time: ZipTime(y, mo, d, h, mi, s), deflated });
    }
    let p = Project { entries: out };
    let bytes = py.detach(|| p.to_bytes()).map_err(err)?;
    Ok(PyBytes::new(py, &bytes))
}

// ---------------------------------------------------------------------------
// paths
// ---------------------------------------------------------------------------

fn path_str(p: &Path) -> String {
    p.to_string_lossy().into_owned()
}

/// "windows", "wsl", "mac" or "linux", plus the WSL distro name ("" elsewhere).
#[pyfunction]
fn host() -> (String, String) {
    match dorico_paths::host() {
        dorico_paths::Host::Windows => ("windows".into(), String::new()),
        dorico_paths::Host::Wsl { distro } => ("wsl".into(), distro),
        dorico_paths::Host::Mac => ("mac".into(), String::new()),
        dorico_paths::Host::Linux => ("linux".into(), String::new()),
    }
}

#[pyfunction]
fn to_host(path: &str) -> String {
    path_str(&dorico_paths::to_host(path))
}

#[pyfunction]
fn to_windows(path: PathBuf) -> Option<String> {
    dorico_paths::to_windows(&path)
}

#[pyfunction]
fn windows_to_wsl(path: &str) -> String {
    dorico_paths::windows_to_wsl(path)
}

#[pyfunction]
fn wsl_to_windows(path: &str, distro: &str) -> String {
    dorico_paths::wsl_to_windows(path, distro)
}

/// `[(dir, version or None)]`, newest first.
#[pyfunction]
fn dorico_installs() -> Vec<(String, Option<u32>)> {
    dorico_paths::dorico_installs().into_iter().map(|i| (path_str(&i.dir), i.version)).collect()
}

#[pyfunction]
#[pyo3(signature = (version = None))]
fn dorico_install(version: Option<u32>) -> Option<(String, Option<u32>)> {
    dorico_paths::dorico_install(version).map(|i| (path_str(&i.dir), i.version))
}

#[pyfunction]
fn user_home() -> Option<String> {
    dorico_paths::user_home().as_deref().map(path_str)
}

#[pyfunction]
fn dorico_appdata(version: u32) -> Option<String> {
    dorico_paths::dorico_appdata(version).as_deref().map(path_str)
}

#[pyfunction]
fn documents() -> Option<String> {
    dorico_paths::documents().as_deref().map(path_str)
}

#[pyfunction]
fn dorico_projects() -> Option<String> {
    dorico_paths::dorico_projects().as_deref().map(path_str)
}

/// Every corpus entry (`engine/tests/corpus.toml` + env overrides) as name -> path.
#[pyfunction]
fn corpus<'py>(py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
    let c = dorico_paths::corpus::Corpus::load().map_err(err)?;
    let d = PyDict::new(py);
    for name in c.names() {
        d.set_item(name, path_str(c.get(name).unwrap()))?;
    }
    d.set_item("_root", path_str(&c.root))?;
    Ok(d)
}

// ---------------------------------------------------------------------------
// timeline
// ---------------------------------------------------------------------------

/// Time in a project (engine/crates/timeline): positions are passed as text ("81/4").
#[pyclass(frozen, module = "doricokit._native")]
struct Timeline {
    t: dorico_timeline::ProjectTimeline,
}

impl Timeline {
    fn flow(&self, flow: usize) -> PyResult<&dorico_timeline::FlowTimeline> {
        self.t.flows.get(flow).ok_or_else(|| PyValueError::new_err(format!("no flow {flow}")))
    }
}

fn pos(s: &str) -> PyResult<Ratio> {
    Ratio::try_parse(s).ok_or_else(|| PyValueError::new_err(format!("bad position {s:?}")))
}

#[pymethods]
impl Timeline {
    /// Build from a `.dorico` file's bytes.
    #[staticmethod]
    fn from_bytes(py: Python<'_>, data: &[u8]) -> PyResult<Timeline> {
        py.detach(|| -> anyhow::Result<Timeline> {
            let p = Project::from_bytes(data)?;
            let score = dorico_model::read_project(&p)?;
            Ok(Timeline { t: dorico_timeline::ProjectTimeline::new(&score) })
        })
        .map_err(err)
    }

    /// Everything (tempo segments, performed spans, caveats, flow starts) as JSON text.
    fn to_json(&self) -> PyResult<String> {
        serde_json::to_string(&self.t).map_err(|e| err(e.into()))
    }

    /// Seconds from the flow start to the first time `pos` sounds (performed order).
    fn seconds(&self, flow: usize, pos: &str) -> PyResult<Option<f64>> {
        Ok(self.flow(flow)?.seconds(self::pos(pos)?))
    }

    /// Seconds from the flow start to `pos` in notated order (repeats ignored).
    fn notated_seconds(&self, flow: usize, pos: &str) -> PyResult<f64> {
        Ok(self.flow(flow)?.notated_seconds(self::pos(pos)?))
    }

    /// Every time `pos` sounds: [(pass, seconds, performed crotchets "n/d")].
    fn occurrences(&self, flow: usize, pos: &str) -> PyResult<Vec<(u32, f64, String)>> {
        Ok(self.flow(flow)?.occurrences(self::pos(pos)?).into_iter().map(|o| (o.pass, o.secs, o.crotchets.to_string())).collect())
    }

    /// Performed seconds -> (span index, notated crotchets as a float).
    fn at_seconds(&self, flow: usize, secs: f64) -> PyResult<Option<(usize, f64)>> {
        Ok(self.flow(flow)?.at_seconds(secs))
    }

    /// Crotchets per minute at `pos`.
    fn bpm_at(&self, flow: usize, pos: &str) -> PyResult<f64> {
        Ok(self.flow(flow)?.tempo.bpm_at(self::pos(pos)?))
    }

    /// Performed seconds -> clip time of the flow's video (None without video).
    fn clip_time(&self, flow: usize, secs: f64) -> PyResult<Option<f64>> {
        Ok(self.flow(flow)?.clip_time(secs))
    }

    /// Performed seconds -> timecode text (None without a frame rate).
    fn timecode(&self, flow: usize, secs: f64) -> PyResult<Option<String>> {
        Ok(self.flow(flow)?.timecode(secs))
    }

    /// MIDI tempo events in performed order: [(tick, crotchets per minute)], as Dorico exports them.
    fn tempo_events(&self, flow: usize) -> PyResult<Vec<(i128, f64)>> {
        Ok(self.flow(flow)?.tempo_events())
    }
}

// ---------------------------------------------------------------------------
#[pymodule]
fn _native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("DTN_VERSION", dtn::DTN_VERSION)?;
    m.add("MARKER_PI", xml::MARKER_PI)?;
    m.add("TICKS_PER_CROTCHET", TICKS_PER_CROTCHET)?;
    m.add_function(wrap_pyfunction!(dtn_decode, m)?)?;
    m.add_function(wrap_pyfunction!(dtn_encode, m)?)?;
    m.add_function(wrap_pyfunction!(xml_write, m)?)?;
    m.add_function(wrap_pyfunction!(xml_read, m)?)?;
    m.add_function(wrap_pyfunction!(zip_read, m)?)?;
    m.add_function(wrap_pyfunction!(zip_write, m)?)?;
    m.add_class::<Timeline>()?;
    for f in [
        wrap_pyfunction!(ratio_parse, m)?,
        wrap_pyfunction!(ratio_format, m)?,
        wrap_pyfunction!(ratio_to_ticks, m)?,
        wrap_pyfunction!(ids_check, m)?,
        wrap_pyfunction!(model_json, m)?,
        wrap_pyfunction!(listing_json, m)?,
        wrap_pyfunction!(host, m)?,
        wrap_pyfunction!(to_host, m)?,
        wrap_pyfunction!(to_windows, m)?,
        wrap_pyfunction!(windows_to_wsl, m)?,
        wrap_pyfunction!(wsl_to_windows, m)?,
        wrap_pyfunction!(dorico_installs, m)?,
        wrap_pyfunction!(dorico_install, m)?,
        wrap_pyfunction!(user_home, m)?,
        wrap_pyfunction!(dorico_appdata, m)?,
        wrap_pyfunction!(documents, m)?,
        wrap_pyfunction!(dorico_projects, m)?,
        wrap_pyfunction!(corpus, m)?,
    ] {
        m.add_function(f)?;
    }
    Ok(())
}
