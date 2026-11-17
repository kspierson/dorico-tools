# Companion utilities (proposal)

*2026-10-27. The user asked for complementary tools, e.g. a score "cleaner" and a score "editor".
Decided: start with the **reviewer** (built, v1); the end goal is **one UI giving access to all
features** (converter, reviewer, cleaner, editor), on the same framework as dorigit's app
(Tauri 2 + Svelte 5). Everything therefore exposes JSON the UI can consume.*

Principle (from the user): the converter reproduces what Finale has and compensates for Finale
artifacts, but makes no editorial decisions. Editorial clean-up belongs in separate, optional
tools that work on **any** `.dorico` project (converted, MusicXML-imported, or hand-made) and
always write a new file (or a dorigit commit) so changes can be reviewed and undone.

They would be built on the shared engine ([SHARED_ENGINE.md](SHARED_ENGINE.md)): the same codec,
container, model and writer pieces the converter uses.

## 1. Cleaner (rule-based, each rule switchable, with a report of every change)

| Rule | Example from the Willow work |
|---|---|
| Harmonise section dynamics: players playing the same phrase get identical groups (hairpin starts/ends aligned, same dynamics), then linked | User aligned Tbn 2/3 + Vla and Vln 1/2 hairpins in 13 so they link |
| Link / unlink dynamics by condensing group (what would condense together) | Cl 3 + Hn 1 linked, not with the trumpets |
| Group dynamics along a staff (dynamic -> hairpin -> dynamic chains, gaps while playing) | User's 07 and 13 edits |
| Remove redundant or conflicting dynamics (same level repeated with nothing between; two different dynamics on one beat) | Bass Cl bar 2: barline ff vs mp |
| Hairpins that cross rests or end on nothing | |
| Explode / implode condensed staves in projects that came via MusicXML | Horn 1/3 in layers |
| Merge players that are really one doubling player (parts never overlap) | Fl 1 doubling Picc; "Broadway" Wind 1 |
| Normalise playing techniques per instrument (e.g. "Mute" -> straight mute for brass) | |

## 2. Editor (scripted / batch edits; CLI first, maybe a small UI later)

- Apply a house style: copy engraving/notation/layout options, fonts, paragraph styles, page
  templates from a template project.
- Rename / renumber / reorder players; set instrument names and short names in bulk.
- Find & replace in text items, titles, tempo marks, technique text.
- Bulk transpose or respell; set key or time signatures across flows.
- Set or clear forced durations, stem directions, accidental visibility on a selection.

## 3. Reviewer (report only, no edits) — built, v1

`python3 -m f2d review X.dorico [--json findings.json] [--all]` ([f2d/review.py](../f2d/review.py),
reader [f2d/dorico/read.py](../f2d/dorico/read.py), a view over the shared `doricokit.model`). Works on any .dorico. Checks (each finding:
check, severity, flow, player, bar/beat, message):

| Check | Severity |
|---|---|
| dynamic-clash: two different dynamics at one position on a staff | warning |
| dynamic-in-silence: dynamic where nothing sounds | warning |
| hairpin-in-silence: hairpin starting in / mostly over rests | warning / info |
| duplicate: same dynamics group / trill / technique twice at a position | warning |
| range: outside Dorico's advanced (warning) or standard (info) range, concert pitch | warning / info |
| repeated-dynamic: same dynamic again with nothing between (and no long rest) | info |
| could-link / could-align: identical / nearly identical dynamics on staves playing the same rhythm, not linked (one finding per position and set of staves) | info |
| mute-not-released | info |
| not-converted: from `f2d convert --report` sidecar (`X.f2d-report.json`) | info |

Round 6 ran it on the five real scores (`experiments/round6/*.review.txt|json`). On Willow it
flags exactly the places the user fixed by hand in 13 (e.g. bar 1 beat 2: Bassoons, Trombones,
Violins, Viola could align; the barline ff in bar 2).

Next ideas: suspicious enharmonics, slurs over rests, ties to different pitches, unreleased
pizz., techniques on rests, tempo without metronome mark, cue/condensing readiness.

## Questions for the user

1. ~~Which first?~~ Reviewer (done, v1). Next suggested: the cleaner's harmonise / link / group
   rules (they act on exactly what the reviewer reports).
2. ~~CLI or UI?~~ A UI for everything eventually, Tauri 2 + Svelte 5 like dorigit. Where it lives
   (dorigit's app vs a new app) ties in with the shared-engine decision.
