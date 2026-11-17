"""Reviewer: places in a Dorico project worth a human look. Report only; changes nothing.

    from doricokit import review
    found = review.review("Score.dorico")          # list[findings.Finding]
    print(review.format_text(found)); review.to_json(found, path)

Works on any .dorico (converted, MusicXML-imported or hand-made). Each finding has a check
name, a severity ("warning" = probably wrong, "info" = worth a look), a location (flow, player,
bar/beat; flow, stave and event IDs so a UI can jump to the item) and a message. The checks are registered in `doricokit.findings`; tools add their
own (finale2dorico adds "not-converted" from its converter report). `section_clusters` is
shared with the cleaner's `link` rule.

Moved here from finale2dorico's f2d/review.py (2026-10-31); `f2d review` uses it.
"""
from __future__ import annotations

import re
from collections import defaultdict
from fractions import Fraction
from pathlib import Path

from . import findings
from .findings import Finding
from .view import Flow, Project, Staff, read_project

F = Fraction

_PITCH = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def _midi(name: str) -> int | None:
    m = re.fullmatch(r"([A-G])(#|b|x|bb)?(-?\d+)", name.strip())
    if not m:
        return None
    alt = {"#": 1, "b": -1, "x": 2, "bb": -2}.get(m.group(2) or "", 0)
    return 12 * (int(m.group(3)) + 1) + _PITCH[m.group(1)] + alt


def _sounding(st: Staff) -> list[tuple[Fraction, Fraction]]:
    iv = sorted((n.pos, n.pos + n.dur) for n in st.notes())
    merged: list[list[Fraction]] = []
    for a, b in iv:
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return [(a, b) for a, b in merged]


def _sounds_at(iv, p: Fraction) -> bool:
    return any(a <= p < b for a, b in iv)


def _silence_in(iv, a: Fraction, b: Fraction) -> Fraction:
    covered = sum((min(b, y) - max(a, x) for x, y in iv if y > a and x < b), F(0))
    return (b - a) - covered


def _rhythm(st: Staff, a: Fraction, b: Fraction) -> tuple:
    return tuple(sorted({(n.pos, n.dur) for n in st.notes() if a <= n.pos < b}))


def section_clusters(fl: Flow, check: str) -> list[tuple[Fraction, list]]:
    """Sets of staves that play the same rhythm over a phrase and have identical
    (check="could-link") or nearly identical ("could-align") dynamics groups at one position,
    joined through pairs that don't already share an element. [(pos, [(staff, group), ...])],
    in position order; also used by the cleaner's `link` rule."""
    groups = defaultdict(list)  # position -> [(staff, group)]
    for st in fl.staves:
        for g in st.dynamics:
            groups[g.pos].append((st, g))
    out = []
    for pos, items in groups.items():
        if len(items) < 2:
            continue
        bar = fl.bars[fl.bar_beat(pos)[0] - 1]
        parent = list(range(len(items)))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i
        for i, (sa, ga) in enumerate(items):
            for j in range(i + 1, len(items)):
                sb, gb = items[j]
                if ga.element == gb.element:
                    continue
                end = max([pos] + [x.end or x.pos for x in ga.items + gb.items])
                window = max(end, bar[0] + bar[1])
                ra = _rhythm(sa, pos, window)
                if not ra or ra != _rhythm(sb, pos, window):
                    continue
                same = ga.signature() == gb.signature()
                near = (not same and [(x.kind, x.level) for x in ga.items] == [(x.kind, x.level) for x in gb.items]
                        and max(abs(x.pos - y.pos) + abs((x.end or x.pos) - (y.end or y.pos))
                                for x, y in zip(ga.items, gb.items)) <= 1)
                if (check == "could-link" and same) or (check == "could-align" and near):
                    parent[find(i)] = find(j)
        clusters = defaultdict(list)
        for i in range(len(items)):
            clusters[find(i)].append(items[i])
        out += [(pos, members) for members in clusters.values() if len(members) > 1]
    return out


def located(out: list[Finding], f: Finding, flow: Flow, pos: Fraction, staff=None, events=(),
            change: tuple[str, str] | None = None) -> None:
    """Fill a finding's v2 location (flow ID, bar, beat, staves, events, change) and append it.
    Shared by the reviewer and the cleaner."""
    _, beat = flow.bar_beat(pos)
    staves = staff if isinstance(staff, list) else [staff] if staff is not None else []
    f.tool = findings.owner_of(f.check)
    f.flow_id, f.bar, f.beat = flow.id, flow.bar_label(pos), str(beat)
    f.staves = [st.stave_id for st in staves if st.stave_id]
    f.events = list(dict.fromkeys(e for e in events if e))
    if change is not None:
        f.change = {"before": change[0], "after": change[1]}
    out.append(f)


