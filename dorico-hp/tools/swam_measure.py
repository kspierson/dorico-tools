"""Measure how SWAM instruments respond, from test notes rendered outside Dorico (Project C).

The test notes use the user's own plug-in settings (the states Dorico saved in a project) and
the init controllers of each instrument's expression map. Two ways to render:

  kit      write a Cubase kit: one MIDI file + one SWAM preset (.swam) per instrument and a
           README with the steps; the user renders in Cubase and exports one WAV per instrument
  render   render directly with vi-render (doricokit.virender); only for plug-ins that play
           in it (SWAM v3 brass, Pianoteq; not the installed SWAM Woodwinds 2.8.1)
  analyse  measure a rendered WAV against the test plan -> research/vi/swam-measurements/

    K=/mnt/c/Users/kspie/Documents/HPCaptures/swam
    uv run --with numpy python dorico-hp/tools/swam_measure.py kit --out $K            # SWAM woodwinds
    uv run --with numpy python dorico-hp/tools/swam_measure.py render --name violin,viola,cello,double_bass
    uv run --with numpy python dorico-hp/tools/swam_measure.py analyse $K/renders/<file>.wav --name flute

Batteries, in this order in every file (times in the plan JSON):
  E  range probe: every semitone around the range -> which notes sound, at what pitch
  A  loudness vs CC11 (Expression) per register: steady level of 1.5 s notes
  B  short notes: peak level and sounding length of 20 ms .. 1 s notes vs a sustained one
  C  velocity: onset delay, rise time and overshoot per note-on velocity
  D  legato detection: gap (or overlap) between two notes -> slurred transition or new attack
"""
from __future__ import annotations

import argparse
import json
import math
import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "engine/python"))
sys.path.insert(0, str(ROOT / "dorico-hp"))
from doricokit import midi as smf  # noqa: E402
from doricokit import virender as vr  # noqa: E402

HERE = ROOT / "dorico-hp"
RESULTS = HERE / "research/vi/swam-measurements"
WIN = 0.005    # analysis window, s
PRE = 1.0      # silence before the first note, s
GAP = 2.0      # silence between batteries, s
TEMPO_US = 500000  # 120 bpm: 1 bar of 4/4 = 2 s
PPQ = 960

# key -> (source project in Dorico Projects, plug-in name, sounding range as Dorico sends it, MIDI)
WW, HP = "HP WW.dorico", "Harry Potter Cues Plus 5 + LASS3.dorico"
INSTRUMENTS = {
    "flute": (WW, "SWAM Flute 64bit", 60, 96), "piccolo": (WW, "SWAM Piccolo 64bit", 74, 108),
    "oboe": (WW, "SWAM Oboe 64bit", 58, 91), "english_horn": (WW, "SWAM English Horn 64bit", 52, 81),
    "clarinet": (WW, "SWAM Clarinet 64bit", 50, 91), "bass_clarinet": (WW, "SWAM Bass Clarinet 64bit", 34, 72),
    "bassoon": (WW, "SWAM Bassoon 64bit", 34, 75), "contrabassoon": (WW, "SWAM Contrabassoon 64bit", 22, 53),
    "violin": (HP, "SWAM Violin 3", 55, 100), "viola": (HP, "SWAM Viola 3", 48, 88),
    "cello": (HP, "SWAM Cello 3", 36, 76), "double_bass": (HP, "SWAM Double Bass 3", 28, 67),
}
PROJECTS = Path("/mnt/c/Users/kspie/Documents/Dorico Projects")


def source(name: str, project: str | None = None) -> tuple[str, vr.PluginState]:
    """(project path, plug-in state) for an instrument: the first slot with its plug-in."""
    proj = project or str(PROJECTS / INSTRUMENTS[name][0])
    st = next((s for s in vr.plugin_states(proj) if s.name == INSTRUMENTS[name][1]), None)
    if st is None:
        raise SystemExit(f"{name}: no {INSTRUMENTS[name][1]!r} in {proj}")
    return proj, st


