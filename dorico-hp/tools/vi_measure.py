"""Measure how the Kontakt instruments respond, from test notes rendered in Cubase (Project C).

  kit      one Cubase track archive per Dorico project: every Kontakt rack slot that players use
           becomes one Kontakt 7 instrument track with the exact state Dorico saved (Kontakt 6
           states converted, see doricokit.virender.PluginState.kontakt7_state) and one MIDI part
           that tests each used MIDI channel in turn. The user imports the archives (File >
           Import > Track Archive) and exports all tracks at once (Channel Batch Export).
  analyse  measure the exported WAVs (one per track) against the plans

    K=/mnt/c/Users/kspie/Documents/HPCaptures/kontakt
    uv run --with numpy python dorico-hp/tools/vi_measure.py kit --out $K
    uv run --with numpy python dorico-hp/tools/vi_measure.py analyse $K/renders

What each channel gets depends on its expression map (`doricohp.playback`):
  dynamics by CC (LASS CC1, IW CC11, IB CC1, the SWAM maps on Sample Modeling brass CC11):
      E range, A level vs that CC, B short notes, C velocity -> attack, D legato
  velocity only, sustaining instrument (strings, winds, brass, voices; "Default" maps):
      E, A level vs velocity, A level vs CC1 and vs CC11 (does the patch use them?), D
  velocity only, struck/plucked (harp, mallets, keyboards, bells): E, A level vs velocity
  further players with the same map and instrument on the same slot: E and A only
Skipped for now: unpitched percussion and the CinePerc/Cinesamples slots (CinePerc doesn't load in
Kontakt 7; the user loads those by hand later).
Each channel's segment starts with the map's init actions and its natural technique's switch
(CCs, keyswitch notes). Tests, timing and analysis are swam_measure's (same batteries, generalised
to the map's dynamics controller); plans and results go to research/vi/measurements/.
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "engine/python"))
sys.path.insert(0, str(ROOT / "dorico-hp"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from doricokit import cubase  # noqa: E402
from doricokit import virender as vr  # noqa: E402
import swam_measure as sm  # noqa: E402

RESULTS = ROOT / "dorico-hp/research/vi/measurements"
PROJECTS = sm.PROJECTS
SOURCES = {"hp": "Harry Potter Cues Plus 5 + LASS3.dorico", "tpl": "Full Orchestra Template NEW FULL v5.dorico"}
LEAD = 1.0       # s from a segment's start (actions) to its first test note
SEG_GAP = 3.0    # s between channel segments
SKIP_MAPS = ("CineSamples", "Percussion - Mod Wheel Rolls")   # CinePerc: later, by hand

# sounding ranges (MIDI) as Dorico sends them, by instrument entity id (longest prefix wins)
RANGES = {
    "instrument.strings.violin": (55, 100), "instrument.strings.viola": (48, 88),
    "instrument.strings.violoncello": (36, 76), "instrument.strings.contrabass": (28, 67),
    "instrument.wind.flute": (60, 96), "instrument.wind.flute.alto": (55, 91), "instrument.wind.flute.bass": (48, 84),
    "instrument.wind.piccolo": (74, 108), "instrument.wind.oboe": (58, 91),
    "instrument.wind.coranglais": (52, 81), "instrument.wind.clarinet": (50, 91),
    "instrument.wind.clarinet.eflat": (55, 93), "instrument.wind.clarinet.bass": (34, 72),
    "instrument.wind.clarinet.contrabass": (22, 58), "instrument.wind.bassoon": (34, 75),
    "instrument.wind.contrabassoon": (22, 53), "instrument.wind.saxophone.soprano": (56, 87),
    "instrument.wind.saxophone.alto": (49, 81), "instrument.wind.saxophone.tenor": (44, 76),
    "instrument.wind.saxophone.baritone": (36, 69),
    "instrument.brass.horn": (34, 77), "instrument.brass.trumpet": (52, 82), "instrument.brass.trombone": (40, 72),
    "instrument.brass.trombone.bass": (34, 67), "instrument.brass.tuba": (28, 58), "instrument.brass.euphonium": (40, 70),
    "instrument.pitchedpercussion.harp": (24, 103), "instrument.pitchedpercussion.timpani": (38, 57),
    "instrument.pitchedpercussion.glockenspiel": (79, 108), "instrument.pitchedpercussion.marimba": (45, 96),
    "instrument.pitchedpercussion.xylophone": (65, 108), "instrument.pitchedpercussion.vibraphone": (53, 89),
    "instrument.pitchedpercussion.crotales": (84, 108), "instrument.pitchedpercussion.bells.tubular": (60, 77),
    "instrument.keyboard.celesta": (60, 108), "instrument.keyboard.piano": (21, 108),
    "instrument.keyboard.harpsichord": (29, 89), "instrument.keyboard.synthesizer": (36, 96),
    "instrument.singers.treble": (60, 81), "instrument.singers.choir": (40, 81),
}
MAP_RANGES = {"Joshua Bell violin": (55, 100)}
SUSTAINING = ("instrument.strings.", "instrument.wind.", "instrument.brass.", "instrument.singers.")


def entity_range(entity: str, map_name: str) -> tuple[int, int]:
    if map_name in MAP_RANGES:
        return MAP_RANGES[map_name]
    best = max((k for k in RANGES if entity.startswith(k)), key=len, default=None)
    return RANGES[best] if best else (36, 96)


@dataclass
class Target:
    """One MIDI channel of one rack slot, as players use it."""
    project: str              # key in SOURCES
    slot: int                 # Dorico slot (pluginRackContents slotID)
    channel: int              # 0-based
    players: list[str]
    entity: str
    map_name: str
    dyn: str                  # "CC1", "CC11", ... or "velocity"
    actions: list[tuple[str, int, int]]   # init + natural switch actions
    lo: int = 0
    hi: int = 0
    tests: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        who = re.sub(r"[^a-z0-9]+", "-", self.players[0].lower()).strip("-")[:24]
        return f"{self.project}-s{self.slot:02d}-c{self.channel + 1:02d}-{who}"


def targets(project_key: str) -> tuple[dict[int, vr.PluginState], list[Target]]:
    from doricohp.playback import PlaybackSetup
    from doricohp.project import Project
    path = PROJECTS / SOURCES[project_key]
    p = Project(str(path))
    ps = PlaybackSetup(p)
    states = {s.dorico_slot: s for s in vr.plugin_states(path)}
    names: dict[str, str] = {}
    for f in p.flows():
        for i in p.instruments(f):
            names.setdefault(i.instrument_id, i.player_name)
    found: dict[tuple[int, int], Target] = {}
    for iid, ip in ps.instruments.items():
        for e in ip.endpoints:
            slot, port, ch = e >> 10, (e >> 4) & 63, e & 15
            st = states.get(slot)
            plugin, map_id = ps.slots.get((slot, port, ch), ("", None))
            m = ps.maps.get(map_id)
            if st is None or not st.kontakt7_state() or m is None or port != 0:
                continue
            if ".unpitched." in ip.entity or any(k in m.name for k in SKIP_MAPS):
                continue
            nat = m.natural
            dyn = str(nat.volume) if nat and nat.volume else "velocity"
            t = found.get((slot, ch))
            if t is None:
                acts = list(m.init_actions) + list(nat.actions if nat else [])
                t = found[(slot, ch)] = Target(project_key, slot, ch, [], ip.entity, m.name, dyn, acts)
            who = names.get(iid, iid).replace("{@flat@}", "b").replace("{@sharp@}", "#")
            if who not in t.players:
                t.players.append(who)
    out = sorted(found.values(), key=lambda t: (t.slot, t.channel))
    seen: set[tuple[int, str, str]] = set()
    for t in out:
        t.lo, t.hi = entity_range(t.entity, t.map_name)
        repeat = (t.slot, t.map_name, t.entity) in seen
        seen.add((t.slot, t.map_name, t.entity))
        if t.dyn.startswith("CC"):
            t.tests = ["E", "A"] if repeat else ["E", "A", "B", "C", "D"]
        elif t.entity.startswith(SUSTAINING):
            t.tests = ["E", "A"] if repeat else ["E", "A", "A:CC1", "A:CC11", "D"]
        else:
            t.tests = ["E", "A"]
    return states, out


# ---------------------------------------------------------------- tests

class Seg:
    """A channel's tests on the track timeline (absolute seconds)."""

    def __init__(self, tgt: Target, start: float):
        self.tgt, self.ch = tgt, tgt.channel
        self.events: list[cubase.Event] = []
        self.items: list[dict] = []
        t = start
        for kind, a, b in tgt.actions:
            if kind == "kControlChange":
                self.events.append(cubase.cc(t, self.ch, a, b))
            elif kind == "kKeySwitch":
                self.events.append(cubase.note(t, self.ch, a, b or 100, 0.1))
                t += 0.15
            else:
                print(f"warning: {tgt.key}: action {kind} {a} {b} not sent", file=sys.stderr)
        self.t = start + LEAD

    def regs(self, n: int = 6) -> list[int]:
        lo, hi = self.tgt.lo, self.tgt.hi
        fr = (0.05, 0.23, 0.41, 0.59, 0.77, 0.95) if n == 6 else (0.1, 0.37, 0.63, 0.9)
        return [int(round(lo + (hi - lo) * f)) for f in fr]

    def play(self, test: str, pitch: int, dyn: int, vel: int, dur: float, ctl: str | None = None, **extra) -> None:
        """One test note at self.t with the dynamics controller `ctl` (default: the map's) at `dyn`."""
        ctl = ctl or self.tgt.dyn
        if ctl.startswith("CC"):
            self.events.append(cubase.cc(self.t - 0.1, self.ch, int(ctl[2:]), dyn))
        else:
            vel = dyn
        self.events.append(cubase.note(self.t, self.ch, pitch, vel, dur))
        self.items.append(dict(test=test, t=round(self.t, 4), ch=self.ch, pitch=pitch, dyn=dyn, dyn_ctl=ctl,
                               vel=vel, dur=dur, **extra))

    def end(self) -> float:
        return max([e.t + e.dur for e in self.events] + [self.t])


