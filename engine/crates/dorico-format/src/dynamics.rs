//! Dorico dynamics → readable text ("sffz", "subito mf", "fp", "dim. hairpin al niente over 2").
//!
//! A dynamic event points at a `DynamicGroupElementDefinition`, whose `subElements` hold one or
//! more definitions. Encodings (learned from the user's projects and the Round 9 reference files
//! `finale2dorico/experiments/round9/ref-extras*.dorico`; see `engine/docs/CHANGES.md`):
//!
//! | Definition | Fields |
//! |---|---|
//! | `ImmediateChangeDynamicDefinition` | `intensity` = `{int: 0=f/1=p}, {int: 1=possibile (f or p only)}, {bool: mezzo}, {int: letters}`; `intensityModifier` = `{int: amount 2=poco/4=molto}, {int: 1=meno/2=più}` (confirmed by the user in `dorigit/research/refs/ref-dynamics-divisi.dorico`); `commonDef/subito` |
//! | `ForceDynamicDefinition` | `type` kForceDynamicFz/Rfz/Sfz/Mfz, `intensityLevel` (2 = ffz/rffz/sffz); property `kDynamicRinforzandoAndSforzandoHaveZ` = false → sf/rf; `commonDef/subito` |
//! | `CombinedDynamicDefinition` | `direction` kDown (loud first: fp) / kUp (pf); `startIntensity`, `endIntensity` = letters, 0 = mezzo (mf/mp; mf-mp and ff-mp confirmed by the user); `commonDef/subito` |
//! | `GradualChangeDynamicDefinition` | `type` kCrescOrDim / kMessaDiVoce, `direction` kGradualDynamicUp/Down, `hasNiente`, `showsPocoAPoco`, `hasFlaredEnd`, `duration`; property `kDynamicGradualChangeDynamicAppearance` (hairpin, …) |
//!
//! Policy (user, 2026-10-30): every dynamic Dorico offers by default is shown by name; anything
//! not recognised is still shown readably ("custom dynamic …"), never dropped. Tools read and
//! keep such dynamics but never create non-standard ones.

use crate::dtn::Node;
use crate::ratio::Ratio;
use crate::vocab::{clean_value, variant_tokens};

/// Dynamic intensity -> "pp", "mf", ...: `{int: 0=forte|1=piano}, {}, {bool: mezzo}, {int: count}`.
/// All confirmed against Dorico (HP Plus 5, Quidditch 2004: bar 19 fff, bar 11 mf, bar 88 mp).
/// `{int: 0}, {int: 1}, {bool: false}, {}` (second slot set, no count) is what Dorico shows as
/// "f possibile" (user, test file A: Horns 1/3 bars 87 and 89, Cello 66/68, Timpani 68); "p
/// possibile" is `{int: 1}, {int: 1}, …` (dorigit/research/refs/ref-dynamics-divisi.dorico).
/// Possibile is a standard Dorico modifier, allowed only on f or p. Anything else comes back
/// as the cleaned raw value (callers show it as a custom dynamic).
pub fn decode_intensity(v: &str) -> String {
    let cleaned = clean_value(v);
    let t = variant_tokens(&cleaned);
    let attempt = || -> Option<String> {
        let loud = t.first()?.1 == "0"; // 0 = forte, 1 = piano (confirmed: HP Plus 5 bar 19 fff)
        let mezzo = t.get(2)?.1 == "true";
        let has_count = t.get(3).is_some_and(|c| !c.1.is_empty());
        if !t.get(1)?.1.is_empty() {
            // possibile: Dorico allows it only on a plain f or p (user, 2026-10-30); any other
            // combination is left raw so the caller shows it as a custom dynamic
            return (t[1].1 == "1" && !mezzo && !has_count)
                .then(|| format!("{} possibile", if loud { "f" } else { "p" }));
        }
        if mezzo {
            return Some(if loud { "mf" } else { "mp" }.to_owned());
        }
        let count: usize = t.get(3)?.1.parse().ok()?;
        Some((if loud { "f" } else { "p" }).repeat(count))
    };
    attempt().unwrap_or(cleaned)
}

