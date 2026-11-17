"""Cleaner: fix what the reviewer reports, in a copy of any Dorico project.

    from doricokit import clean
    changes = clean.clean("In.dorico", "Out.dorico")                 # default rules
    changes = clean.clean("In.dorico", None, ["link"], dry_run=True)
    print(clean.format_text(changes))

Never overwrites the input. Each rule reports every change it makes (`findings.Finding`,
severity "change") and every place it left alone on purpose (severity "info"). Edits go
through `doricokit.edit`: only the score is re-encoded, a run with no changes copies the input
byte for byte, IDs are checked before saving.

Rules are registered in `doricokit.findings`; any tool can add its own:

    def my_rule(ctx, flow, fe):      # ctx: Cleaner, flow: view.Flow, fe: edit.FlowEdit
        ...; fe.remove_event(eid); ctx.change("my-rule", flow, player, pos, "what changed")
    findings.register_rule("my-rule", "What it changes", my_rule, default=False, owner="mytool")

Built-in rules (default on; the certain ones):
  dedupe  the same marking twice at one position on a staff -> keep the first
          (identical dynamics groups, trills, playing techniques)
  link    identical dynamics on staves playing the same rhythm at one position (reviewer
          "could-link") -> one shared (linked) element, as Dorico links them

Moved here from finale2dorico's f2d/clean.py (2026-10-31), where it was first written;
`f2d clean` uses it. Docs: finale2dorico/docs/CLEANER.md.
"""
from __future__ import annotations

from fractions import Fraction
from pathlib import Path

from . import edit, findings, view
from .findings import Finding
from .review import Reviewer, located, section_clusters

__all__ = ["Cleaner", "clean", "default_rules", "format_text", "to_json", "after_check"]


class Cleaner:
    def __init__(self, data: bytes, path: str = ""):
        self.edit = edit.Project(data, path)
        self.project = view.read_bytes(data, path)
        self.changes: list[Finding] = []
        self.skipped: list[Finding] = []   # places a rule left alone on purpose

    def change(self, rule: str, fl: view.Flow, player: str, pos: Fraction, message: str, *,
               staff=None, events=(), change: tuple[str, str] | None = None) -> None:
        """Report a change made: `events` = the Dorico event IDs changed or removed, `change` =
        (before, after) in words."""
        located(self.changes, Finding(rule, "change", fl.name, player, str(pos), fl.where(pos), message),
                fl, pos, staff, events, change)

    def skip(self, rule: str, fl: view.Flow, player: str, pos: Fraction, message: str, *,
             staff=None, events=()) -> None:
        located(self.skipped, Finding(rule, "info", fl.name, player, str(pos), fl.where(pos), message),
                fl, pos, staff, events)

    def run(self, rules=None) -> list[Finding]:
        regs = findings.rules()
        names = list(rules) if rules is not None else default_rules()
        for name in names:
            if name not in regs:
                raise ValueError(f"unknown rule {name!r} (known: {', '.join(regs)})")
        for fl, fe in zip(self.project.flows, self.edit.flows):
            for name in regs:  # registration order, whatever order they were named in
                if name in names:
                    regs[name].fn(self, fl, fe)
        return self.changes


def default_rules() -> list[str]:
    return [n for n, r in findings.rules().items() if r.default]


# ------------------------------------------------------------------ built-in rules
def _dedupe(ctx: Cleaner, fl: view.Flow, fe: edit.FlowEdit) -> None:
    for st in fl.staves:
        seen = set()
        kept = []
        for g in sorted(st.dynamics, key=lambda g: (g.pos, int(g.event or 0))):
            key = (g.pos, g.signature(), fe.dynamic_group_content(g.event))
            if key in seen and g.event in fe.events:
                fe.remove_event(g.event)
                levels = " ".join(i.level for i in g.items)
                ctx.change("dedupe", fl, st.label, g.pos, f"removed a second identical dynamics group ({levels})",
                           staff=st, events=[g.event], change=(f"{levels} ×2", levels))
                continue
            seen.add(key)
            kept.append(g)
        st.dynamics = kept
        seen = set()
        for kind, pos, detail, eid in sorted(st.marks, key=lambda m: (m[1], int(m[3] or 0))):
            key = (kind, pos, detail, fe.event_content(eid))
            if key in seen and eid in fe.events:
                fe.remove_event(eid)
                what = f"technique {detail}" if kind == "technique" else kind
                ctx.change("dedupe", fl, st.label, pos, f"removed a second identical {what}",
                           staff=st, events=[eid], change=(f"{what} ×2", what))
                continue
            seen.add(key)