def bat_e(S: Seg, _=None):
    step = 0.8 if S.tgt.entity.startswith(SUSTAINING) else 1.0
    for p in range(S.tgt.lo - 3, S.tgt.hi + 4):
        S.play("E", p, 80, 80, 0.45)
        S.t += step


def bat_a(S: Seg, ctl: str | None = None):
    levels = (1, 16, 32, 48, 64, 80, 96, 112, 127)
    ctl = ctl or S.tgt.dyn
    for p in S.regs(4 if ctl != S.tgt.dyn else 6):
        for v in levels:
            S.play("A", p, v, 80, 1.5, ctl=ctl)
            S.t += 2.3


def bat_b(S: Seg, _=None):
    r = S.regs()
    for p in (r[2], r[4]):
        for vel in (70, 115):
            for d in (0.02, 0.03, 0.04, 0.05, 0.06, 0.08, 0.10, 0.12, 0.15, 0.20, 0.30, 0.50, 1.0):
                S.play("B", p, 90 if S.tgt.dyn.startswith("CC") else vel, vel, d)
                S.t += d + 0.9


def bat_c(S: Seg, _=None):
    r = S.regs()
    for p in (r[1], r[3]):
        for vel in (1, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120, 127):
            S.play("C", p, 90, vel, 0.6)
            S.t += 1.5