/// The machine form of one dynamic sub-element, for tools that compute with dynamics
/// (dorico-hp's playback rules, the reviewer's comparisons). Readable text: [`describe`].
#[derive(Debug, Clone, PartialEq)]
pub struct Level {
    /// "dynamic", "hairpin", "combined", "force", or the definition name for others.
    pub kind: String,
    /// "mf", "f possibile", "cresc", "dim", "fp", "mf-mp", "sfz"; immediate dynamics Dorico
    /// can't name keep their cleaned raw intensity.
    pub level: String,
    /// Force dynamics: `intensityLevel`; hairpins: appearance ("kHairpin", "kNiente"…).
    pub extra: String,
    /// Hairpins: their length.
    pub duration: Option<Ratio>,
}

/// Machine form of a sub-element (see [`Level`]). Subito and modifiers are not part of the
/// level; [`describe`] shows them.
pub fn level(sub: &Node) -> Level {
    let (kind, level, extra, duration) = match &*sub.tag {
        "ImmediateChangeDynamicDefinition" => ("dynamic".to_owned(), decode_intensity(sub.text("intensity")), String::new(), None),
        "GradualChangeDynamicDefinition" => {
            let d = sub.text("direction");
            let level = if d.ends_with("Up") {
                "cresc"
            } else if d.ends_with("Down") {
                "dim"
            } else {
                d
            };
            let look = crate::tree::props::get(sub, "kDynamicGradualChangeDynamicAppearance").map(clean_value).unwrap_or_default();
            ("hairpin".to_owned(), level.to_owned(), look, Some(Ratio::parse(sub.text("duration"))))
        }
        "CombinedDynamicDefinition" => {
            let name = combined(sub).map(|(a, b)| join_combined(&a, &b)).unwrap_or_else(|| {
                format!("{}{}/{}", sub.text("direction"), sub.text("startIntensity"), sub.text("endIntensity"))
            });
            ("combined".to_owned(), name, String::new(), None)
        }
        "ForceDynamicDefinition" => {
            let t = sub.text("type");
            let level = t.strip_prefix("kForceDynamic").unwrap_or(t).to_lowercase();
            ("force".to_owned(), level, sub.text("intensityLevel").to_owned(), None)
        }
        other => (other.strip_suffix("DynamicDefinition").unwrap_or(other).to_owned(), String::new(), String::new(), None),
    };
    Level { kind, level, extra, duration }
}

/// The two parts of a combined dynamic ("f", "p"; 0 letters = mezzo: "mf"/"mp").
fn combined(sub: &Node) -> Option<(String, String)> {
    let part = |n: &str, loud: bool| -> Option<String> {
        let n: usize = n.parse().ok()?;
        Some(match (n, loud) {
            (0, true) => "mf".into(),
            (0, false) => "mp".into(),
            (n, true) => "f".repeat(n),
            (n, false) => "p".repeat(n),
        })
    };
    let (s, e) = (sub.text("startIntensity"), sub.text("endIntensity"));
    match sub.text("direction") {
        "kDown" => part(s, true).zip(part(e, false)),
        "kUp" => part(s, false).zip(part(e, true)),
        _ => None,
    }
}

/// "fp", "ffp"; a mezzo part needs the separator to stay readable ("mf-mp", "ff-mp").
fn join_combined(a: &str, b: &str) -> String {
    if a.starts_with('m') || b.starts_with('m') { format!("{a}-{b}") } else { format!("{a}{b}") }
}

fn subito(n: &Node) -> bool {
    n.find("commonDef/subito").and_then(|s| s.value.as_deref()) == Some("true")
}

fn property<'a>(n: &'a Node, ptype: &str) -> Option<&'a str> {
    n.find("propertyTable/entries")
        .map(Node::items)
        .unwrap_or(&[])
        .iter()
        .rev()
        .find(|e| e.text("propertyType") == ptype)
        .map(|e| e.text("value"))
}

/// True if `decode_intensity` could not name the level (it returns the raw variant list).
fn is_raw(level: &str) -> bool {
    level.contains('{') || level.is_empty()
}

