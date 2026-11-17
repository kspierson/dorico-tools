"""The performance rules: from a Score (doricohp.model) to a Performance.

A Performance holds, per part:
- `marked`: the dynamic level the notation asks for over time (immediate dynamics and
  written hairpins), in steps (mf = 0),
- `shaped`: marked + this engine's shaping (section balance, soften basses, automatic
  espressivo on long notes, phrase rules). `shaped - marked` is what Apply adds on top of
  Dorico's own dynamics,
- per-note attack velocity, velocity offset (for velocity-dynamics instruments) and
  onset/offset shifts in ms (rhythmic feel, per-library attack latency),
- controller curves for vibrato (only for libraries with a vibrato controller).

Rules and their sources:
- metric accents, rhythmic feel ......... HP captures, research/hp-engine.md (style tables)
- hairpins (S-curve) ..................... HP captures (06-hairpins)
- automatic espressivo ................... "The Last Temptation" HP MIDI (arch on notes > 1.1 crotchets, depth ~ mood)
- phrase rules (rise-swell, arrival, release) ... the user's playback copies (score-vs-playback.md)
- vibrato bloom ........................... per-library profile (new; HP only had Garritan auto vibrato)
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field
from fractions import Fraction

from .model import STEP, Note, Part, Score

F = Fraction


@dataclass
class NotePerf:
    note: Note
    velocity: int                 # attack velocity (instruments whose dynamics are on a controller)
    vel_delta: float              # accent offset only (for instruments whose dynamics are velocity)
    start_ms: float = 0.0         # + = later
    end_ms: float = 0.0


@dataclass
class PartPerf:
    part: Part
    settings: dict
    notes: list[NotePerf] = field(default_factory=list)
    marked: list[tuple[Fraction, float]] = field(default_factory=list)
    shaped: list[tuple[Fraction, float]] = field(default_factory=list)
    ccs: dict[int, list[tuple[Fraction, float]]] = field(default_factory=dict)
    notes_for_log: list[str] = field(default_factory=list)

    def offset_curve(self) -> list[tuple[Fraction, float]]:
        return [(p, s - level_at(self.marked, p)) for p, s in self.shaped]


# ---------------------------------------------------------------------------
# curves
# ---------------------------------------------------------------------------

def level_at(curve: list[tuple[Fraction, float]], pos: Fraction) -> float:
    if not curve:
        return 0.0
    i = bisect_right([p for p, _ in curve], pos) - 1
    if i < 0:
        return curve[0][1]
    if i + 1 < len(curve):
        (p0, v0), (p1, v1) = curve[i], curve[i + 1]
        if p1 > p0:
            return v0 + (v1 - v0) * float((pos - p0) / (p1 - p0))
    return curve[i][1]


def s_blend(x: float, amount: float) -> float:
    """0..1 → 0..1; amount 0 = linear, 1 = smoothstep."""
    x = min(1.0, max(0.0, x))
    return (1 - amount) * x + amount * (x * x * (3 - 2 * x))


def simplify(points: list[tuple[Fraction, float]], tol: float = 0.02) -> list[tuple[Fraction, float]]:
    """Drop points that lie on the line between their neighbours (within tol)."""
    if len(points) <= 2:
        return points
    out = [points[0]]
    for i in range(1, len(points) - 1):
        (p0, v0), (p1, v1), (p2, v2) = out[-1], points[i], points[i + 1]
        if p1 == p0 or p1 == p2:          # keep both sides of an instant jump
            out.append(points[i])
            continue
        if p2 == p0:
            continue
        expect = v0 + (v2 - v0) * float((p1 - p0) / (p2 - p0))
        if abs(expect - v1) > tol:
            out.append(points[i])
    out.append(points[-1])
    return out


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def lead_line(part: Part) -> list[Note]:
    """Highest non-grace note at each onset (the line the shaping follows)."""
    by: dict[Fraction, Note] = {}
    for n in part.notes:
        if n.grace:
            continue
        if n.pos not in by or n.pitch > by[n.pos].pitch:
            by[n.pos] = n
    return [by[p] for p in sorted(by)]


def under_hairpin(part: Part, a: Fraction, b: Fraction) -> bool:
    return any(h0 < b and h1 > a for h0, h1, _ in part.hairpins)


def beat_class(score: Score, pos: Fraction) -> str:
    bar, off, blen = score.beat_info(pos)
    if off == 0:
        return "downbeat"
    compound = blen.denominator == 2 and blen > 1 and (blen * 2) % 3 == 0     # 6/8, 9/8, 12/8
    beat = F(3, 2) if compound else F(1)
    if off % beat == 0:
        if not compound and blen == 4 and off == 2:
            return "beat3"
        if compound and blen == 6 and off == 3:
            return "beat3"
        return "beat"
    if off % F(1, 2) == 0:
        return "offbeat"
    return "weak"


# ---------------------------------------------------------------------------
# dynamics
# ---------------------------------------------------------------------------

def marked_curve(score: Score, part: Part, s: dict) -> list[tuple[Fraction, float]]:
    d = s["dynamics"]
    imm = [(p, float(STEP[k])) for p, k in part.dynamics if k in STEP]
    imm += [(p, float(STEP["p"])) for p, k in part.dynamics if k in ("fp", "sfp", "sfzp")]
    imm.sort()
    start = imm[0][1] if imm else d["unmarked_level"]
    end_pos = max([n.end for n in part.notes] + [score.bar_starts[-1] + score.bar_length(len(score.bar_starts) - 1)])
    pts: list[tuple[Fraction, float]] = [(F(0), start)]
    events = sorted([(p, "imm", v) for p, v in imm] + [(h0, "hp", (h1, dr)) for h0, h1, dr in part.hairpins],
                    key=lambda e: (e[0], e[1] != "imm"))
    cur = start
    for pos, kind, val in events:
        if kind == "imm":
            pts.append((pos, cur))
            pts.append((pos, val))
            cur = val
        else:
            h1, dr = val
            nxt = [v for p, v in imm if h1 - F(1) <= p <= h1 + F(1, 2)]
            target = nxt[0] if nxt else cur + (d["hairpin_default_steps"] if dr == "cresc" else -d["hairpin_default_steps"])
            if (dr == "cresc" and target <= cur) or (dr == "dim" and target >= cur):
                target = cur + (1 if dr == "cresc" else -1) * d["hairpin_default_steps"]
            steps = 12
            pts.append((pos, cur))
            for i in range(1, steps + 1):
                x = i / steps
                pts.append((pos + (h1 - pos) * F(i, steps), cur + (target - cur) * s_blend(x, d["hairpin_s_curve"])))
            cur = target
    pts.append((end_pos, cur))
    # make positions strictly ordered (instant jumps become two points at the same pos)
    pts.sort(key=lambda x: x[0])
    return pts


def open_hairpin_returns(score: Score, part: Part, d: dict, contributions: list) -> int:
    """Hairpins with no dynamic at their end, read as local swells ([dynamics] open_hairpin).

    `marked_curve` reads them literally (the level moves `hairpin_default_steps` and stays).
    For each one this adds a contribution that brings the level back to where it was before
    the hairpin: from the hairpin's end (the note it leads to keeps the peak) down to the
    start of the next phrase (first note after a rest or starting a slur, at most
    `open_hairpin_return_bars` bars later), held until the next immediate dynamic resets
    the marked level anyway. Returns how many hairpins it changed."""
    if d.get("open_hairpin", "stay") != "swell":
        return 0
    imm = sorted(p for p, k in part.dynamics if k in STEP or k in ("fp", "sfp", "sfzp"))
    onsets = sorted({n.pos for n in part.notes if not n.grace})
    ends: dict[Fraction, Fraction] = {}
    for n in part.notes:
        if not n.grace:
            ends[n.pos] = max(ends.get(n.pos, n.pos), n.end)
    slur_starts = {s0 for s0, _ in part.slurs}
    end_pos = max([n.end for n in part.notes], default=F(0))
    eps = F(1, 1920)
    count = 0
    for h0, h1, dr in part.hairpins:
        if any(h1 - F(1) <= p <= h1 + F(1, 2) for p in imm):
            continue  # has a target dynamic: marked_curve already goes there
        rise = d["hairpin_default_steps"] * (1 if dr == "cresc" else -1)
        bar = score.bar_of(h1)
        limit = h1 + score.bar_length(bar) * F(str(d.get("open_hairpin_return_bars", 1.0)))
        nxt_imm = next((p for p in imm if p > h1), end_pos)
        r = limit
        prev_end = None
        for o in onsets:
            if o > h1 and prev_end is not None and (o > prev_end or o in slur_starts):
                r = min(r, o)
                break
            if o >= h1:
                prev_end = max(prev_end or o, ends[o])
        r = min(r, nxt_imm)
        if r <= h1:
            continue
        pts = [(h1, 0.0), (r, -rise)]
        if nxt_imm > r:
            pts += [(nxt_imm - eps, -rise)]
        pts += [(nxt_imm, 0.0)]
        contributions.append(pts)
        count += 1
    return count


def shaping(score: Score, part: Part, s: dict, marked) -> tuple[list[tuple[Fraction, float]], list[str]]:
    """Offsets in steps (piecewise linear, as breakpoints) added to the marked curve."""
    log = []
    contributions: list[list[tuple[Fraction, float]]] = []
    bal = s["balance"]
    const = float(bal.get(part.family, 0.0))
    pitches = sorted(n.pitch for n in part.notes)
    if pitches and s["style"].get("softenBasses") and pitches[len(pitches) // 2] < bal["soften_below_pitch"]:
        const -= bal["soften_steps"]
    if const:
        log.append(f"balance {const:+.2f} steps")
    line = lead_line(part)
    mood = s["style"].get("mood", 0) or 0
    esp = s["espressivo"]
    if esp["enabled"] and mood:
        depth = esp["depth_at_mood_76"] * mood / 76
        n_esp = 0
        for n in line:
            if n.dur <= F(esp["min_crotchets"]).limit_denominator(64) or under_hairpin(part, n.pos, n.end):
                continue
            base = level_at(marked, n.pos)
            room = 1.0 if base <= esp["headroom_level"] else max(0.0, 1 - (base - esp["headroom_level"]))
            if room <= 0:
                continue
            peak = n.pos + n.dur * F(esp["peak_at"]).limit_denominator(100)
            contributions.append([(n.pos, 0.0), (n.pos + n.dur * F(1, 10), depth * room * 0.1), (peak, depth * room),
                                  (n.end - n.dur * F(1, 20), -esp["end_drop"] * room), (n.end, 0.0)])
            n_esp += 1
        log.append(f"espressivo depth {depth:.2f} steps on {n_esp} notes")
    ph = s["phrase"]
    if ph["enabled"] and mood:
        k = min(1.5, mood / 40)          # phrase shaping grows with mood (Standard 5 → small)
        n_rise = n_arr = n_rel = 0
        # rise-swell over slurred rising groups
        for s0, s1 in part.slurs:
            grp = [n for n in line if s0 <= n.pos <= s1]
            if len(grp) < 3 or under_hairpin(part, s0, s1):
                continue
            rise = (grp[-1].pitch - grp[0].pitch) / 12
            top = max(g.pitch for g in grp)
            if rise <= 0 and top - grp[0].pitch < 3:
                continue
            amt = ph["rise_swell_steps"] * k * max(rise, (top - grp[0].pitch) / 12)
            peak_note = max(grp, key=lambda g: (g.pitch, -g.pos))
            contributions.append([(s0, 0.0), (peak_note.pos, amt), (s1, amt * 0.3), (s1 + F(1, 2), 0.0)])
            n_rise += 1
        # arrival crescendos: onto a longer and not lower note on a beat
        for i in range(1, len(line)):
            n, prev = line[i], line[i - 1]
            if beat_class(score, n.pos) not in ("downbeat", "beat3") or n.dur < F(1):
                continue
            if n.dur < prev.dur * 2 or n.pitch < prev.pitch - 2 or under_hairpin(part, n.pos - F(ph["arrival_crotchets"]).limit_denominator(16), n.pos):
                continue
            a0 = max(F(0), n.pos - F(ph["arrival_crotchets"]).limit_denominator(16))
            amt = ph["arrival_steps"] * k
            contributions.append([(a0, 0.0), (n.pos, amt), (n.pos + n.dur / 2, amt * 0.4), (n.end, 0.0)])
            n_arr += 1
        # phrase-end release
        for i, n in enumerate(line):
            nxt = line[i + 1] if i + 1 < len(line) else None
            ends = nxt is None or nxt.pos > n.end or n.slur == "end"
            if not ends or n.dur < F(ph["release_min_crotchets"]).limit_denominator(16) or under_hairpin(part, n.pos, n.end):
                continue
            amt = -ph["release_steps"] * k
            contributions.append([(n.pos + n.dur / 3, 0.0), (n.end, amt), (n.end + F(1, 8), 0.0)])
            n_rel += 1
        log.append(f"phrase: {n_rise} rise-swells, {n_arr} arrivals, {n_rel} releases (strength {k:.2f})")
    n_open = open_hairpin_returns(score, part, s["dynamics"], contributions)
    if n_open:
        log.append(f"{n_open} open hairpins read as local swells")
    # sum the contributions on a common set of breakpoints
    xs = sorted({p for c in contributions for p, _ in c} | {p for p, _ in marked})
    out = []
    for x in xs:
        v = const
        for c in contributions:
            if c[0][0] <= x <= c[-1][0]:
                v += level_at(c, x)
        out.append((x, v))
    return out or [(F(0), const)], log


# ---------------------------------------------------------------------------
# notes: velocity and timing
# ---------------------------------------------------------------------------

def note_perf(score: Score, part: Part, s: dict, shaped) -> list[NotePerf]:
    st = s["style"]
    acc = st.get("rhythmicAccents", 0) or 0
    feel = st.get("rhythmicFeel", 0) or 0
    syncop = bool(st.get("emphasizeShortSyncops")) and s["accents"]["syncopation_invert"]
    a, att, tm, lat = s["accents"], s["attack"], s["timing"], s["latency"]
    out = []
    for n in part.notes:
        bc = beat_class(score, n.pos)
        if syncop:
            delta = {"downbeat": -0.07, "beat3": -0.07, "beat": 0.0, "offbeat": 0.03, "weak": 0.015}[bc] * acc
        else:
            delta = {"downbeat": a["per_unit_beat1"], "beat3": a["per_unit_beat3"], "beat": 0.0,
                     "offbeat": a["per_unit_offbeat"], "weak": a["per_unit_offbeat"] / 2}[bc] * acc
        lv = level_at(shaped, n.pos)
        vel = att["base"] + att["per_step"] * lv + delta
        state = part.passage.at(n.pos) if part.passage else set()
        if "light" in state:
            vel += att.get("light_offset", 0)
        if "marcato" in state:
            vel += att.get("marcato_offset", 0)
        vel = int(round(min(att["max"], max(att["min"], vel))))
        # rhythmic feel: later onsets after the downbeat, shrinking towards the barline
        _, off, blen = score.beat_info(n.pos)
        x = float(off / blen) if blen else 0.0
        shape = tm["downbeat_ms_per_unit"] / tm["ms_per_unit"] if off == 0 else min(1.0, 1.15 * (1 - x))
        delay = feel * tm["ms_per_unit"] * shape
        # fast notes: HP's lean after the downbeat becomes a hitch in runs, so scale it
        # down for notes shorter than the reference length (beyond HP)
        ref = F(str(tm.get("short_note_ref", 0.5)))
        if n.dur < ref:
            delay *= float(n.dur / ref)
        if n.grace:
            delay = 0.0
        early = lat["attack_ms"] + (lat["legato_ms"] if n.slur in ("in", "end") else 0)
        start = delay - early
        out.append(NotePerf(n, vel, delta, start, start))
    return out


# ---------------------------------------------------------------------------
# vibrato
# ---------------------------------------------------------------------------

def vibrato(score: Score, part: Part, s: dict, shaped) -> dict[int, list[tuple[Fraction, float]]]:
    v = s["vibrato"]
    if not v["enabled"] or not v["depth_cc"]:
        return {}
    mood = s["style"].get("mood", 0) or 0
    esp_k = min(1.5, mood / 76) if s["espressivo"]["enabled"] else 0.0
    line = lead_line(part)
    depth: list[tuple[Fraction, float]] = []
    rate: list[tuple[Fraction, float]] = []

    def at_ms(pos: Fraction, ms: float) -> Fraction:
        return pos + F(ms / score.ms_per_crotchet(pos)).limit_denominator(960)

    prev_end, prev_val = None, 0.0
    for i, n in enumerate(line):
        nxt = line[i + 1] if i + 1 < len(line) else None
        dur_ms = float(n.dur) * score.ms_per_crotchet(n.pos)
        lv = level_at(shaped, n.pos)
        target = min(v["max_depth"], max(v["min_depth"], v["base_depth"] + v["per_step"] * lv))
        legato = prev_end is not None and n.pos <= prev_end and n.slur in ("in", "end")
        if dur_ms < v["short_note_ms"]:
            val = v["short_note_depth"] if not legato else max(v["short_note_depth"], prev_val)
            depth += [(n.pos, val)]
            prev_end, prev_val = n.end, val
            continue
        start_val = prev_val if legato else min(target, v["short_note_depth"])
        on = at_ms(n.pos, 0 if legato else v["onset_ms"])
        full = at_ms(on, v["bloom_ms"])
        pts = [(n.pos, start_val), (min(on, n.end), start_val), (min(full, n.end), target)]
        if n.dur > F(s["espressivo"]["min_crotchets"]).limit_denominator(64) and esp_k:
            peak = n.pos + n.dur * F(s["espressivo"]["peak_at"]).limit_denominator(100)
            if peak > full:
                pts.append((peak, min(v["max_depth"], target + v["espressivo_extra"] * esp_k)))
        ends_phrase = nxt is None or nxt.pos > n.end or n.slur == "end"
        if ends_phrase:
            rel = at_ms(n.end, -v["release_ms"])
            if rel > pts[-1][0]:
                pts.append((rel, pts[-1][1]))
            pts.append((n.end, target * 0.5))
        else:
            pts.append((n.end, target))
        depth += pts
        if v["rate_cc"] and v["rate_base"]:
            peak_rate = v["rate_peak"] or v["rate_base"]
            rate += [(n.pos, v["rate_base"]), (pts[-2][0] if len(pts) > 2 else n.end, peak_rate)]
        prev_end, prev_val = n.end, pts[-1][1]
    out = {v["depth_cc"]: simplify(sorted(depth, key=lambda p: p[0]), 0.5)}
    if rate:
        out[v["rate_cc"]] = simplify(sorted(rate, key=lambda p: p[0]), 0.5)
    return out


# ---------------------------------------------------------------------------

def perform(score: Score, profiles, part_info: dict[str, tuple[str, str, str]] | None = None) -> list[PartPerf]:
    """part_info: Dorico instrument id (or part key) → (expression map name, plug-in name, entity)."""
    out = []
    for part in score.parts:
        pi = part_info or {}
        info = pi.get(part.instrument_id) or pi.get(part.key) or ("", "", part.entity)
        s = profiles.for_part(part.name, *info)
        pp = PartPerf(part, s)
        pp.marked = simplify(marked_curve(score, part, s), 0.001)
        offsets, log = shaping(score, part, s, pp.marked)
        # keep the marked curve's instant jumps (two points at one position)
        mpos = {p for p, _ in pp.marked}
        pts = [(p, v + level_at(offsets, p)) for p, v in pp.marked]
        pts += [(p, level_at(pp.marked, p) + v) for p, v in offsets if p not in mpos]
        pts.sort(key=lambda x: x[0])
        pp.shaped = simplify(pts, 0.01)
        pp.notes = note_perf(score, part, s, pp.shaped)
        pp.ccs = vibrato(score, part, s, pp.shaped)
        pp.notes_for_log = [f"library {s['library']}"] + log
        out.append(pp)
    return out