def bat_d(S: Seg, _=None):
    a = S.regs()[2]
    cc_dyn = S.tgt.dyn.startswith("CC")
    for b in (a + 2, a + 7):
        for g in (-0.05, -0.02, -0.01, 0.0, 0.005, 0.01, 0.015, 0.02, 0.03, 0.04, 0.06, 0.08, 0.12):
            if cc_dyn:
                S.events.append(cubase.cc(S.t - 0.1, S.ch, int(S.tgt.dyn[2:]), 90))
            S.events.append(cubase.note(S.t, S.ch, a, 90, 0.5))
            S.events.append(cubase.note(S.t + 0.5 + g, S.ch, b, 90, 0.5))
            S.items.append(dict(test="D", t=round(S.t, 4), ch=S.ch, a=a, b=b, vel=90, gap=g, dur=0.5))
            S.t += 2.0 + max(g, 0)


BATTERIES = {"E": bat_e, "A": bat_a, "B": bat_b, "C": bat_c, "D": bat_d}


def build_segment(tgt: Target, start: float) -> Seg:
    S = Seg(tgt, start)
    for i, test in enumerate(tgt.tests):
        if i:
            S.t += sm.GAP
        name, _, arg = test.partition(":")
        BATTERIES[name](S, arg or None)
    return S


# ---------------------------------------------------------------- commands