/// `intensityModifier` = `{amount}, {less or more}` -> "poco", "molto più", …; `Err(raw)` for
/// values not seen yet (shown raw, never dropped).
fn immediate_modifier(raw: &str) -> Result<Option<String>, String> {
    let cleaned = clean_value(raw);
    let t = variant_tokens(&cleaned);
    let unknown = || Err(cleaned.clone());
    let amount = match t.first().map(|x| x.1.as_str()) {
        None | Some("") => None,
        Some("2") => Some("poco"),
        Some("4") => Some("molto"),
        Some(_) => return unknown(),
    };
    let direction = match t.get(1).map(|x| x.1.as_str()) {
        None | Some("") => None,
        Some("1") => Some("meno"),
        Some("2") => Some("più"),
        Some(_) => return unknown(),
    };
    if t.len() > 2 {
        return unknown();
    }
    let words: Vec<&str> = amount.into_iter().chain(direction).collect();
    Ok((!words.is_empty()).then(|| words.join(" ")))
}

/// Modifier fields not seen yet on force dynamics or hairpins: shown raw if they ever appear.
fn other_modifier(n: &Node, ptype: &str) -> Option<String> {
    let field = n.child("intensityModifier").and_then(|m| m.value.as_deref()).map(clean_value);
    let value = field.or_else(|| property(n, ptype).map(clean_value))?;
    let empty = value.chars().all(|c| "{}, ".contains(c));
    (!empty).then(|| format!("(modifier {value})"))
}

fn with_subito(n: &Node, text: String) -> String {
    if subito(n) { format!("subito {text}") } else { text }
}

/// One `…DynamicDefinition` sub-element as text.
pub fn describe(sub: &Node) -> String {
    match &*sub.tag {
        "ImmediateChangeDynamicDefinition" => {
            let raw = sub.text("intensity");
            let level = decode_intensity(raw);
            let mut text = if is_raw(&level) { format!("custom dynamic ({})", clean_value(raw)) } else { level };
            match immediate_modifier(sub.text("intensityModifier")) {
                Ok(Some(words)) => text = format!("{words} {text}"),
                Ok(None) => {}
                Err(raw) => text = format!("{text} (modifier {raw})"),
            }
            with_subito(sub, text)
        }
        "ForceDynamicDefinition" => {
            let t = sub.text("type");
            let base = t.strip_prefix("kForceDynamic").unwrap_or(t).to_lowercase();
            let level: usize = sub.text("intensityLevel").parse().unwrap_or(1).max(1);
            // the level repeats the f: fz -> ffz, sfz -> sffz, rfz -> rffz
            let mut text = match base.find('f') {
                Some(i) => format!("{}{}{}", &base[..i], "f".repeat(level), &base[i + 1..]),
                None => base.clone(),
            };
            if property(sub, "kDynamicRinforzandoAndSforzandoHaveZ").map(clean_value).as_deref() == Some("false")
                && (text.starts_with('s') || text.starts_with('r'))
            {
                text = text.trim_end_matches('z').to_owned();
            }
            if text.is_empty() {
                text = format!("custom force dynamic ({t})");
            }
            if let Some(m) = other_modifier(sub, "kDynamicForceIntensityModifier") {
                text = format!("{text} {m}");
            }
            with_subito(sub, text)
        }
        "CombinedDynamicDefinition" => {
            let text = match combined(sub) {
                Some((a, b)) => join_combined(&a, &b),
                None => format!(
                    "custom combined dynamic ({} {}/{})",
                    sub.text("direction"),
                    sub.text("startIntensity"),
                    sub.text("endIntensity")
                ),
            };
            with_subito(sub, text)
        }
        "GradualChangeDynamicDefinition" => {
            let up = sub.text("direction").ends_with("Up");
            let down = sub.text("direction").ends_with("Down");
            let messa = sub.text("type") == "kMessaDiVoce";
            let mut words = vec![match (messa, up, down) {
                (true, true, _) => "messa di voce (cresc.-dim.)".to_owned(),
                (true, _, true) => "messa di voce (dim.-cresc.)".to_owned(),
                (false, true, _) => "cresc.".to_owned(),
                (false, _, true) => "dim.".to_owned(),
                _ => format!("gradual dynamic ({})", sub.text("type")),
            }];
            if let Some(look) = property(sub, "kDynamicGradualChangeDynamicAppearance") {
                let v = clean_value(look);
                words.push(v.strip_prefix('k').unwrap_or(&v).to_lowercase());
            }
            if sub.text("showsPocoAPoco") == "true" {
                words.push("poco a poco".into());
            }
            if sub.text("hasNiente") == "true" {
                // a hairpin from nothing (cresc., or messa di voce starting from nothing) or to nothing
                words.push(if up { "dal niente" } else { "al niente" }.into());
            }
            if sub.text("hasFlaredEnd") == "true" {
                words.push("flared".into());
            }
            if let Some(m) = other_modifier(sub, "kDynamicGradualChangeDynamicIntensityModifier") {
                words.push(m);
            }
            words.push(format!("over {}", sub.text("duration")));
            with_subito(sub, words.join(" "))
        }
        other => format!("custom dynamic ({})", other.strip_suffix("DynamicDefinition").unwrap_or(other)),
    }
}

