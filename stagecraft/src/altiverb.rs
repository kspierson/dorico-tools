//! Altiverb 7 (Audio Ease; VST2 id "AVr5") state: an XML plist ("Mission Preset") with the
//! loaded impulse response and every parameter as `{ID, Name, Value Float | Value Long}`.

use serde::Serialize;

#[derive(Debug, Clone, Default, Serialize)]
pub struct Altiverb {
    /// Impulse response, e.g. "MUSIC/studio-scoring/Todd-AO - California USA/10.7m wide s-s".
    pub ir: String,
    /// Every parameter by name, in file order.
    pub params: Vec<(String, f64)>,
}

impl Altiverb {
    pub fn get(&self, name: &str) -> Option<f64> {
        self.params.iter().find(|(n, _)| n == name).map(|(_, v)| *v)
    }

    /// The parameters that shape placement, for reports.
    pub fn summary(&self) -> String {
        let mut s = vec![format!("IR {}", if self.ir.is_empty() { "?" } else { &self.ir })];
        for (label, name) in [
            ("dry/wet", "Dry/Wet Mix"),
            ("direct gain", "Direct Gain"),
            ("ER gain", "EarlyRef Gain"),
            ("tail gain", "Tail Gain"),
            ("pre-delay", "Pre Delay"),
            ("size", "Size"),
            ("reverb time", "Reverb Time"),
        ] {
            if let Some(v) = self.get(name) {
                s.push(format!("{label} {}", trim(v)));
            }
        }
        for (label, name) in [("direct", "Direct On"), ("ER", "Early Reflections On"), ("tail", "Tail On"), ("stage positions", "Stage Positions On"), ("bypass", "Bypass")] {
            if let Some(v) = self.get(name) {
                s.push(format!("{label} {}", if v != 0.0 { "on" } else { "off" }));
            }
        }
        s.join(", ")
    }
}

fn trim(v: f64) -> String {
    let s = format!("{v:.3}");
    s.trim_end_matches('0').trim_end_matches('.').to_string()
}

fn between<'a>(s: &'a str, from: usize, open: &str, close: &str) -> Option<(&'a str, usize)> {
    let a = s[from..].find(open)? + from + open.len();
    let b = s[a..].find(close)? + a;
    Some((&s[a..b], b + close.len()))
}

pub fn parse(chunk: &[u8]) -> Altiverb {
    let s = String::from_utf8_lossy(chunk);
    let mut a = Altiverb::default();
    if let Some(i) = s.find("/info.iri2") {
        let start = s[..i].rfind("ir_ae/").map(|j| j + 6).or_else(|| s[..i].rfind('>').map(|j| j + 1)).unwrap_or(i);
        a.ir = s[start..i].to_string();
    }
    let mut p = 0;
    while let Some((name, after)) = between(&s, p, "<key>Name</key>", "</string>") {
        p = after;
        let name = name.trim().trim_start_matches("<string>").to_string();
        // the value belongs to this dict: it must come before the next "<key>Name</key>"
        let next = s[p..].find("<key>Name</key>").map_or(s.len(), |j| j + p);
        let val = between(&s, p, "<key>Value Float</key>", "</real>")
            .filter(|(_, e)| *e <= next)
            .map(|(v, _)| v.trim().trim_start_matches("<real>").to_string())
            .or_else(|| between(&s, p, "<key>Value Long</key>", "</integer>").filter(|(_, e)| *e <= next).map(|(v, _)| v.trim().trim_start_matches("<integer>").to_string()));
        if let Some(v) = val.and_then(|v| v.trim().parse::<f64>().ok()) {
            a.params.push((name, v));
        }
    }
    a
}

#[cfg(test)]
mod tests {
    #[test]
    fn reads_params_and_ir() {
        let x = r#"<dict><key>ID</key><string>DWMx</string><key>Name</key>
            <string>Dry/Wet Mix</string><key>Value Float</key> <real>0.4499999881</real></dict>
            <dict><key>Name</key><string>Stage Positions On</string><key>Value Long</key><integer>0</integer></dict>
            <dict><key>Name</key><string>IR Automation</string><key>x</key><string>y</string></dict>
            <string>ir_ae/MUSIC/studio-scoring/Todd-AO - California USA/3.5m s-s/info.iri2</string>"#;
        let a = super::parse(x.as_bytes());
        assert_eq!(a.ir, "MUSIC/studio-scoring/Todd-AO - California USA/3.5m s-s");
        assert_eq!(a.get("Dry/Wet Mix"), Some(0.4499999881));
        assert_eq!(a.get("Stage Positions On"), Some(0.0));
        assert_eq!(a.params.len(), 2);
        assert!(a.summary().contains("dry/wet 0.45"));
    }
}
