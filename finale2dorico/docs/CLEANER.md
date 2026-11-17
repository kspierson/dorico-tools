# Cleaner

## Status (2026-10-31): v1 built — `dedupe` and `link`

`python3 -m f2d clean In.dorico [-o Out.dorico] [--rules dedupe,link] [--dry-run] [--json changes.json] [--all]`

**Where it lives (2026-10-31, user's request: modular, usable by every tool):** in the shared
engine package, not in the converter: `doricokit.clean` (rules), `doricokit.edit` (general
editing operations: load/change/save, remove event, link, content equality), `doricokit.findings`
(one report format + a registry where any tool registers its own checks and rules),
`doricokit.view` + `doricokit.review` (the reviewer). f2d's `review`/`clean` commands only wrap
them; the house-style tool, harpgliss etc. import `doricokit` directly and add rules with
`findings.register_rule(...)`. Tests: `engine/tests/python/test_clean.py`, f2d `tests/test_clean.py`.

- Edits the score tree in place (`doricokit.container` / `format`); only `score.dtn`/`score.xml`
  changes, other zip entries are copied; a no-op decode/encode is byte-identical on all 40 of the
  user's projects tried; a run with no changes copies the input byte for byte. Never writes over
  the input (default output: `<name> (cleaned).dorico`). After writing it checks IDs
  (`doricokit.ids.check`) and re-runs the reviewer.
- `dedupe`: identical dynamics groups / trills / playing techniques at one position on one
  staff -> the first is kept. "Identical" means the whole Dorico item apart from its IDs, so
  hand-made tweaks (offsets ...) are never merged away.
- `link`: the reviewer's could-link sets (shared `review.section_clusters`) -> every event points
  at one element (the one already shared most), its `referencingEventIDs` lists them all, and
  elements nothing refers to are removed (element IDs with gaps are normal in Dorico's files).
  Groups that match in level/position but differ in their properties are left alone and listed.
- Willow (user's edited 13-willow-full): 4 duplicate hairpins removed, 3 sets linked; the
  reviewer then reports no duplicate / could-link.
- Sweep (2026-10-31) over 337 projects (the user's Dorico projects and backups + converted
  scores): no errors, no ID problems; 29 duplicates removed, 5,983 links; 474 sets left alone
  because a property really differs (e.g. a dynamic moved before a grace note, secondary
  position -1/2). Default-valued properties and the two forms of an empty property list count
  as equal.
- To check in Dorico: `experiments/cleaner/willow-cleaned.dorico` (from the user's 13-willow-full
  edit, `willow-before.dorico`; changes listed in `willow-changes.txt`).

## Design (2026-10-28)

*2026-10-28. Plan only; build starts after the current converter batch. Agreed with the user:
the cleaner is next; it acts on what the reviewer reports; editorial changes stay out of the
converter.*

## What it is

`python3 -m f2d clean In.dorico -o Out.dorico [--rules a,b,c] [--dry-run]`

- Works on **any** Dorico project (converted, MusicXML-imported, hand-made).
- Never overwrites: writes a new file (later: a dorigit commit, so history shows the change).
- Every rule is optional and reports each change (bar/beat, player, what changed), in the same
  JSON shape as the reviewer's findings, so the future UI can show "found -> fixed".
- `--dry-run` = report what would change, write nothing.

## How it edits (different from the converter)

The converter *generates* a project from the IR. The cleaner must *edit* an existing project
and keep everything it doesn't touch byte-identical (layouts, playback, user tweaks):

1. Read `score.dtn` / `score.xml` into the tree (`doricokit.container` / `doricokit.format`, the shared engine).
2. Locate items through `f2d/dorico/read.py` (positions, players, element IDs).
3. Change the tree in place: edit element-table entries, add or remove events, reuse
   `idGenerators` for any new IDs (dorigit's MERGE.md notes ID rules).
4. Write back in the same form (DTN in, DTN out; other zip entries copied unchanged).
5. Re-read and re-run the reviewer on the result as a check.

This is exactly the "edit existing projects" capability the shared engine is meant to own; the
cleaner should move onto it when the engine exists (SHARED_ENGINE.md).

## Rules (first set, from the Willow work)

| Rule | Acts on reviewer check | Change |
|---|---|---|
| `link` | could-link | identical section dynamics on staves playing the same rhythm -> one shared element (others' events re-pointed, their elements removed) |
| `align` | could-align | nearly identical section dynamics -> copy one staff's group (the majority, or the earliest hairpin start on a beat) to the others, then `link` |
| `group` | (new) | regroup dynamics/hairpins along a staff with the converter's grouping rule |
| `dedupe` | duplicate | remove the second of identical dynamics / trills / techniques at one position |
| `clash` | dynamic-clash | keep one dynamic: the one that starts a group, else the later-entered one; report the other (opt-in, it is an editorial choice) |
| `barline-dynamics` | dynamic-in-silence at a barline after a hairpin | move the target dynamic onto the hairpin's group end or delete (opt-in) |
| `mute-release` | mute-not-released | add "open" / "senza sord." at the next entry after a long rest (opt-in) |
| `doublings` | (new reviewer check) | merge players whose staves never overlap and whose names suggest a doubling (Fl 1 + Picc) into one player with two instruments (opt-in; needs the instrument-change encoding from the user's projects) |

## Order of work

1. Edit plumbing: load/modify/save keeping untouched data identical; tests that a no-op clean
   gives a byte-identical file.
2. `dedupe`, `link` (smallest, most certain).
3. `align`, `group`.
4. Opt-in editorial rules.
5. Reviewer + cleaner in the UI (with the shared engine).