/// A whole `DynamicGroupElementDefinition` (its sub-elements, in order).
pub fn describe_group(element: Option<&Node>) -> String {
    let Some(element) = element else { return "?".into() };
    let parts: Vec<String> =
        element.child("subElements").map(Node::items).unwrap_or(&[]).iter().map(describe).collect();
    if parts.is_empty() { "(empty)".into() } else { parts.join(" ") }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn el(tag: &str, kids: Vec<Node>) -> Node {
        Node::element(tag, kids)
    }
    fn leaf(t: &str, v: &str) -> Node {
        Node::leaf(t, v)
    }
    fn common(subito: bool) -> Node {
        el("commonDef", vec![leaf("subito", if subito { "true" } else { "false" })])
    }
    fn prop(t: &str, v: &str) -> Node {
        el("propertyTable", vec![el("entries", vec![el("entry", vec![leaf("propertyType", t), leaf("value", v)])])])
    }
    fn immediate(i: &str, subito: bool) -> Node {
        immediate_mod(i, "{}, {}", subito)
    }
    fn immediate_mod(i: &str, m: &str, subito: bool) -> Node {
        el(
            "ImmediateChangeDynamicDefinition",
            vec![
                leaf("intensity", &format!("steamVariantList:list: {i}")),
                leaf("intensityModifier", &format!("steamVariantList:list: {m}")),
                common(subito),
            ],
        )
    }
    fn force(t: &str, level: &str, extra: Vec<Node>) -> Node {
        let mut kids = vec![leaf("type", t), leaf("intensityLevel", level), common(false)];
        kids.extend(extra);
        el("ForceDynamicDefinition", kids)
    }
    fn combined(dir: &str, s: &str, e: &str, subito: bool) -> Node {
        el(
            "CombinedDynamicDefinition",
            vec![leaf("direction", dir), leaf("startIntensity", s), leaf("endIntensity", e), common(subito)],
        )
    }
    fn gradual(t: &str, dir: &str, niente: bool, poco: bool) -> Node {
        el(
            "GradualChangeDynamicDefinition",
            vec![
                prop("kDynamicGradualChangeDynamicAppearance", "string: \"kHairpin\""),
                leaf("type", t),
                leaf("direction", dir),
                leaf("duration", "7"),
                leaf("hasNiente", if niente { "true" } else { "false" }),
                leaf("showsPocoAPoco", if poco { "true" } else { "false" }),
                leaf("hasFlaredEnd", "false"),
                common(false),
            ],
        )
    }

    #[test]
    fn immediate_levels() {
        assert_eq!(describe(&immediate("{int: 0}, {}, {bool: false}, {int: 3}", false)), "fff");
        assert_eq!(describe(&immediate("{int: 1}, {}, {bool: true}, {}", false)), "mp");
        assert_eq!(describe(&immediate("{int: 0}, {}, {bool: true}, {}", true)), "subito mf");
        assert_eq!(describe(&immediate("{int: 0}, {int: 1}, {bool: false}, {}", false)), "f possibile");
        assert_eq!(describe(&immediate("{int: 1}, {int: 1}, {bool: false}, {}", false)), "p possibile");
        // possibile on anything but f or p isn't something Dorico makes: shown as custom
        assert_eq!(
            describe(&immediate("{int: 0}, {int: 1}, {bool: false}, {int: 2}", false)),
            "custom dynamic ({int: 0}, {int: 1}, {bool: false}, {int: 2})"
        );
        assert_eq!(
            describe(&immediate("{int: 9}, {list: {int: 2}}", false)),
            "custom dynamic ({int: 9}, {list: {int: 2}})"
        );
    }

    #[test]
    fn modifiers() {
        // ref-dynamics-divisi.dorico, confirmed by the user
        let p5 = "{int: 1}, {}, {bool: false}, {int: 5}";
        assert_eq!(describe(&immediate_mod(p5, "{int: 2}, {}", false)), "poco ppppp");
        assert_eq!(describe(&immediate_mod(p5, "{int: 4}, {}", false)), "molto ppppp");
        assert_eq!(describe(&immediate_mod(p5, "{}, {int: 2}", false)), "più ppppp");
        assert_eq!(describe(&immediate_mod(p5, "{}, {int: 1}", true)), "subito meno ppppp");
        assert_eq!(describe(&immediate_mod(p5, "{int: 4}, {int: 2}", false)), "molto più ppppp");
        assert_eq!(describe(&immediate_mod(p5, "{int: 3}, {}", false)), "ppppp (modifier {int: 3}, {})");
    }

    #[test]
    fn force_dynamics() {
        assert_eq!(describe(&force("kForceDynamicSfz", "1", vec![])), "sfz");
        assert_eq!(describe(&force("kForceDynamicSfz", "2", vec![])), "sffz");
        assert_eq!(describe(&force("kForceDynamicRfz", "2", vec![])), "rffz");
        assert_eq!(describe(&force("kForceDynamicFz", "2", vec![])), "ffz");
        assert_eq!(describe(&force("kForceDynamicMfz", "1", vec![])), "mfz");
        let sf =
            force("kForceDynamicSfz", "1", vec![prop("kDynamicRinforzandoAndSforzandoHaveZ", "string: \"false\"")]);
        assert_eq!(describe(&sf), "sf");
    }

    #[test]
    fn combined_dynamics() {
        assert_eq!(describe(&combined("kDown", "1", "1", false)), "fp");
        assert_eq!(describe(&combined("kDown", "2", "1", false)), "ffp");
        assert_eq!(describe(&combined("kDown", "1", "2", false)), "fpp");
        assert_eq!(describe(&combined("kUp", "1", "1", false)), "pf");
        assert_eq!(describe(&combined("kDown", "0", "0", true)), "subito mf-mp");
    }

    #[test]
    fn machine_levels() {
        let l = |n: &Node| {
            let l = level(n);
            (l.kind, l.level, l.extra)
        };
        assert_eq!(l(&immediate("{int: 0}, {}, {bool: true}, {}", true)), ("dynamic".into(), "mf".into(), "".into()));
        assert_eq!(l(&combined("kDown", "1", "1", false)), ("combined".into(), "fp".into(), "".into()));
        assert_eq!(l(&combined("kDown", "2", "0", false)).1, "ff-mp");
        assert_eq!(l(&combined("kSideways", "1", "1", false)).1, "kSideways1/1");
        assert_eq!(l(&force("kForceDynamicSfz", "2", vec![])), ("force".into(), "sfz".into(), "2".into()));
        let h = level(&gradual("kMessaDiVoce", "kGradualDynamicDown", false, false));
        assert_eq!((h.kind.as_str(), h.level.as_str(), h.extra.as_str()), ("hairpin", "dim", "kHairpin"));
        assert_eq!(h.duration, Some(Ratio::int(7)));
    }

    #[test]
    fn gradual_dynamics() {
        assert_eq!(describe(&gradual("kCrescOrDim", "kGradualDynamicUp", false, false)), "cresc. hairpin over 7");
        assert_eq!(
            describe(&gradual("kCrescOrDim", "kGradualDynamicDown", true, false)),
            "dim. hairpin al niente over 7"
        );
        assert_eq!(
            describe(&gradual("kMessaDiVoce", "kGradualDynamicUp", true, true)),
            "messa di voce (cresc.-dim.) hairpin poco a poco dal niente over 7"
        );
    }
}