class Reviewer:
    """Runs the registered checks; checks report through `add`."""

    def __init__(self, project: Project):
        self.p = project
        self.findings: list[Finding] = []

    def add(self, check: str, severity: str, flow: Flow, player: str, pos: Fraction, message: str, *,
            staff: Staff | list[Staff] | None = None, events=()) -> None:
        """Report a finding. `staff`: the staff (or staves) it is on; `events`: Dorico event IDs
        of the items concerned (empty IDs are dropped)."""
        located(self.findings, Finding(check, severity, flow.name, player, str(pos), flow.where(pos), message),
                flow, pos, staff, events)

    def run(self, only: list[str] | None = None) -> list[Finding]:
        regs = [c for c in findings.checks().values() if c.fn and (only is None or c.name in only)]
        for fl in self.p.flows:
            for st in fl.staves:
                for c in regs:
                    if c.scope == "staff":
                        c.fn(self, fl, st)
            for c in regs:
                if c.scope == "flow":
                    c.fn(self, fl)
        for c in regs:
            if c.scope == "project":
                c.fn(self)
        if only is not None:  # one function can report several checks (could-link + could-align)
            self.findings = [f for f in self.findings if f.check in only]
        order = {"warning": 0, "info": 1}
        self.findings.sort(key=lambda f: (order.get(f.severity, 2), f.check, f.flow, F(f.pos), f.player))
        return self.findings


def _dynamics(ctx, fl: Flow, st: Staff) -> None:
    iv = _sounding(st)
    points = sorted((i.pos, i.level, i.kind, g.event) for g in st.dynamics for i in g.items if i.kind != "hairpin")
    by_pos = defaultdict(set)
    events_at = defaultdict(list)
    for pos, level, _, ev in points:
        by_pos[pos].add(level)
        events_at[pos].append(ev)
    for pos, levels in by_pos.items():
        if len(levels) > 1:
            ctx.add("dynamic-clash", "warning", fl, st.label, pos, f"{' and '.join(sorted(levels))} at the same position",
                    staff=st, events=events_at[pos])
    for pos, level, _, ev in points:
        if not _sounds_at(iv, pos):
            ctx.add("dynamic-in-silence", "warning", fl, st.label, pos, f"{level} where nothing sounds",
                    staff=st, events=[ev])
    for g in st.dynamics:
        for i in g.items:
            if i.kind == "hairpin" and i.end and i.end > i.pos:
                if not _sounds_at(iv, i.pos):
                    ctx.add("hairpin-in-silence", "warning", fl, st.label, i.pos, f"{i.level} hairpin starts in a rest",
                            staff=st, events=[g.event])
                elif _silence_in(iv, i.pos, i.end) * 2 > i.end - i.pos:
                    ctx.add("hairpin-in-silence", "info", fl, st.label, i.pos, f"{i.level} hairpin mostly over rests",
                            staff=st, events=[g.event])
    # repeated dynamic: same level as the one in force, no hairpin/other dynamic between,
    # and no rest of a bar or more between (restating after a long rest is normal)
    events = sorted([(i.pos, i.kind, i.level, g.event) for g in st.dynamics for i in g.items], key=lambda x: x[0])
    last = None
    for pos, kind, level, ev in events:
        if kind == "hairpin":
            last = None
            continue
        if kind != "dynamic":
            last = None
            continue
        if last and last[1] == level:
            bar_len = fl.bars[fl.bar_beat(pos)[0] - 1][1]
            if _silence_in(iv, last[0], pos) < bar_len:
                ctx.add("repeated-dynamic", "info", fl, st.label, pos,
                         f"{level} again (already {level} since {fl.where(last[0])})", staff=st, events=[ev])
        last = (pos, level)

def _duplicates(ctx, fl: Flow, st: Staff) -> None:
    seen = defaultdict(int)
    for g in st.dynamics:
        seen[("dynamics", g.pos, g.signature())] += 1
    for t in st.trills:
        seen[("trill", t[0], t)] += 1
    for t in st.techniques:
        seen[("technique", t[0], t[1])] += 1
    ids = defaultdict(list)
    for g in st.dynamics:
        ids[("dynamics", g.pos, g.signature())].append(g.event)
    for kind, pos, detail, eid in st.marks:
        ids[(kind, pos, detail)].append(eid)   # trill detail = (pos, end), technique = appearance
    for (what, pos, sig), n in seen.items():
        if n > 1:
            ctx.add("duplicate", "warning", fl, st.label, pos, f"{what} ×{n}" + (f" ({sig})" if what == "technique" else ""),
                    staff=st, events=ids[(what, pos, sig)])