def registers(name: str) -> list[int]:
    _, _, lo, hi = INSTRUMENTS[name]
    return [int(round(lo + (hi - lo) * f)) for f in (0.05, 0.23, 0.41, 0.59, 0.77, 0.95)]


# ---------------------------------------------------------------- plan

class Plan:
    """Timed events (seconds) + what each test note is for."""

    def __init__(self, name: str, init: dict[int, int]):
        self.name, self.init = name, init
        self.events: list[tuple[float, str, int, int, float]] = []  # (t, "cc"|"note", a, b, dur)
        self.items: list[dict] = []
        self.t = PRE
        for c, v in init.items():
            self.events.append((0.0, "cc", c, v, 0.0))

    def cc(self, t, num, v):
        self.events.append((t, "cc", num, v, 0.0))

    def note(self, t, pitch, vel, dur):
        self.events.append((t, "note", pitch, vel, dur))

    def end(self) -> float:
        return max(t + d for t, _, _, _, d in self.events)

    def to_events(self) -> vr.Events:
        ev = vr.Events()
        for t, k, a, b, d in self.events:
            ev.cc(t, a, b) if k == "cc" else ev.note(t, a, b, d)
        return ev

    def to_midi(self, path: Path) -> None:
        tick = lambda s: int(round(s * PPQ * 1_000_000 / TEMPO_US))
        tr = smf.Track(name=f"SWAM {self.name}")
        for t, k, a, b, d in self.events:
            if k == "cc":
                tr.ctrls.append((tick(t), a, b))
            else:
                tr.notes.append((tick(t), a, b, max(1, tick(t + d) - tick(t))))
        smf.write(path, [tr], ppq=PPQ, tempos=[(0, TEMPO_US)], time_sigs=[(0, 4, 4)])


def battery_e(P: Plan):
    _, _, lo, hi = INSTRUMENTS[P.name]
    for p in range(lo - 3, hi + 3):
        P.cc(P.t - 0.1, 11, 80)
        P.note(P.t, p, 80, 0.45)
        P.items.append(dict(test="E", t=P.t, pitch=p, cc11=80, vel=80, dur=0.45))
        P.t += 0.8


def battery_a(P: Plan):
    for p in registers(P.name):
        for cc in (1, 8, 16, 24, 32, 40, 48, 56, 64, 72, 80, 88, 96, 104, 112, 120, 127):
            P.cc(P.t - 0.1, 11, cc)
            P.note(P.t, p, 80, 1.5)
            P.items.append(dict(test="A", t=P.t, pitch=p, cc11=cc, vel=80, dur=1.5))
            P.t += 2.3


def battery_b(P: Plan):
    regs = registers(P.name)
    for p in (regs[2], regs[4]):
        for cc in (64, 110):
            for vel in (70, 115):
                for d in (0.02, 0.03, 0.04, 0.05, 0.06, 0.08, 0.10, 0.12, 0.15, 0.20, 0.30, 0.50, 1.0):
                    P.cc(P.t - 0.1, 11, cc)
                    P.note(P.t, p, vel, d)
                    P.items.append(dict(test="B", t=P.t, pitch=p, cc11=cc, vel=vel, dur=d))
                    P.t += d + 0.9


def battery_c(P: Plan):
    regs = registers(P.name)
    for p in (regs[1], regs[3]):
        for cc in (50, 100):
            for vel in (1, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120, 127):
                P.cc(P.t - 0.1, 11, cc)
                P.note(P.t, p, vel, 0.6)
                P.items.append(dict(test="C", t=P.t, pitch=p, cc11=cc, vel=vel, dur=0.6))
                P.t += 1.5


