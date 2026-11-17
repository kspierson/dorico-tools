"""One report format for every tool, and a registry of checks and rules any tool can add to.

A **check** looks at a project and reports findings (the reviewer). A **rule** changes a copy
of a project and reports each change (the cleaner; later house styles, harpgliss ...). Both
report `Finding`s, so a UI can show "found -> fixed" side by side.

    from doricokit import findings
    findings.register_check("my-check", "What it looks for", my_fn, scope="staff")
    findings.register_rule("my-rule", "What it changes", my_rule_fn, default=False)

Check functions: scope "staff" -> fn(ctx, flow, staff); "flow" -> fn(ctx, flow);
"project" -> fn(ctx). They call `ctx.add(check, severity, flow, player, pos, message,
staff=..., events=[...])`. Rule functions: fn(ctx, flow, flow_edit) (see doricokit.clean) and
report with `ctx.change(..., events=[...], change=(before, after))`. Registration order is the
order checks run and are listed in reports.

Versions (FINDINGS_VERSION; readers accept every version, `from_dict` fills the defaults):
- 1 (2026-10-31): the shape f2d's reviewer has written since 2026-10-27: check, severity, flow,
  player, pos, where, message.
- 2 (2026-10-31): additive. Every v1 field keeps its name, meaning and position; new optional
  fields `tool`, `flow_id`, `bar`, `beat`, `staves`, `events`, `change` (see `Finding`). The
  JSON report gains `"findings_version": 2`. `change` is left out when there is none.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from typing import Callable

__all__ = ["FINDINGS_VERSION", "Finding", "Check", "Rule", "register_check", "register_rule",
           "checks", "rules", "owner_of", "to_json", "from_json"]

FINDINGS_VERSION = 2

TOOL = "doricokit"   # `tool` of findings from checks and rules registered without an owner


@dataclass
class Finding:
    # --- v1 (order kept: positional construction still works) ---
    check: str           # check or rule name
    severity: str        # "warning" | "info" (checks); "change" | "info" (rules: made / left alone)
    flow: str            # flow name
    player: str          # who, as shown to people: staff label(s) ("Violin I (divisi staff 2)")
    pos: str             # crotchets from the flow start ("n/d"); the contract's `position`
    where: str           # "bar 12 beat 3" (Dorico's bar number)
    message: str
    # --- v2 (all optional) ---
    tool: str = ""       # who reported it: the owner that registered the check/rule ("finale2dorico"),
                         # or "doricokit"; filled on output when left empty
    flow_id: str = ""    # Dorico flow ID
    bar: str = ""        # bar number as Dorico shows it ("35a", pick-up "0"): "go to bar"
    beat: str = ""       # exact beat in the bar, in the time signature's beat unit ("1", "5/2")
    staves: list[str] = field(default_factory=list)  # Dorico stave IDs (the contract's `staff`)
    events: list[str] = field(default_factory=list)  # Dorico event IDs of the items concerned
    change: dict | None = None  # rules: {"before": "...", "after": "..."} in words

    def to_dict(self) -> dict:
        d = asdict(self)
        if d["change"] is None:
            del d["change"]
        if not d["tool"]:
            d["tool"] = owner_of(self.check)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Finding":
        """Read a finding of any version (v1 has no v2 fields; unknown keys are ignored)."""
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in names})


@dataclass
class Check:
    name: str
    description: str
    fn: Callable
    scope: str           # "staff" | "flow" | "project"
    owner: str = ""      # tool that registered it ("" = doricokit)


@dataclass
class Rule:
    name: str
    description: str
    fn: Callable
    default: bool        # run when no rules are named (False: opt-in, e.g. editorial choices)
    owner: str = ""


_CHECKS: dict[str, Check] = {}
_RULES: dict[str, Rule] = {}


def register_check(name: str, description: str, fn: Callable | None = None, scope: str = "staff",
                   owner: str = "") -> None:
    """Add (or replace) a check. fn=None registers a name/description only (for findings that
    a function registered under another name adds, e.g. could-align next to could-link)."""
    if scope not in ("staff", "flow", "project"):
        raise ValueError(f"unknown scope {scope!r}")
    _CHECKS[name] = Check(name, description, fn, scope, owner)


def register_rule(name: str, description: str, fn: Callable, default: bool = False, owner: str = "") -> None:
    _RULES[name] = Rule(name, description, fn, default, owner)


def checks() -> dict[str, Check]:
    return dict(_CHECKS)


def rules() -> dict[str, Rule]:
    return dict(_RULES)


def owner_of(name: str) -> str:
    """The tool that registered a check or rule ("doricokit" for the built-in ones)."""
    reg = _CHECKS.get(name) or _RULES.get(name)
    return (reg.owner if reg and reg.owner else TOOL)


def to_json(items: list[Finding], project: str, kind: str = "checks") -> str:
    """{"findings_version", "project", "checks"|"rules": {name: description},
    "findings"|"changes": [...]}"""
    if kind == "checks":
        names, key = {n: c.description for n, c in _CHECKS.items()}, "findings"
    else:
        names, key = {n: r.description for n, r in _RULES.items()}, "changes"
    return json.dumps({"findings_version": FINDINGS_VERSION, "project": project, kind: names,
                       key: [f.to_dict() for f in items]},
                      indent=1, ensure_ascii=False)


def from_json(text: str) -> tuple[dict, list[Finding]]:
    """Read a report written by `to_json` (any version): (header, findings or changes)."""
    d = json.loads(text)
    items = d.get("findings", d.get("changes", []))
    head = {k: v for k, v in d.items() if k not in ("findings", "changes")}
    head.setdefault("findings_version", 1)
    return head, [Finding.from_dict(x) for x in items]
