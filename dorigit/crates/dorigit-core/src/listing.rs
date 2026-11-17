//! dorigit's musical listing: the shared listing (`dorico_format::build_score`) with the
//! remaining raw lines turned into musical words.
//!
//! The shared listing already names notes, dynamics (with modifiers), tempos, markers, video and
//! harmonics. What it leaves as `field=value` text is rewritten here from the event's own data,
//! following the shared read model's reading (`dorico-model`: technique names from the score's
//! library, clef and ottava entities, text content) plus decodings learned in dorigit's research
//! (tuplets, divisi sections). See docs/RESEARCH.md.
//!
//! | Before | After |
//! |---|---|
//! | `playing technique appearanceEntityID=pta.pizzText, …` | `playing technique "Pizzicato"` |
//! | `tuplet tupletDefinition={int: 3}, {int: 2}, {list: {int: 7}, …} (length 1)` | `tuplet 3:2 quavers` |
//! | `clef forceAfterGraceNotes=false, idForTransposingLayouts=clef.bass` | `clef bass` |
//! | `text aboveOrBelow=kAbove, …, content=div., …` | `text "div."` |
//! | `divisi …, content=1, …, content=2` | `divisi 1 / 2` (`unison`, `Solo + gli altri`) |
//! | `note F2 crotchet {ArticulationDuration=kTenuto}` | `note F2 crotchet tenuto` |
//!
//! Lines this module doesn't know stay exactly as the shared listing wrote them.
//!
//! Every name comes from the engine (`dorico_format::vocab`); this module only decides which
//! listing lines get them and how they read (quotes, kept lengths).

use dorico_format::model::Event;
use dorico_format::vocab::{self, TechniqueAppearance, rich_text};
use dorico_format::{Node, Score, build_score};
use std::collections::{BTreeMap, HashMap};

pub use dorico_format::vocab::glyphs;

/// The listing dorigit shows, diffs and stores summaries from.
pub fn build(root: &Node) -> Score {
    let mut score = build_score(root);
    // Dorico's glyph tokens in player names: "Trumpet (B{@flat@})" -> "Trumpet (B♭)"
    for (_, name) in &mut score.players {
        *name = glyphs(name);
    }
    for flow in &mut score.flows {
        for ev in &mut flow.events {
            if ev.owner.contains("{@") {
                ev.owner = glyphs(&ev.owner);
            }
        }
    }
    let techniques = vocab::technique_appearances(root);
    for (flow_node, flow) in root.find("flows/array").map(Node::items).unwrap_or(&[]).iter().zip(&mut score.flows) {
        if flow_node.text("flowID") != flow.flow_id {
            continue; // not expected: both follow the file's flow order
        }
        let mut events: HashMap<&str, &Node> = HashMap::new();
        for b in flow_node.find("blocks/array").map(Node::items).unwrap_or(&[]) {
            for ev in b.child("events").map(Node::items).unwrap_or(&[]) {
                events.insert(ev.text("eventID"), ev);
            }
        }
        for ev in &mut flow.events {
            if let Some(node) = events.get(ev.event_id.as_str()) {
                describe(ev, node, &techniques);
            }
        }
    }
    score
}

fn describe(ev: &mut Event, node: &Node, techniques: &BTreeMap<String, TechniqueAppearance>) {
    let text = match ev.kind.as_str() {
        "note" | "grace note" => {
            let names = articulations(&mut ev.props);
            if names.is_empty() {
                return;
            }
            format!("{} {}", ev.text, names.join(" "))
        }
        "playing technique" => {
            let name = vocab::technique_name(techniques, node.text("appearanceEntityID"));
            with_length(&format!("\"{name}\""), &ev.text)
        }
        "tuplet" => match vocab::tuplet(node.text("tupletDefinition")) {
            Some(t) => t.name,
            None => return,
        },
        "clef" => {
            let id = node.find("entityIDs/idForTransposingLayouts").and_then(|n| n.value.as_deref()).unwrap_or("");
            if id.is_empty() {
                return;
            }
            vocab::clef_name(id)
        }
        "text" | "system text" | "staff text" => {
            let t = rich_text(node);
            if t.is_empty() {
                return;
            }
            format!("\"{t}\"")
        }
        "divisi" => vocab::divisi_name(node),
        "ottava line" => with_length(&vocab::ottava_name(node.text("entityID")), &ev.text),
        "ornament" => vocab::ornament_name(node.text("entityID")),
        "arpeggio" => vocab::arpeggio_name(node.text("arpeggioType")),
        "pause" => vocab::pause_name(node),
        _ => return,
    };
    ev.text = text;
}

/// "(length 7/2)" kept from the shared text, so line lengths still diff.
fn with_length(what: &str, old: &str) -> String {
    match old.rfind(" (length ") {
        Some(i) => format!("{what}{}", &old[i..]),
        None => what.to_owned(),
    }
}

/// Note articulations by name (`vocab::articulation_name`); removes them from `props`.
fn articulations(props: &mut Vec<String>) -> Vec<String> {
    let mut names = Vec::new();
    props.retain(|p| {
        let Some((k, v)) = p.split_once('=') else { return true };
        if !matches!(k, "ArticulationDuration" | "ArticulationForce" | "ArticulationStress") || v.contains("layout") {
            return true;
        }
        let name = vocab::articulation_name(v);
        if !names.contains(&name) {
            names.push(name);
        }
        false
    });
    names
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn names() {
        let mut props = vec!["ArticulationDuration=kTenuto".to_owned(), "NoteSplitDurations=x".to_owned()];
        assert_eq!(articulations(&mut props), vec!["tenuto"]);
        assert_eq!(props, vec!["NoteSplitDurations=x"]);
    }
}