def battery_d(P: Plan):
    a = registers(P.name)[2]
    for b in (a + 2, a + 7):
        for vel in (60, 110):
            for g in (-0.05, -0.02, -0.01, 0.0, 0.005, 0.01, 0.015, 0.02, 0.03, 0.04, 0.06, 0.08, 0.12):
                P.cc(P.t - 0.1, 11, 80)
                P.note(P.t, a, vel, 0.5)
                P.note(P.t + 0.5 + g, b, vel, 0.5)
                P.items.append(dict(test="D", t=P.t, a=a, b=b, vel=vel, gap=g, dur=0.5))
                P.t += 2.0 + max(g, 0)


BATTERIES = {"E": battery_e, "A": battery_a, "B": battery_b, "C": battery_c, "D": battery_d}


def make_plan(name: str, init: dict[int, int], tests: str = "E,A,B,C,D") -> Plan:
    P = Plan(name, init)
    for i, k in enumerate(tests.split(",")):
        if i:
            P.t += GAP
        BATTERIES[k](P)
    return P


def map_init(project: str, st: vr.PluginState) -> dict[int, int]:
    """The controllers the expression map on this plug-in's slot sends at the start of playback."""
    from doricohp.playback import PlaybackSetup
    from doricohp.project import Project
    ps = PlaybackSetup(Project(project))
    for (s, _port, _ch), (plugin, map_id) in sorted(ps.slots.items()):
        if s == st.dorico_slot and map_id in ps.maps:
            if plugin != st.name:
                raise ValueError(f"slot {s}: score says {plugin!r}, enginedata says {st.name!r}")
            m = ps.maps[map_id]
            # what Dorico sends when playback starts: the map's init actions, then the switch-on
            # actions of the natural technique (e.g. SWAM strings: CC20=0 = bowed, whatever play
            # mode the saved state has)
            out = {a: b for kind, a, b in m.init_actions if kind == "kControlChange"}
            nat = m.natural
            for kind, a, b in (nat.actions if nat else []):
                if kind == "kControlChange":
                    out[a] = b
                else:
                    print(f"warning: {m.name}: natural action {kind} {a} {b} not sent by the tests", file=sys.stderr)
            return out
    return {}


# ---------------------------------------------------------------- audio