def _range(ctx, fl: Flow, st: Staff) -> None:
    inst = ctx.p.instruments.get(st.instrument)
    if inst is None:
        return
    def rng(text):
        parts = (text or "").split("-")
        lo, hi = (_midi(parts[0]), _midi(parts[1])) if len(parts) == 2 else (None, None)
        return (lo, hi) if lo is not None and hi is not None else None
    std, adv = rng(inst["standard_range"]), rng(inst["advanced_range"])
    if not adv:
        return
    for v in st.voices:
        for n in v:
            if n.pitch < adv[0] or n.pitch > adv[1]:
                ctx.add("range", "warning", fl, st.label, n.pos, f"MIDI {n.pitch} outside the advanced range {inst['advanced_range']} (concert)",
                        staff=st, events=[n.event])
            elif std and (n.pitch < std[0] or n.pitch > std[1]):
                ctx.add("range", "info", fl, st.label, n.pos, f"MIDI {n.pitch} outside the standard range {inst['standard_range']} (concert)",
                        staff=st, events=[n.event])

def _mutes(ctx, fl: Flow, st: Staff) -> None:
    on = None
    event = {(pos, pta): eid for kind, pos, pta, eid in st.marks if kind == "technique"}
    for pos, pta in sorted(st.techniques):
        low = pta.lower()
        if "mute" in low and "off" not in low and "remove" not in low or "consordino" in low:
            on = (pos, pta)
        elif "open" in low or "senza" in low or "muteoff" in low or "remove" in low:
            on = None
    if on:
        ctx.add("mute-not-released", "info", fl, st.label, on[0], f"{on[1]} is never released",
                staff=st, events=[event.get(on, "")])


def _sections(ctx, fl: Flow) -> None:
    """Staves playing the same rhythm over a phrase with the same (or nearly the same)
    dynamics at the same position, not sharing one (linked) element. Reported once per
    position and set of staves."""
    for check in ("could-link", "could-align"):
        for pos, members in section_clusters(fl, check):
            msg = ("identical dynamics and rhythm, not linked" if check == "could-link"
                   else "same dynamics and rhythm; hairpin positions differ slightly")
            ctx.add(check, "info", fl, ", ".join(st.label for st, _ in members), pos, msg,
                    staff=[st for st, _ in members], events=[g.event for _, g in members])



# Registration order = run order and report order (as f2d's reviewer always listed them)
findings.register_check("dynamic-clash", "Two different dynamics at the same position on one staff", _dynamics)
findings.register_check("dynamic-in-silence", "Dynamic where nothing is sounding on that staff")
findings.register_check("hairpin-in-silence", "Hairpin that starts in, or mostly covers, a rest")
findings.register_check("repeated-dynamic", "Same dynamic again with no change in between")
findings.register_check("duplicate", "The same marking twice at one position", _duplicates)
findings.register_check("could-link", "Identical dynamics on staves playing the same rhythm, not linked",
                        _sections, scope="flow")
findings.register_check("could-align", "Nearly identical dynamics on staves playing the same rhythm (hairpins differ slightly)")
findings.register_check("range", "Note outside the instrument's range (Dorico's standard / advanced range)", _range)
findings.register_check("mute-not-released", "Mute (or con sord.) with no later open / senza sord.", _mutes)


def review(path: str | Path, only: list[str] | None = None) -> list[Finding]:
    return Reviewer(read_project(path)).run(only)


def _description(check: str) -> str:
    c = findings.checks().get(check)
    return c.description if c else ""


def format_text(findings: list[Finding], limit: int | None = 12) -> str:
    out = []
    by_check = defaultdict(list)
    for f in findings:
        by_check[(f.severity, f.check)].append(f)
    for (sev, check), fs in sorted(by_check.items(), key=lambda kv: (kv[0][0] != "warning", kv[0][1])):
        out.append(f"{sev.upper():7} {check} ({len(fs)}): {_description(check)}")
        for f in fs[: limit or len(fs)]:
            loc = ", ".join(x for x in (f.player, f.where) if x)
            out.append(f"          {loc}: {f.message}" if loc else f"          {f.message}")
        if limit and len(fs) > limit:
            out.append(f"          ... {len(fs) - limit} more (use --all)")
    if not findings:
        out.append("Nothing to report.")
    return "\n".join(out)


def to_json(items: list[Finding], project: str) -> str:
    return findings.to_json(items, project, "checks")
