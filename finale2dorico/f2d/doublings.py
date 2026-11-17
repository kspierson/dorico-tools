"""Doublings: Finale staves that switch instrument by text become Dorico multi-instrument players.

Finale has no players: a doubling is a staff named e.g. "Piccolo (Flute 3)", "Oboe 2 / English
Horn" or "Piano/Celeste", with instructions "To Flute", "Flute", "To Picc.", "Eng. Hn." at the
switches (John Williams, E.T.). Dorico has players with several instruments, each with its own
staves; it places the instrument-change labels itself from where each instrument has music
(the user's Rite of Spring file: the InstrumentChange event only stores label overrides).

This IR -> IR transform splits such a staff into one instrument per name, in the same player.
Each note goes to the instrument named by the latest switch instruction at or before it (the
first name before any instruction). Switch texts are removed; staff markings (dynamics,
hairpins, techniques, texts, ottavas, pedals, harp pedals) follow the instrument playing there.
Clefs are copied to both. Skipped when a staff has no switch instructions.
"""
from __future__ import annotations

import copy
import re
from fractions import Fraction

from . import ir

# abbreviations seen in scores -> words to match against instrument names
ABBREVIATIONS = {
    "picc": "piccolo", "fl": "flute", "afl": "alto flute", "ob": "oboe", "e.h": "english horn",
    "eh": "english horn", "eng. hn": "english horn", "eng hn": "english horn", "eng. horn": "english horn",
    "c.a": "cor anglais", "cl": "clarinet", "b. cl": "bass clarinet", "bcl": "bass clarinet",
    "bsn": "bassoon", "cbsn": "contrabassoon", "c.bsn": "contrabassoon", "tpt": "trumpet", "flug": "flugelhorn",
    "cel": "celesta", "celeste": "celesta", "pno": "piano", "glock": "glockenspiel", "vib": "vibraphone",
    "xyl": "xylophone", "sop. sax": "soprano saxophone", "alto sax": "alto saxophone",
    "ten. sax": "tenor saxophone", "bari. sax": "baritone saxophone",
}


def _norm(s: str) -> str:
    s = s.lower().replace("\n", " ").strip().strip("()").strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\s*\d+$", "", s)  # "flute 3" -> "flute"
    s = s.rstrip(".")
    s = ABBREVIATIONS.get(s, s)
    return s.replace("celeste", "celesta").replace("cor anglais", "english horn")


def staff_instruments(name: str) -> list[str]:
    """'Piccolo\\n(Flute 3)' -> ['Piccolo', 'Flute 3']; 'Piano/Celeste' -> ['Piano', 'Celeste']."""
    parts = [p.strip().strip("()").strip() for p in re.split(r"\n|/|&|\band\b|\(", name) if p.strip().strip("()").strip()]
    return parts if len(parts) >= 2 else []


def _switch_target(text: str, names: list[str]) -> int | None:
    """Index of the instrument a switch instruction names ("To Flute", "Picc.", "(Eng. Hn.)
    Solo"), or None."""
    t = text.strip().splitlines()[0] if text.strip() else ""
    t = re.sub(r"^(to|muta in|change to)\s+", "", t.strip(), flags=re.I).strip().strip("()").strip()
    t = re.sub(r"\s+solo$", "", t, flags=re.I)
    key = _norm(t)
    for k, n in enumerate(names):
        nn = _norm(n)
        if key and (key == nn or nn.startswith(key) or key.startswith(nn)):
            return k
    return None


def apply_doublings(score: ir.Score) -> list[str]:
    report = []
    if not score.flows:
        return report
    flow = score.flows[0]
    for p in list(score.players):
        if len(p.instruments) != 1:
            continue
        inst = p.instruments[0]
        names = staff_instruments(inst.name)
        if not names:
            continue
        staves = [st for st in flow.staves if st.instrument == inst.id]
        switches = sorted((t.pos, _switch_target(t.text, names), t) for st in staves for t in st.techniques
                          if t.kind is None and _switch_target(t.text, names) is not None)
        if not switches:
            continue
        _split(score, flow, p, inst, staves, names, switches)
        report.append(f"{inst.name.replace(chr(10), ' ')}: one player, instruments {', '.join(names)} "
                      f"({len(switches)} switch instructions)")
    return report


def _split(score, flow, player, inst, staves, names, switches) -> None:
    def active(pos: Fraction) -> int:
        cur = 0
        for p, k, _ in switches:
            if p <= pos:
                cur = k
        return cur

    switch_texts = {id(t) for _, _, t in switches}
    new_insts = []
    for k, name in enumerate(names):
        ni = copy.deepcopy(inst)
        ni.name = name
        ni.short_name = ""
        if k > 0:
            ni.id = f"{inst.id}d{k}"
            ni.finale_uuid, ni.sound_id = None, None
        ni.transposition = None  # let the Dorico match decide (Finale wrote these staves in C)
        new_insts.append(ni)
    for st in staves:
        parts = []
        for k, ni in enumerate(new_insts):
            s = ir.Staff(instrument=ni.id, index=st.index, clefs=copy.deepcopy(st.clefs),
                         time_signatures=copy.deepcopy(st.time_signatures))
            for v in st.voices:
                nv = copy.deepcopy(v)
                nv.chords = [c for c in nv.chords if active(c.pos) == k]
                nv.tuplets = [t for t in nv.tuplets if active(t.pos) == k]
                nv.slurs = [x for x in nv.slurs if active(x.pos) == k]
                nv.trills = [x for x in nv.trills if active(x.pos) == k]
                nv.glissandi = [x for x in nv.glissandi if active(x.pos) == k]
                s.voices.append(nv)
            for attr in ("dynamics", "hairpins", "ottavas", "pedals", "harp_pedals", "pauses", "lines"):
                setattr(s, attr, [copy.deepcopy(x) for x in getattr(st, attr) if active(x.pos) == k])
            s.techniques = [copy.deepcopy(t) for t in st.techniques
                            if id(t) not in switch_texts and active(t.pos) == k]
            parts.append(s)
        idx = flow.staves.index(st)
        flow.staves[idx:idx + 1] = parts
    player.instruments = new_insts
    player.name = names[0]