def _link(ctx: Cleaner, fl: view.Flow, fe: edit.FlowEdit) -> None:
    for pos, members in section_clusters(fl, "could-link"):
        # keep the element already shared by the most staves (else the first staff's)
        first = max(members, key=lambda m: (m[1].linked, -members.index(m)))[1]
        keep = first.element
        if keep not in fe.dynamic_elements:
            continue
        want = fe.dynamic_group_content(first.event)
        moved, differ = [], []
        before = len({g.element for _, g in members})
        for st, g in members:
            if g.element == keep or g.event not in fe.events:
                continue
            if fe.dynamic_group_content(g.event) != want:  # same levels, but tweaked by hand
                differ.append((st, g))
                continue
            fe.link_dynamic_group(g.event, keep)
            g.element = keep
            moved.append((st, g))
        if moved:
            labels = [st.label for st, _ in differ]
            kept = [(st, g) for st, g in members if st.label not in labels]
            names = ", ".join(st.label for st, _ in kept)
            ctx.change("link", fl, names, pos, f"linked the identical dynamics of {names}",
                       staff=[st for st, _ in kept], events=[g.event for _, g in moved],
                       change=(f"{before} separate dynamics elements", "1 linked element" if not differ
                               else f"{len({g.element for _, g in members})} elements"))
        if differ:
            ctx.skip("link", fl, ", ".join(st.label for st, _ in differ), pos,
                     "not linked: same dynamics, but their properties differ (edited by hand?)",
                     staff=[st for st, _ in differ], events=[g.event for _, g in differ])


findings.register_rule("dedupe", "Remove the second of identical dynamics / trills / techniques at one position on a staff",
                       _dedupe, default=True)
findings.register_rule("link", "Link identical dynamics on staves playing the same rhythm (one shared element)",
                       _link, default=True)


# ------------------------------------------------------------------ running
def clean(src: str | Path, dest: str | Path | None, rules=None, dry_run: bool = False) -> list[Finding]:
    """Clean `src` into `dest` (never over `src`). Returns the changes made (severity "change";
    with dry_run, the changes that would be made), then the places a rule left alone on
    purpose (severity "info"). rules=None: the default rules."""
    src = Path(src)
    c = Cleaner(src.read_bytes(), str(src))
    changes = c.run(rules)
    if not dry_run:
        if dest is None:
            raise ValueError("an output file is needed (or use dry_run)")
        c.edit.save(dest, protect=src)
    return changes + c.skipped


def after_check(path: str | Path, rules=None) -> list[Finding]:
    """Reviewer findings that the built-in rules should have removed, in a cleaned project."""
    names = list(rules) if rules is not None else default_rules()
    want = {"dedupe": "duplicate", "link": "could-link"}
    checks = [want[n] for n in names if n in want]
    return Reviewer(view.read_project(path)).run(checks) if checks else []


def format_text(changes: list[Finding], limit: int | None = 12) -> str:
    regs = findings.rules()
    out = []
    if not any(c.severity == "change" for c in changes):
        out.append("Nothing to change.")
    for sev, head in (("change", ""), ("info", "left alone: ")):
        for rule in regs:
            cs = [c for c in changes if c.check == rule and c.severity == sev]
            if not cs:
                continue
            out.append(f"{head}{rule} ({len(cs)})" + (f": {regs[rule].description}" if sev == "change" else ""))
            for c in cs[: limit or len(cs)]:
                out.append(f"          {c.player}, {c.where}: {c.message}")
            if limit and len(cs) > limit:
                out.append(f"          ... {len(cs) - limit} more (use --all)")
    return "\n".join(out)


def to_json(changes: list[Finding], project: str) -> str:
    return findings.to_json(changes, project, "rules")