README = """Kontakt test renders (dorico-hp, Project C)                      {date}

What this is: test notes for every Kontakt instrument your players use in
{projects}
with the exact Kontakt settings saved in those projects (Kontakt 6 ones converted to Kontakt 7).
Rendering them lets me measure how each library responds (range, loudness per dynamic and
register, short notes, attacks, legato) to tune the expression maps and playback profiles.
Not included yet: CinePerc / Cinesamples and unpitched percussion (you'll load those by hand
later).

Files
  {archives}
  renders\\                       put the exported WAVs here

Steps (Cubase 13; one project, one export)
 1. New empty project. Project > Project Setup: sample rate 48 kHz.
 2. Transport bar: tempo Fixed (not Tempo Track), 120 bpm, 4/4.
 3. File > Import > Track Archive..., pick an archive above; in the import dialog keep all
    tracks selected, OK. Wait until Kontakt has loaded everything (watch the Kontakt windows /
    sample loading). Repeat for the other archive. If the computer runs short of memory, do
    one archive per project/export instead and tell me.
 4. Don't change anything in the tracks or plug-ins (no inserts, faders at 0 dB). The parts
    start at bar 1; each track tests its channels one after another.
 5. Locators: left at bar 1, right at the end of the longest part (select all parts, press P).
 6. File > Export > Audio Mixdown:
      - Channel Batch Export: tick all the instrument channels from the archives
      - Path: this folder's renders\\ ; naming: channel name is fine
      - Wave, 48 kHz, 32 bit float; Real-Time Export OFF
    Export.
 7. Tell me the files are there, and anything odd (a track that didn't load, missing-sample
    messages, a channel that stays silent).

Tracks (longest part {mins} min)
{table}
"""


