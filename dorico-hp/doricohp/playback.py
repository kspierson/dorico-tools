"""What a Dorico project's playback setup does with each instrument.

Reads, from the project itself:
- playback options (`/kScore/scoreOptions/playbackOptions`), as a flat dict
  ("timingOptions.staccatoDurationPercent" -> "50"),
- the expression maps it embeds (`/kScore/library/expressionMapDefinitions`, falling back
  to `scorelibrary.dtn`),
- which plug-in slot / channel / expression map each instrument plays through
  (`/kScore/playModeData`: `pluginRackContents` lists slots and the map on each channel;
  `instrumentPlaybackData` lists each instrument's endpoints per technique).

Endpoint ids encode slot << 10 | port << 4 | channel (confirmed on the user's LASS 3
project: 9218 = slot 9, channel 2 = Violin II on the LASS divisi patch).

    python3 -m doricohp.playback Project.dorico      # summary per instrument
"""
from __future__ import annotations

import sys
from collections import Counter
from dataclasses import dataclass, field

from doricokit import format as dtn
from .project import Project, items


@dataclass
class Controller:
    kind: str           # "vel" or "cc"
    number: int = 0

    def __str__(self) -> str:
        return "velocity" if self.kind == "vel" else f"CC{self.number}"


@dataclass
class Combination:
    techniques: tuple[str, ...]
    volume: Controller | None
    volume2: Controller | None
    attack: Controller | None
    volume_range: tuple[int, int]
    length_factor: float
    velocity_factor: float
    condition: str
    actions: list[tuple[str, int, int]]


@dataclass
class ExpressionMap:
    id: str
    name: str
    combinations: list[Combination] = field(default_factory=list)
    addons: dict[str, list[tuple[str, int, int]]] = field(default_factory=dict)
    init_actions: list[tuple[str, int, int]] = field(default_factory=list)
    option_overrides: dict[str, str] = field(default_factory=dict)

    @property
    def natural(self) -> Combination | None:
        for c in self.combinations:
            if c.techniques in (("pt.natural",), ()):
                return c
        return self.combinations[0] if self.combinations else None

    def techniques(self) -> set[str]:
        out = set()
        for c in self.combinations:
            out.update(c.techniques)
        out.update(self.addons)
        return out

    def dynamics_controllers(self) -> set[int]:
        """CC numbers that carry dynamics in any combination (owned by Dorico)."""
        out = set()
        for c in self.combinations:
            for v in (c.volume, c.volume2):
                if v is not None and v.kind == "cc":
                    out.add(v.number)
        return out

    def switched_controllers(self) -> set[int]:
        """CC numbers sent by technique switches (also owned by Dorico)."""
        out = set()
        for c in self.combinations:
            out.update(n for t, n, _ in c.actions if t == "kControlChange")
        for acts in self.addons.values():
            out.update(n for t, n, _ in acts if t == "kControlChange")
        return out

    def init_controllers(self) -> dict[int, int]:
        return {n: v for t, n, v in self.init_actions if t == "kControlChange"}


@dataclass
class InstrumentPlayback:
    instrument_id: str
    entity: str
    endpoints: list[int]
    plugins: list[str]
    maps: list[ExpressionMap]

    @property
    def map(self) -> ExpressionMap | None:
        return self.maps[0] if self.maps else None


def _ctl(n) -> Controller | None:
    if n is None:
        return None
    t = n.text("type")
    if t == "kNoteVelocity":
        return Controller("vel")
    if t == "kCC":
        return Controller("cc", int(n.text("param1") or 0))
    return None


def _actions(n) -> list[tuple[str, int, int]]:
    return [(a.text("type"), int(a.text("param1") or 0), int(a.text("param2") or 0)) for a in items(n)]


def _range(s: str) -> tuple[int, int]:
    try:
        a, b = s.split(",")
        return int(a), int(b)
    except ValueError:
        return 1, 127


def parse_map(m) -> ExpressionMap:
    em = ExpressionMap(m.text("entityID"), m.text("name"))
    em.init_actions = _actions(m.find("initSwitchData/initActions"))
    for o in items(m.child("playbackOptionsOverrides")):
        em.option_overrides[o.text("option")] = o.text("value").replace("int: ", "")
    for c in items(m.child("playingTechniqueCombinations")):
        if c.text("enabled") == "false":
            continue
        techs = tuple(t.strip() for t in c.text("techniqueIDs").split("+") if t.strip())
        em.combinations.append(Combination(
            techs, _ctl(c.child("volumeType")), _ctl(c.child("volumeType2")), _ctl(c.child("attackType")),
            _range(c.text("velocityRange", "1,127")), float(c.text("lengthFactor") or 1),
            float(c.text("velocityFactor") or 1), c.text("conditionString"), _actions(c.child("switchOnActions"))))
    for a in items(m.child("techniqueAddOns")):
        for t in a.text("techniqueIDs").split("+"):
            if t.strip():
                em.addons[t.strip()] = _actions(a.child("switchOnActions"))
    return em


