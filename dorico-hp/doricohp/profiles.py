"""Layered settings: defaults → style → library → instrument → project.

    settings = Profiles(style="Romantic", project_file="Piece.hp.toml")
    s = settings.for_part(part_name, map_name, plugin_name, entity)
    s["espressivo"]["depth_at_mood_76"], s["style"]["mood"], s["library"] …

Styles come from Finale's own preset table (data/hp-presets.tsv, extracted from
Finale.exe); the HP parameters are exposed as s["style"][...] with HP's names
(rhythmicFeel, rhythmicAccents, rubato, mood, swing, flags such as emphasizeShortSyncops).
"""
from __future__ import annotations

import copy
import csv
import re
import tomllib
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"


def deep_merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def load_styles() -> dict[str, dict]:
    styles = {}
    with open(DATA / "hp-presets.tsv") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            st = {}
            for k, v in row.items():
                if k in ("index",) or k.startswith("x") or k is None:
                    continue
                if k == "name":
                    st[k] = v
                elif v in ("", None):
                    st[k] = 0 if k in ("rhythmicFeel", "rhythmicAccents", "rubato", "reverb", "swing", "mood") else False
                elif k in ("rhythmicFeel", "rhythmicAccents", "rubato", "reverb", "selectedPreset", "swing", "mood"):
                    st[k] = int(v)
                else:
                    st[k] = v == "1"
            styles[row["name"].lower()] = st
    return styles


class Profiles:
    def __init__(self, style: str | None = None, project_file: str | Path | None = None,
                 overrides: dict | None = None):
        self.defaults = tomllib.loads((DATA / "defaults.toml").read_text())
        self.libraries = tomllib.loads((DATA / "libraries.toml").read_text()).get("library", {})
        self.project = {}
        if project_file and Path(project_file).exists():
            self.project = tomllib.loads(Path(project_file).read_text())
        if overrides:
            self.project = deep_merge(self.project, overrides)
        self.styles = load_styles()
        name = (style or self.project.get("style", {}).get("name") or self.defaults["style"]["name"]).lower()
        if name not in self.styles:
            raise KeyError(f"unknown style {name!r}; known: {', '.join(sorted(self.styles))}")
        self.style = dict(self.styles[name])
        # project may tweak individual HP parameters: [style] mood = 60
        for k, v in self.project.get("style", {}).items():
            if k != "name":
                self.style[k] = v

    def library_for(self, *names: str) -> tuple[str, dict]:
        hay = " | ".join(n for n in names if n)
        for key, lib in self.libraries.items():
            if re.search(lib.get("match", "$^"), hay, re.I):
                return key, lib
        return "default", {}

    def for_part(self, part_name: str, map_name: str = "", plugin: str = "", entity: str = "") -> dict:
        key, lib = self.library_for(map_name, plugin, entity, part_name)
        s = deep_merge(self.defaults, {k: v for k, v in lib.items() if k not in ("match", "instrument")})
        for word, over in lib.get("instrument", {}).items():
            if word.lower() in part_name.lower():
                s = deep_merge(s, over)
        proj = {k: v for k, v in self.project.items() if k not in ("style", "instrument", "library")}
        s = deep_merge(s, proj)
        # project-level library and instrument overrides
        s = deep_merge(s, self.project.get("library", {}).get(key, {}))
        for word, over in self.project.get("instrument", {}).items():
            if word.lower() in part_name.lower():
                s = deep_merge(s, over)
        s["style"] = dict(self.style)
        s["library"] = key
        return s