def read_wav(path: Path):
    """(sample rate, mono float64 array) of PCM 16/24/32 or float 32/64 WAV, incl. extensible."""
    import numpy as np
    b = Path(path).read_bytes()
    if b[:4] != b"RIFF" or b[8:12] != b"WAVE":
        raise ValueError(f"{path}: not a WAV file")
    pos, fmt, data = 12, None, None
    while pos + 8 <= len(b):
        cid, n = b[pos:pos + 4], struct.unpack("<I", b[pos + 4:pos + 8])[0]
        body = b[pos + 8:pos + 8 + n]
        if cid == b"fmt ":
            tag, nch, sr = struct.unpack("<HHI", body[:8])
            bits = struct.unpack("<H", body[14:16])[0]
            if tag == 0xFFFE:
                tag = struct.unpack("<H", body[24:26])[0]
            fmt = (tag, nch, sr, bits)
        elif cid == b"data":
            data = body
        pos += 8 + n + (n & 1)
    if not fmt or data is None:
        raise ValueError(f"{path}: no fmt/data chunk")
    tag, nch, sr, bits = fmt
    if tag == 3:
        x = np.frombuffer(data[: len(data) // (bits // 8) * (bits // 8)], dtype="<f4" if bits == 32 else "<f8")
    elif tag == 1 and bits == 16:
        x = np.frombuffer(data[: len(data) // 2 * 2], dtype="<i2") / 32768.0
    elif tag == 1 and bits == 24:
        a = np.frombuffer(data[: len(data) // 3 * 3], dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        v = a[:, 0] | (a[:, 1] << 8) | (a[:, 2] << 16)
        x = np.where(v >= 1 << 23, v - (1 << 24), v) / float(1 << 23)
    elif tag == 1 and bits == 32:
        x = np.frombuffer(data[: len(data) // 4 * 4], dtype="<i4") / 2147483648.0
    else:
        raise ValueError(f"{path}: unsupported WAV format {tag}/{bits} bit")
    x = np.asarray(x, dtype=np.float64)
    x = x[: len(x) // nch * nch].reshape(-1, nch).mean(axis=1)
    return sr, x


class Audio:
    def __init__(self, path: Path):
        import numpy as np
        self.np = np
        self.sr, self.x = read_wav(path)
        n = int(self.sr * WIN)
        m = len(self.x) // n
        rms = np.sqrt(np.mean(self.x[: m * n].reshape(m, n) ** 2, axis=1))
        self.env = 20 * np.log10(np.maximum(rms, 1e-9))

    def span(self, t0, t1):
        a = max(0, int(t0 / WIN))
        return self.env[a:max(int(t1 / WIN), a + 1)]

    def mean_db(self, t0, t1):
        seg = self.span(t0, t1)
        return float(10 * self.np.log10(self.np.mean(10 ** (seg / 10)))) if len(seg) else -180.0

    def onset(self, t, ref, th=-30.0, look=0.4):
        """Seconds from t until the level first rises above ref + th (None if never). A tail
        still ringing from the previous note doesn't count: the threshold is at least 6 dB
        above the level just before t."""
        before = self.span(t - 0.03, t - 0.005)
        floor = float(before.max()) + 6 if len(before) else -180.0
        seg = self.span(t - 0.005, t + look)
        i = self.np.nonzero(seg > max(ref + th, floor))[0]
        return None if not len(i) else i[0] * WIN - 0.005

    def pitch(self, t0, t1):
        """Fundamental (MIDI number, fractional) of a steady stretch, by autocorrelation."""
        np = self.np
        x = self.x[int(t0 * self.sr):int(t1 * self.sr)]
        if len(x) < 256 or np.sqrt(np.mean(x ** 2)) < 1e-5:
            return None
        x = x - x.mean()
        f = np.fft.rfft(x, 2 * len(x))
        ac = np.fft.irfft(f * np.conj(f))[: len(x)]
        ac /= ac[0]
        lo, hi = int(self.sr / 4500), int(self.sr / 25)
        # skip the lobe around lag 0 (low notes stay correlated for many samples): start after
        # the autocorrelation first goes negative
        neg = np.nonzero(ac[lo:hi] < 0)[0]
        if not len(neg):
            return None
        lo = lo + int(neg[0])
        seg = ac[lo:hi]
        if not len(seg):
            return None
        best = seg.max()
        # first peak close to the best: avoids picking an octave below
        cand = np.nonzero(seg > 0.9 * best)[0]
        i = cand[0]
        while i + 1 < len(seg) and seg[i + 1] > seg[i]:
            i += 1
        lag = lo + i
        if 0 < i < len(seg) - 1:  # parabolic refinement
            a, b, c = seg[i - 1], seg[i], seg[i + 1]
            lag += 0.5 * (a - c) / (a - 2 * b + c) if (a - 2 * b + c) else 0
        return 69 + 12 * math.log2(self.sr / lag / 440.0)


# ---------------------------------------------------------------- analysis

def analyse_items(au: Audio, items: list[dict]) -> list[dict]:
    out = []
    for it in items:
        t, r = it["t"], dict(it)
        k = it["test"]
        if k == "E":
            lvl = au.mean_db(t + 0.15, t + 0.4)
            r["level_db"] = round(lvl, 1)
            p = au.pitch(t + 0.15, t + 0.4) if lvl > -70 else None
            r["sounding"] = None if p is None else round(p, 2)
        elif k == "A":
            r["level_db"] = round(au.mean_db(t + 0.6, t + 1.4), 1)
        elif k == "B":
            seg = au.span(t, t + it["dur"] + 0.8)
            pk = float(seg.max())
            r["peak_db"] = round(pk, 1)
            above = au.np.nonzero(seg > pk - 20)[0]
            r["sounds_ms"] = round(float((above[-1] - above[0] + 1) * WIN * 1000)) if len(above) else 0
        elif k == "C":
            steady = au.mean_db(t + 0.35, t + 0.55)
            on, rise = au.onset(t, steady, -30), au.onset(t, steady, -6)
            r["steady_db"] = round(steady, 1)
            r["onset_ms"] = None if on is None else round(on * 1000)
            r["rise_ms"] = None if rise is None else round(rise * 1000)
            r["overshoot_db"] = round(float(au.span(t, t + 0.6).max()) - steady, 1)
        elif k == "D":
            tb = t + it["dur"] + it["gap"]
            steady = au.mean_db(t + 0.25, t + 0.45)
            r["dip_db"] = round(float(au.span(tb - 0.03, tb + 0.08).min()) - steady, 1)
            later = au.mean_db(tb + 0.25, tb + 0.45)
            rise = au.onset(tb, later, -6, 0.2)
            r["b_rise_ms"] = None if rise is None else round(rise * 1000)
            r["b_steady_db"] = round(later, 1)
        out.append(r)
    return out


def alignment(au: Audio, items: list[dict], pre: float = PRE) -> dict:
    """Checks that the WAV starts at the MIDI file's start and runs at the plan's tempo: median
    onset offset of the first test's notes vs the last test's (louder half)."""
    np = au.np
    def offsets(sel):
        vals = []
        for it in sel:
            ref = au.mean_db(it["t"] + 0.25, it["t"] + 0.4)
            if ref > -70:
                on = au.onset(it["t"], ref, -30)
                if on is not None:
                    vals.append(on)
        return float(np.median(vals)) if vals else None
    first_test, last_test = items[0]["test"], items[-1]["test"]
    last_items = [it for it in items if it["test"] == last_test]
    vels = sorted({it.get("vel", 0) for it in last_items})
    first = offsets([it for it in items if it["test"] == first_test and "pitch" in it][:40])
    last = offsets([it for it in last_items if it.get("vel", 0) >= vels[len(vels) // 2]])
    lead = au.mean_db(max(0.0, items[0]["t"] - pre), items[0]["t"] - 0.15) if items[0]["t"] > 0.3 else -120.0
    res = {"onset_first_battery_ms": None if first is None else round(first * 1000),
           "onset_last_battery_ms": None if last is None else round(last * 1000),
           "level_before_first_note_db": round(lead, 1)}
    if first is not None and last is not None and abs(last - first) > 0.25:
        res["warning"] = ("onsets drift between the first and last battery: the WAV doesn't run at the "
                          "plan's tempo (Cubase tempo must be fixed at 120) or doesn't start at bar 1")
    elif first is not None and not (-0.005 <= min(first, last if last is not None else first) <= 0.15):
        # the earlier of the two: slow attacks (e.g. IW oboe, ~150 ms at mf) aren't misalignment
        res["warning"] = "notes start far from their planned times: export must start at bar 1"
    return res


def summary(res: list[dict]) -> str:
    L = []
    dv = lambda r: r.get("dyn", r.get("cc11"))  # dynamics value sent (CC value or velocity)
    E = [r for r in res if r["test"] == "E"]
    if E:
        L.append("E range probe: sent -> sounding (level dB)")
        L.append("  " + "  ".join(f"{r['pitch']}->{'-' if r['sounding'] is None else round(r['sounding'])}({r['level_db']:.0f})"
                                  for r in E))
    A = [r for r in res if r["test"] == "A"]
    if A:
        for ctl in sorted({r.get("dyn_ctl", "CC11") for r in A}):
            AA = [r for r in A if r.get("dyn_ctl", "CC11") == ctl]
            ps = sorted({r["pitch"] for r in AA})
            L.append(f"A level (dBFS) by {ctl} (rows) and pitch (columns)")
            L.append(f"{ctl[:5]:>5}" + " ".join(f"{p:>6d}" for p in ps))
            for v in sorted({dv(r) for r in AA}):
                row = {r["pitch"]: r["level_db"] for r in AA if dv(r) == v}
                L.append(f"{v:5d}" + " ".join(f"{row.get(p, float('nan')):6.1f}" for p in ps))
    B = [r for r in res if r["test"] == "B"]
    for key in sorted({(r["pitch"], dv(r), r["vel"]) for r in B}):
        rs = [r for r in B if (r["pitch"], dv(r), r["vel"]) == key]
        ref = rs[-1]["peak_db"]
        L.append(f"B pitch {key[0]} dyn {key[1]} vel {key[2]} (ms: peak vs 1 s note / sounding ms): " + "  ".join(
            f"{round(r['dur']*1000)}:{r['peak_db']-ref:+.1f}/{r['sounds_ms']}" for r in rs))
    C = [r for r in res if r["test"] == "C"]
    for key in sorted({(r["pitch"], dv(r)) for r in C}):
        rs = [r for r in C if (r["pitch"], dv(r)) == key]
        L.append(f"C pitch {key[0]} dyn {key[1]} (vel: onset/rise ms, overshoot dB): " + "  ".join(
            f"v{r['vel']}:{r['onset_ms']}/{r['rise_ms']}{r['overshoot_db']:+.0f}" for r in rs))
    D = [r for r in res if r["test"] == "D"]
    for key in sorted({(r["a"], r["b"], r["vel"]) for r in D}):
        rs = [r for r in D if (r["a"], r["b"], r["vel"]) == key]
        L.append(f"D {key[0]}->{key[1]} vel {key[2]} (gap ms: dip dB / 2nd-note rise ms): " + "  ".join(
            f"{round(r['gap']*1000)}:{r['dip_db']:+.0f}/{r['b_rise_ms']}" for r in rs))
    return "\n".join(L)


# ---------------------------------------------------------------- commands

README = """SWAM test renders (dorico-hp, Project C)                         {date}

What this is: test notes for each SWAM woodwind, played with your own SWAM settings from
"HP WW.dorico". Rendering them in Cubase lets me measure how SWAM responds (loudness per
dynamic and register, short notes, attacks, legato), to tune the Dorico expression maps.
Only the flute is needed to start; the others can follow any time (same steps).

Files
  midi\\NN-<instrument>.mid      the test notes (tempo 120, starts at bar 1, about {mins} min each)
  presets\\<instrument>.swam     your SWAM settings from HP WW (load with SWAM's Load button)
  renders\\                      put the exported WAVs here

Steps (Cubase 13)
 1. New empty project. Project > Project Setup: sample rate 48 kHz.
 2. Transport bar: switch the tempo to Fixed (not Tempo Track) and set 120 bpm, 4/4.
 3. For each instrument you render: Project > Add Track > Instrument, choose the SWAM
    plug-in (e.g. "SWAM Flute 64bit"). In the SWAM window press Load and open
    presets\\<instrument>.swam from this folder. Then close the window; don't change anything.
 4. Drag midi\\NN-<instrument>.mid from Explorer onto that track, exactly at bar 1
    (the part must start at bar 1; the first events are controllers at the very start).
 5. Locators: left locator at bar 1; right locator at least 2 bars after the end of the
    longest part.
 6. No inserts or effects on the instrument channels or the Stereo Out; faders at 0 dB.
 7. File > Export > Audio Mixdown:
      - Channel Batch Export: tick the SWAM instrument channels
      - Path: this folder's renders\\ ; naming: channel name is fine
      - Wave, 48 kHz, 32 bit float; Real-Time Export OFF
    Export.
 8. Tell me the files are there. Nothing else is needed.

Instruments
{table}
"""


def cmd_kit(a):
    out = Path(a.out)
    (out / "midi").mkdir(parents=True, exist_ok=True)
    (out / "presets").mkdir(exist_ok=True)
    (out / "renders").mkdir(exist_ok=True)
    rows, mins = [], 0.0
    names = a.instruments.split(",") if a.instruments else [n for n, v in INSTRUMENTS.items() if v[0] == WW]
    for i, name in enumerate(names, 1):
        proj, st = source(name, a.project)
        slot = st.slot
        init = map_init(proj, st)
        P = make_plan(name, init)
        mid = out / "midi" / f"{i:02d}-{name}.mid"
        P.to_midi(mid)
        (out / "presets" / f"{name}.swam").write_text('<?xml version="1.0" encoding="UTF-8"?>\n\n' + st.xml + "\n",
                                                       encoding="utf-8")
        RESULTS.mkdir(parents=True, exist_ok=True)
        (RESULTS / f"{name}.plan.json").write_text(json.dumps(
            {"project": Path(proj).name, "slot": slot, "plugin": st.name, "init": init,
             "program": re.search(r'<program value="([^"]+)"', st.xml).group(1),
             "tempo_bpm": 60_000_000 / TEMPO_US, "end_s": round(P.end(), 3), "items": P.items}, indent=1))
        mins = max(mins, P.end() / 60)
        rows.append(f"  {i:02d}  {name:14s} plug-in '{st.name}'  init CCs {init}  {P.end()/60:.1f} min")
        print(rows[-1])
    import datetime
    (out / "README.txt").write_text(README.format(date=datetime.date.today(), mins=round(mins, 1),
                                                  table="\n".join(rows)).replace("\n", "\r\n"), encoding="utf-8")
    print(f"kit -> {out}")


def cmd_analyse(a):
    plan = json.loads((RESULTS / f"{a.name}.plan.json").read_text())
    au = Audio(Path(a.wav))
    res = analyse_items(au, plan["items"])
    al = alignment(au, plan["items"])
    tag = f"-{a.tag}" if a.tag else ""
    (RESULTS / f"{a.name}{tag}.json").write_text(json.dumps(
        {"wav": str(a.wav), "plan": f"{a.name}.plan.json", "alignment": al, "results": res}, indent=1))
    print(f"## {a.name}{tag}: {Path(a.wav).name}\nalignment {al}\n{summary(res)}")


def cmd_render(a):
    for name in a.name.split(","):
        proj, st = source(name, a.project)
        P = make_plan(name, map_init(proj, st), a.tests)
        RESULTS.mkdir(parents=True, exist_ok=True)
        (RESULTS / f"{name}.plan.json").write_text(json.dumps(
            {"project": Path(proj).name, "slot": st.slot, "plugin": st.name, "init": P.init, "renderer": "vi-render",
             "tempo_bpm": 60_000_000 / TEMPO_US, "end_s": round(P.end(), 3), "items": P.items}, indent=1))
        wav = Path(a.wav_dir) / f"{name}.wav"
        print(vr.render(st.name, P.to_events(), wav, state=st))
        cmd_analyse(argparse.Namespace(wav=wav, name=name, tag=""))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    k = sub.add_parser("kit", help="write MIDI + presets + README for rendering in Cubase")
    k.add_argument("--project", help="source project (default: each instrument's own, see INSTRUMENTS)")
    k.add_argument("--out", required=True)
    k.add_argument("--instruments", default="", help=f"comma list (default all): {','.join(INSTRUMENTS)}")
    n = sub.add_parser("analyse", help="measure a rendered WAV")
    n.add_argument("wav")
    n.add_argument("--name", required=True, choices=list(INSTRUMENTS))
    n.add_argument("--tag", default="")
    r = sub.add_parser("render", help="render with vi-render and analyse")
    r.add_argument("--project", help="source project (default: the instrument's own)")
    r.add_argument("--name", required=True, help="instrument key(s), comma-separated")
    r.add_argument("--tests", default="E,A,B,C,D")
    r.add_argument("--wav-dir", default=str(ROOT / "target/swam-renders"))
    a = ap.parse_args()
    {"kit": cmd_kit, "analyse": cmd_analyse, "render": cmd_render}[a.cmd](a)


if __name__ == "__main__":
    main()