def _flatten(n, prefix="", out=None) -> dict[str, str]:
    out = {} if out is None else out
    for c in n.children or ():
        key = f"{prefix}.{c.tag}" if prefix else c.tag
        if c.children:
            _flatten(c, key, out)
        else:
            out[key] = c.value or ""
    return out


class PlaybackSetup:
    def __init__(self, project: Project):
        root = project.root
        self.options = _flatten(root.find("scoreOptions/playbackOptions")) if root.find("scoreOptions/playbackOptions") else {}
        maps = {}
        for m in items(root.find("library/expressionMapDefinitions/entities")):
            em = parse_map(m)
            maps[em.id] = em
        if not maps:
            data = project.entry("scorelibrary.dtn")
            if data is not None:
                lib = dtn.decode(data).root
                for m in items(lib.find("expressionMapDefinitions/entities")):
                    em = parse_map(m)
                    maps[em.id] = em
        self.maps = maps
        pm = root.child("playModeData")
        self.slots: dict[tuple[int, int, int], tuple[str, str]] = {}
        for e in items(pm.find("pluginRackContents/entries")) if pm is not None else ():
            for ch in items(e.find("programContents/entries")):
                self.slots[(int(e.text("slotID")), int(ch.text("portIndex") or 0), int(ch.text("channelNumberRel0") or 0))] = \
                    (e.text("pluginName"), ch.text("expressionMapID"))
        self.instruments: dict[str, InstrumentPlayback] = {}
        for inst in items(pm.find("instrumentPlaybackData/entries")) if pm is not None else ():
            eps = Counter()
            for v in items(inst.child("voiceData")):
                for t in items(v.child("techniqueTracks")):
                    e = int(t.text("endpointID") or -1)
                    if e >= 0:
                        eps[e] += 1
            ordered = [e for e, _ in eps.most_common()]
            plugins, mlist = [], []
            for e in ordered:
                slot = self.slots.get((e >> 10, (e >> 4) & 63, e & 15))
                if slot:
                    plugins.append(slot[0])
                    if slot[1] in maps:
                        mlist.append(maps[slot[1]])
            self.instruments[inst.text("instrumentID")] = InstrumentPlayback(
                inst.text("instrumentID"), inst.text("instrumentEntityID"), ordered, plugins, mlist)

    def option(self, name: str, instrument_id: str | None = None, default: str = "") -> str:
        """A playback option, honouring the instrument's expression-map overrides."""
        if instrument_id is not None:
            ip = self.instruments.get(instrument_id)
            if ip and ip.map and name in ip.map.option_overrides:
                return ip.map.option_overrides[name]
        return self.options.get(name, default)


def main(path: str) -> None:
    p = Project(path)
    setup = PlaybackSetup(p)
    names = {}
    for f in p.flows():
        for i in p.instruments(f):
            names.setdefault(i.instrument_id, i.player_name)
    print(f"{len(setup.maps)} expression maps, {len(setup.slots)} channels, {len(setup.instruments)} instruments\n")
    keys = ["dynamicsOptions.primaryBeatStressDelta", "dynamicsOptions.beatStressDelta", "dynamicsOptions.dynamicHumanisePercent",
            "timingOptions.timingHumanisePercent", "timingOptions.noteDurationPercent", "timingOptions.defaultRhythmicFeel",
            "trillPlaybackOptions.trillPlaybackMode", "noteExpressionOptions.enableNoteExpression"]
    for k in keys:
        print(f"  {k} = {setup.options.get(k, '?')}")
    print()
    for iid, ip in setup.instruments.items():
        m = ip.map
        nat = m.natural if m else None
        dyn = (f"{nat.volume}" + (f" + {nat.volume2}" if nat.volume2 else "") if nat else "?")
        print(f"{names.get(iid, iid):40} {ip.plugins[0] if ip.plugins else '-':28} {m.name if m else '-':28} dyn {dyn:16} "
              f"init {m.init_controllers() if m else {}}")


if __name__ == "__main__":
    main(sys.argv[1])