def cmd_kit(a):
    out = Path(a.out)
    (out / "renders").mkdir(parents=True, exist_ok=True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    rows, archives, longest = [], [], 0.0
    for pk in a.projects.split(","):
        states, tg = targets(pk)
        arc = cubase.TrackArchive()
        by_slot: dict[int, list[Target]] = {}
        for t in tg:
            by_slot.setdefault(t.slot, []).append(t)
        for slot, ts in by_slot.items():
            st = states[slot]
            track = f"{pk.upper()} s{slot:02d} {ts[0].map_name}"[:60]
            t0, segs, events = 0.0, [], []
            for t in ts:
                S = build_segment(t, t0)
                segs.append(S)
                events += S.events
                t0 = S.end() + SEG_GAP
            arc.add(track, st.kontakt7_state(), events, label=f"{SOURCES[pk][:-7]} slot {slot}")
            plan = {"project": SOURCES[pk], "slot": slot, "track": track, "tempo_bpm": 120,
                    "end_s": round(t0, 3), "segments": [
                        {"key": S.tgt.key, "channel": S.ch + 1, "players": S.tgt.players, "entity": S.tgt.entity,
                         "map": S.tgt.map_name, "dyn": S.tgt.dyn, "range": [S.tgt.lo, S.tgt.hi],
                         "actions": S.tgt.actions, "tests": S.tgt.tests, "items": S.items} for S in segs]}
            (RESULTS / f"{pk}-s{slot:02d}.plan.json").write_text(json.dumps(plan, indent=1))
            longest = max(longest, t0 / 60)
            rows.append(f"  {track:44s} {t0 / 60:5.1f} min  " + "; ".join(
                f"ch{S.ch + 1} {S.tgt.players[0][:22]} ({S.tgt.dyn}, {'/'.join(S.tgt.tests)})" for S in segs))
            print(rows[-1])
        name = f"{pk}-kontakt.xml"
        arc.write(out / name)
        archives.append(f"{name:30s} from {SOURCES[pk]}")
    (out / "README.txt").write_text(README.format(
        date=datetime.date.today(), projects="\n".join("  " + SOURCES[p] for p in a.projects.split(",")),
        archives="\n  ".join(archives), mins=round(longest, 1), table="\n".join(rows)).replace("\n", "\r\n"),
        encoding="utf-8")
    print(f"kit -> {out}")


def track_wavs(renders: Path, track: str) -> list[Path]:
    """Every exported WAV of a track: its own channel and any activated Kontakt output channels
    (all carry the track's "HP s13" prefix; any folder depth, any Cubase naming around it)."""
    norm = lambda s: re.sub(r"[^a-z0-9]+", "", s.lower())
    tag = norm(" ".join(track.split()[:2]))      # "hps13"
    return sorted(w for w in renders.rglob("*.wav")
                  if re.search(tag + r"(?![0-9])", norm(w.stem)))


def _float_view(path: Path):
    """(sample rate, channels, float32 memmap) of a 32-bit float WAV, or None for other formats."""
    import numpy as np
    with open(path, "rb") as f:
        head = f.read(1 << 16)
    pos, fmt = 12, None
    while pos + 8 <= len(head):
        cid, n = head[pos:pos + 4], int.from_bytes(head[pos + 4:pos + 8], "little")
        if cid == b"fmt ":
            tag, nch, sr = int.from_bytes(head[pos + 8:pos + 10], "little"), \
                int.from_bytes(head[pos + 10:pos + 12], "little"), int.from_bytes(head[pos + 12:pos + 16], "little")
            bits = int.from_bytes(head[pos + 22:pos + 24], "little")
            if tag == 0xFFFE:
                tag = int.from_bytes(head[pos + 32:pos + 34], "little")
            fmt = (tag, nch, sr, bits)
        elif cid == b"data":
            if not fmt or fmt[0] != 3 or fmt[3] != 32:
                return None
            return fmt[2], fmt[1], np.memmap(path, dtype="<f4", mode="r", offset=pos + 8, shape=(n // 4,))
        pos += 8 + n + (n & 1)
    return None


def segment_level(path: Path, t0: float, t1: float) -> float:
    """Mean square of a time window (sparse read), to find which output a channel plays on."""
    v = _float_view(path)
    if v is None:
        au = sm.Audio(path)
        return float(10 ** (au.mean_db(t0, t1) / 10))
    sr, nch, x = v
    seg = x[int(t0 * sr) * nch:int(t1 * sr) * nch:97 * nch]
    return float((seg.astype("f8") ** 2).mean()) if len(seg) else 0.0


def cmd_analyse(a):
    renders = Path(a.renders)
    plans = sorted(RESULTS.glob(f"{a.only or ''}*.plan.json"))
    for pf in plans:
        plan = json.loads(pf.read_text())
        wavs = track_wavs(renders, plan["track"])
        if not wavs:
            print(f"## {plan['track']}: no WAV in {renders}")
            continue
        audio: dict[Path, sm.Audio] = {}
        out = {"wavs": [str(w) for w in wavs], "plan": pf.name, "segments": []}
        for seg in plan["segments"]:
            items = seg["items"]
            t0, t1 = items[0]["t"], max(it["t"] + it.get("dur", 0.5) for it in items)
            levels = {w: segment_level(w, t0, t1) for w in wavs}
            wav = max(levels, key=levels.get)
            head = f"## {plan['track']} / ch{seg['channel']} {', '.join(seg['players'])} ({seg['map']}, {seg['dyn']})"
            if levels[wav] < 1e-12:
                print(f"{head}\nsilent on every output ({len(wavs)} WAVs)\n")
                out["segments"].append({"key": seg["key"], "silent": True})
                continue
            if wav not in audio:
                audio = {wav: sm.Audio(wav)}      # one decoded WAV in memory at a time
            au = audio[wav]
            res = sm.analyse_items(au, items)
            al = sm.alignment(au, items, pre=LEAD)
            out["segments"].append({"key": seg["key"], "wav": str(wav), "alignment": al, "results": res})
            print(f"{head}\noutput {wav.name}\nalignment {al}\n{sm.summary(res)}\n")
        (RESULTS / pf.name.replace(".plan.json", ".json")).write_text(json.dumps(out, indent=1))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    k = sub.add_parser("kit", help="write the Cubase track archives + README")
    k.add_argument("--out", required=True)
    k.add_argument("--projects", default="hp,tpl", help=f"comma list of {','.join(SOURCES)}")
    n = sub.add_parser("analyse", help="measure the exported WAVs")
    n.add_argument("renders", help="folder with the exported WAVs (searched recursively)")
    n.add_argument("--only", default="", help="plan name prefix, e.g. hp-s09")
    a = ap.parse_args()
    {"kit": cmd_kit, "analyse": cmd_analyse}[a.cmd](a)


if __name__ == "__main__":
    main()
