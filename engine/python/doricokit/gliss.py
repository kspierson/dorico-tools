"""Harp glissando playback, ad lib glissandi first (PLANNED_WORK.md §4.9).

An ad lib glissando is a list of **sweeps**: runs over consecutive harp strings from one
turning point to the next. Sweeps may overlap (a new one starts before the last one ends),
so they carry a `layer` (a hand / output track). Times are seconds; callers convert score
positions with `doricokit.timeline` (Dorico) or `doricokit.midi` (MIDI files).

    from doricokit import gliss, harp
    g = gliss.plan(start=16.34, end=19.40, pedals=harp.Pedals.parse("Db C B | E F# G# A"),
                   low=56, high=84, first=84, last=56)          # new ad lib gliss from a sketch
    g.notes()                                                   # -> [GlissNote], pedal-aware
    r = gliss.fit(notes)                                        # spec from a crafted MIDI region
    gliss.compare(original, r.gliss.notes())                    # how well the spec reproduces it

Model (from the user's crafted reference, trex-harp.mid): even steps inside a sweep, the last
step into a turn `hang` times longer, sweep lengths free of the beat, every string of the pedal
setting played (enharmonic doubles included). `plan` follows what a harpist physically does
(user, 2026-11-01): the turning string sounds once, a wave stays in one hand, overlapping
sweeps use the other hand; `physical_checks` flags anything else (the crafted reference
re-plucks its turns, which `fit` reports).

CLI: `python -m doricokit.gliss fit FILE --start BAR[+CROTCHETS] --end BAR[+CROTCHETS]
[--pedals "Db C B | E F# G# A"] [--json OUT] [--write OUT.mid] [--replan OUT.mid --seed N]`.
"""
from __future__ import annotations

import argparse
import bisect
import json
import random
import statistics
import sys
from dataclasses import asdict, dataclass, field

from .harp import Pedals, strings

__all__ = ["Sweep", "GlissNote", "AdLibGliss", "FitResult", "fit", "compare", "plan", "string_near",
           "physical_checks"]

HARP_LOW_PITCH = 23    # C♭1; anything lower in a harp track is a keyswitch, not a string


@dataclass
class Sweep:
    start: float          # onset of the first note (s)
    end: float            # onset of the last note, the turning or target string (s)
    from_string: int      # harp.String.index
    to_string: int
    velocity: int = 100
    hang: float = 1.0     # last step / the other steps
    layer: int = 0
    skip: list[int] = field(default_factory=list)   # strings passed over (crafted sweeps only)

    @property
    def direction(self) -> int:
        return (self.to_string > self.from_string) - (self.to_string < self.from_string)

    def string_indices(self) -> list[int]:
        d = self.direction or 1
        return [i for i in range(self.from_string, self.to_string + d, d) if i not in self.skip]


@dataclass
class GlissNote:
    time: float
    pitch: int
    velocity: int
    length: float
    string: int
    layer: int = 0


@dataclass
class AdLibGliss:
    pedals: Pedals
    sweeps: list[Sweep]
    release: float = 0.25                 # length of the very last note (s)
    dynamics: list[tuple[float, int]] = field(default_factory=list)  # (time, velocity) breakpoints

    def velocity_at(self, t: float, default: int) -> int:
        if not self.dynamics:
            return default
        pts = sorted(self.dynamics)
        if t <= pts[0][0]:
            return pts[0][1]
        for (t0, v0), (t1, v1) in zip(pts, pts[1:]):
            if t <= t1:
                return round(v0 + (v1 - v0) * (t - t0) / ((t1 - t0) or 1))
        return pts[-1][1]

    def notes(self) -> list[GlissNote]:
        strs = strings(self.pedals)
        last_end = max((s.end for s in self.sweeps), default=0.0)
        out: list[GlissNote] = []
        for s in self.sweeps:
            idx = s.string_indices()
            n = len(idx)
            if n == 1:
                times, step = [s.start], self.release
            else:
                step = (s.end - s.start) / ((n - 2) + s.hang)
                times = [s.start + i * step for i in range(n - 1)] + [s.end]
            for i, (si, t) in enumerate(zip(idx, times)):
                if i + 1 < n:
                    length = times[i + 1] - t
                else:
                    length = self.release if s.end >= last_end else step * s.hang
                vel = self.velocity_at(t, s.velocity)
                out.append(GlissNote(t, strs[si].pitch, vel, length, si, s.layer))
        out.sort(key=lambda g: (g.time, g.pitch))
        return out

    def to_dict(self) -> dict:
        return {"pedals": str(self.pedals), "release": self.release,
                "dynamics": [list(p) for p in self.dynamics],
                "sweeps": [asdict(s) for s in self.sweeps]}

    @classmethod
    def from_dict(cls, d: dict) -> "AdLibGliss":
        return cls(Pedals.parse(d["pedals"]), [Sweep(**s) for s in d["sweeps"]],
                   d.get("release", 0.25), [tuple(p) for p in d.get("dynamics", [])])


def string_near(pedals: Pedals, pitch: int, prefer: int = 0) -> int:
    """Index of the string sounding `pitch`, or the nearest one. With two strings on the pitch,
    prefer < 0 takes the lower, > 0 the higher."""
    strs = strings(pedals)
    exact = [s.index for s in strs if s.pitch == pitch]
    if exact:
        return exact[-1] if prefer > 0 else exact[0]
    return min(strs, key=lambda s: (abs(s.pitch - pitch), s.index)).index


# --- fitting a spec to played notes ------------------------------------------------------------


@dataclass
class FitResult:
    gliss: AdLibGliss
    sweeps: list[dict]          # per sweep: notes, seconds, notes/s, step, skipped and off-set notes
    notes: list[GlissNote]      # the input, as GlissNotes with the strings assigned
    warnings: list[str]


def _best_pedals(notes: list[tuple[float, int, int, int]], doubles: set[int]) -> Pedals:
    """The pedal setting that sounds the most input notes; ties: every set pitch class heard,
    observed enharmonic doubles present, fewest sharps/flats."""
    import itertools
    count: dict[int, int] = {}
    for _, p, _, _ in notes:
        count[p % 12] = count.get(p % 12, 0) + 1
    nat = [0, 2, 4, 5, 7, 9, 11]
    best, best_key = Pedals(), None
    for alter in itertools.product((-1, 0, 1), repeat=7):
        pcs = [(n + a) % 12 for n, a in zip(nat, alter)]
        cover = sum(count.get(pc, 0) for pc in set(pcs))
        unheard = sum(1 for pc in set(pcs) if pc not in count)
        dbl_ok = sum(1 for pc in doubles if pcs.count(pc) >= 2)
        key = (cover, -unheard, dbl_ok, -sum(a != 0 for a in alter))
        if best_key is None or key > best_key:
            best, best_key = Pedals(alter), key  # type: ignore[arg-type]
    return best


def _segment(layer_notes: list[tuple[float, int, int, int]], max_gap: float,
             doubled: set[int] | None) -> list[list[tuple[float, int, int, int]]]:
    """Split one layer into runs: a new run after a gap, a change of direction, or a repeated
    pitch that isn't an enharmonic double (`doubled`: pitches two strings sound; None = any)."""
    runs: list[list[tuple[float, int, int, int]]] = []
    cur: list[tuple[float, int, int, int]] = []
    direction = 0
    for n in layer_notes:
        if not cur:
            cur, direction = [n], 0
            continue
        prev = cur[-1]
        dp = n[1] - prev[1]
        sign = (dp > 0) - (dp < 0)
        repeat = sign == 0 and doubled is not None and n[1] not in doubled
        if n[0] - prev[0] > max_gap or (direction and sign and sign != direction) or repeat:
            runs.append(cur)
            cur, direction = [n], 0
            continue
        if direction == 0:
            direction = sign
        cur.append(n)
    if cur:
        runs.append(cur)
    return runs


def fit(notes, pedals: Pedals | None = None, max_gap: float = 0.12) -> FitResult:
    """Fit sweeps to played notes: (time s, pitch, velocity, layer) tuples, e.g. one MIDI track
    per layer. Notes below the harp's range (keyswitches) are ignored."""
    notes = sorted((n for n in notes if n[1] >= HARP_LOW_PITCH), key=lambda n: (n[3], n[0], n[1]))
    warnings: list[str] = []
    layers = sorted({n[3] for n in notes})
    if pedals is None:
        rough = [r for layer in layers for r in _segment([n for n in notes if n[3] == layer], max_gap, None)]
        doubles = {r[i][1] % 12 for r in rough for i in range(1, len(r)) if r[i][1] == r[i - 1][1]}
        pedals = _best_pedals(notes, doubles)
    strs = strings(pedals)
    by_pitch: dict[int, list[int]] = {}
    for s in strs:
        by_pitch.setdefault(s.pitch, []).append(s.index)
    doubled = {p for p, idx in by_pitch.items() if len(idx) > 1}
    runs = [r for layer in layers for r in _segment([n for n in notes if n[3] == layer], max_gap, doubled)]

    sweeps: list[Sweep] = []
    info: list[dict] = []
    assigned: list[GlissNote] = []
    for run in sorted(runs, key=lambda r: r[0][0]):
        d = (run[-1][1] > run[0][1]) - (run[-1][1] < run[0][1])
        idx: list[int] = []
        off: list[int] = []
        for t, p, v, layer in run:
            cands = by_pitch.get(p, [])
            if idx:
                cands = [c for c in cands if (c - idx[-1]) * (d or 1) > 0]
            if cands:
                si = min(cands) if d >= 0 else max(cands)
            else:
                off.append(p)
                pool = [s for s in strs if not idx or (s.index - idx[-1]) * (d or 1) > 0] or strs
                si = min(pool, key=lambda s: (abs(s.pitch - p), abs(s.index - (idx[-1] if idx else s.index)))).index
            idx.append(si)
            assigned.append(GlissNote(t, p, v, 0.0, si, layer))
        times = [n[0] for n in run]
        steps = [b - a for a, b in zip(times, times[1:])]
        if len(steps) >= 2:
            base = statistics.median(steps[:-1])
            hang = steps[-1] / base if base > 0 else 1.0
        else:
            base, hang = (steps[0] if steps else 0.0), 1.0
        step_dir = d or 1
        skip = [i for a, b in zip(idx, idx[1:]) for i in range(a + step_dir, b, step_dir)]
        skipped = [strs[i].name for i in skip]
        sweeps.append(Sweep(run[0][0], run[-1][0], idx[0], idx[-1],
                            round(statistics.median(n[2] for n in run)), round(hang, 3), run[0][3], skip))
        dur = run[-1][0] - run[0][0]
        info.append({"layer": run[0][3], "dir": {1: "up", -1: "down", 0: "-"}[d],
                     "from": strs[idx[0]].name, "to": strs[idx[-1]].name, "notes": len(run),
                     "start": run[0][0], "end": run[-1][0], "seconds": dur,
                     "per_second": (len(run) - 1) / dur if dur > 0 else 0.0,
                     "step_ms": base * 1000, "hang": hang, "skipped": skipped,
                     "off_set": off})
        if off:
            warnings.append(f"{run[0][0]:.3f}s: {len(off)} note(s) outside {pedals}: {off}")
        if skipped:
            warnings.append(f"{run[0][0]:.3f}s: skipped string(s) {', '.join(skipped)}")
    g = AdLibGliss(pedals, sweeps)
    warnings += physical_checks(g, hands=False)
    return FitResult(g, info, assigned, warnings)


def compare(original, generated, tol: float = 0.012) -> dict:
    """Match notes by pitch within `tol` seconds. Both are sequences with .time and .pitch
    (GlissNote) or (time, pitch, ...) tuples. Returns counts and timing errors (ms)."""
    def tp(n):
        return (n.time, n.pitch) if hasattr(n, "time") else (n[0], n[1])
    gen = sorted(tp(n) for n in generated)
    free = [True] * len(gen)
    times = [g[0] for g in gen]
    matched, errs, missing = 0, [], []
    for t, p in sorted(tp(n) for n in original):
        i = bisect.bisect_left(times, t - tol)
        best = None
        while i < len(gen) and gen[i][0] <= t + tol:
            if free[i] and gen[i][1] == p and (best is None or abs(gen[i][0] - t) < abs(gen[best][0] - t)):
                best = i
            i += 1
        if best is None:
            missing.append((round(t, 3), p))
        else:
            free[best] = False
            matched += 1
            errs.append(abs(gen[best][0] - t) * 1000)
    extra = [(round(g[0], 3), g[1]) for g, f in zip(gen, free) if f]
    return {"original": len(original), "generated": len(generated), "matched": matched,
            "missing": missing, "extra": extra,
            "mean_ms": statistics.fmean(errs) if errs else 0.0, "max_ms": max(errs, default=0.0)}


# --- planning a new ad lib gliss --------------------------------------------------------------


def plan(start: float, end: float, pedals: Pedals, *, low: int, high: int,
         first: int | None = None, last: int | None = None, sweep: float = 0.6,
         pattern: str | None = None, jitter: float = 0.2, range_jitter: int = 2,
         hang: float = 1.5, overlap: float = 0.25, repluck: bool = False,
         turn_gap: float | None = None, velocity: int = 100, release: float = 0.25,
         seed: int = 1) -> AdLibGliss:
    """Sketch -> sweeps. low/high/first/last are MIDI pitches (the nearest strings are used).

    pattern: "U"/"D" per sweep ("DUDUD"); repeated letters ("UUU") are overlapping sweeps in
    the same direction, sawtooth-like, each starting `overlap` of its length before the one
    before it ends. Without a pattern the sweeps alternate, about `sweep` seconds each,
    starting away from `first` and ending on `last`. Turning points vary by up to
    `range_jitter` strings inside [low, high]; lengths by ±`jitter`; `seed` makes it repeatable.

    Played as a harpist would (user, 2026-11-01): a turn reverses onto the neighbouring string
    one regular step after the turning string (`repluck=True` sounds the turning string again,
    `turn_gap` fixes the pause in seconds); an up/down wave stays in one hand (`layer`), and an
    overlapping restart in the same direction is taken by the other hand, so at most two sweeps
    sound at once. `physical_checks` lists anything a harpist couldn't do.
    """
    rng = random.Random(seed)
    lo, hi = string_near(pedals, low, -1), string_near(pedals, high, +1)
    if hi <= lo:
        raise ValueError("high must be above low")
    f = string_near(pedals, first) if first is not None else None
    la = string_near(pedals, last) if last is not None else None
    if pattern is None:
        d0 = "D" if f is not None and hi - f < f - lo else "U"
        k = max(1, round((end - start) / sweep))
        want_last = None if la is None else ("D" if la - lo < hi - la else "U")
        if want_last is not None:
            last_dir = d0 if k % 2 else ("U" if d0 == "D" else "D")
            if last_dir != want_last:
                k = k + 1 if (end - start) / (k + 1) >= sweep * 0.75 or k == 1 else k - 1
        pattern = "".join(d0 if i % 2 == 0 else ("U" if d0 == "D" else "D") for i in range(k))
    pattern = pattern.upper()
    if not pattern or set(pattern) - {"U", "D"}:
        raise ValueError("pattern is U/D letters")

    def top():
        return hi - rng.randint(0, range_jitter)

    def bottom():
        return lo + rng.randint(0, range_jitter)

    ends: list[tuple[int, int]] = []
    pos = f if f is not None else (lo if pattern[0] == "U" else hi)
    for i, d in enumerate(pattern):
        if i > 0 and d == pattern[i - 1]:            # same direction again: restart from the far side
            pos = bottom() + rng.randint(0, range_jitter) if d == "U" else top() - rng.randint(0, range_jitter)
        elif i > 0 and not repluck:
            pos += 1 if d == "U" else -1
        target = (top() if d == "U" else bottom())
        if i == len(pattern) - 1 and la is not None:
            target = la
        if (target - pos) * (1 if d == "U" else -1) <= 0:     # keep at least a short sweep
            target = pos + (3 if d == "U" else -3)
        ends.append((pos, target))
        pos = target

    w = [(abs(b - a) + 1) * (1 + jitter * rng.uniform(-1, 1)) for a, b in ends]
    same = [i + 1 < len(pattern) and pattern[i + 1] == pattern[i] for i in range(len(pattern))]
    # the pause at a turn: fixed (`turn_gap`, or 20 ms for a repluck) or one regular step of the
    # next sweep, which scales with the sweep lengths: gap_i = scale * unit_i
    fixed = turn_gap if turn_gap is not None else (0.02 if repluck else None)
    unit = [0.0 if same[i] or i + 1 == len(ends) else
            (w[i + 1] / max(1.0, abs(ends[i + 1][1] - ends[i + 1][0]) - 1 + hang) if fixed is None else 0.0)
            for i in range(len(ends))]
    turns = sum(1 for i in range(len(ends) - 1) if not same[i])
    total = end - start - (fixed or 0.0) * turns
    denom = sum(w) - overlap * sum(wi for wi, s in zip(w, same) if s) + sum(unit)
    scale = total / denom
    if scale <= 0:
        raise ValueError("gliss too short for this pattern")
    sweeps: list[Sweep] = []
    t, hand = start, 0
    for i, ((a, b), wi) in enumerate(zip(ends, w)):
        if i > 0 and same[i - 1]:
            hand = 1 - hand                          # the other hand starts the overlapping sweep
        dur = wi * scale
        sweeps.append(Sweep(t, t + dur, a, b, velocity, hang, hand))
        t = t + dur - overlap * dur if same[i] else t + dur + (fixed if fixed is not None else unit[i] * scale)
    sweeps[-1].end = end
    return AdLibGliss(pedals, sweeps, release)


def physical_checks(g: AdLibGliss, hands: bool = True) -> list[str]:
    """What a harpist couldn't (or wouldn't) play: a turning string sounding twice, more than two
    sweeps at once, and (with `hands`, i.e. layers are hands) a hand starting a sweep before
    finishing its last one."""
    out = []
    strs = strings(g.pedals)
    sw = sorted(g.sweeps, key=lambda s: s.start)
    for a in sw:
        for b in sw:
            if (b is not a and b.from_string == a.to_string and a.direction and b.direction == -a.direction
                    and abs(b.start - a.end) < 0.1):
                out.append(f"{a.end:.3f}s: turning string {strs[a.to_string].name} sounds twice")
    for s in sw:
        busy = sum(1 for o in sw if o.start <= s.start <= o.end)
        if busy > 2:
            out.append(f"{s.start:.3f}s: {busy} sweeps at once (two hands)")
    if hands:
        for layer in sorted({s.layer for s in sw}):
            mine = [s for s in sw if s.layer == layer]
            for a, b in zip(mine, mine[1:]):
                if b.start <= a.end:
                    out.append(f"{b.start:.3f}s: hand {layer + 1} starts before finishing ({a.end:.3f}s)")
    return out


def replan_args(g: AdLibGliss, **extra) -> dict:
    """`plan` arguments that redo a fitted gliss in the same style: same span, pedals, first and
    last strings, U/D pattern, typical sweep length, hang and spread of the turning points."""
    sw = sorted(g.sweeps, key=lambda s: s.start)
    strs = strings(g.pedals)
    ends = [i for s in sw for i in (s.from_string, s.to_string)]
    tops = [s.to_string for s in sw if s.direction > 0]
    bottoms = [s.to_string for s in sw if s.direction < 0]
    spread = max([2] + ([max(ends) - round(statistics.median(tops))] if tops else [])
                 + ([round(statistics.median(bottoms)) - min(ends)] if bottoms else []))
    args = dict(start=sw[0].start, end=max(s.end for s in sw), pedals=g.pedals,
                low=strs[min(ends)].pitch, high=strs[max(ends)].pitch, range_jitter=spread,
                first=strs[sw[0].from_string].pitch, last=strs[max(sw, key=lambda s: s.end).to_string].pitch,
                sweep=statistics.median(s.end - s.start for s in sw if s.end > s.start),
                hang=statistics.median(s.hang for s in sw),
                pattern="".join("D" if s.direction < 0 else "U" for s in sw if s.direction))
    args.update(extra)
    return args


# --- command line -----------------------------------------------------------------------------


def _pos(m, text: str) -> int:
    bar, _, q = text.partition("+")
    from fractions import Fraction
    return m.tick_at(int(bar), float(Fraction(q)) if q else 0)


def select(m, t0: int, t1: int, tracks=None, max_gap: float = 0.12):
    """MIDI notes of a region as (time s, pitch, velocity, track). A track's first note in the
    region is left out when it ends a run that started before the region (a separate lead-in)."""
    tol = m.ppq // 8
    out = []
    for tr in sorted({n.track for n in m.notes}):
        if tracks and tr not in tracks:
            continue
        ns = [n for n in m.notes if n.track == tr and n.pitch >= HARP_LOW_PITCH]
        inside = [n for n in ns if t0 <= n.start <= t1 + tol]
        before = [n for n in ns if n.start < t0]
        if inside and before and m.seconds(inside[0].start) - m.seconds(before[-1].start) <= max_gap:
            inside = inside[1:]
        out += [(m.seconds(n.start), n.pitch, n.velocity, tr) for n in inside]
    return sorted(out)


def _write(path, m, gl: AdLibGliss, program: int = 46):
    from . import midi
    layers: dict[int, midi.Track] = {}
    for g in gl.notes():
        tr = layers.setdefault(g.layer, midi.Track(f"Harp gliss {g.layer + 1}", channel=g.layer, program=program))
        start = m.tick(g.time)
        tr.notes.append((start, g.pitch, g.velocity, max(1, m.tick(g.time + g.length) - start)))
    midi.write(path, [layers[k] for k in sorted(layers)], ppq=m.ppq, tempos=m.tempos, time_sigs=m.time_sigs)


def main(argv=None) -> int:
    from . import midi
    ap = argparse.ArgumentParser(prog="python -m doricokit.gliss")
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fit", help="fit an ad lib gliss spec to a region of a MIDI file")
    f.add_argument("file")
    f.add_argument("--start", required=True, help="BAR or BAR+CROTCHETS (bar 1 = start of file)")
    f.add_argument("--end", required=True, help="position of the gliss's last note")
    f.add_argument("--tracks", help="comma-separated track numbers (default: all)")
    f.add_argument("--pedals", help='e.g. "Db C B | E F# G# A" (default: inferred)')
    f.add_argument("--json", help="write the spec as JSON")
    f.add_argument("--write", help="write the regenerated gliss as MIDI")
    f.add_argument("--replan", help="write a freshly planned gliss over the same span as MIDI")
    f.add_argument("--seed", type=int, default=1)
    f.add_argument("--velocity", type=int, default=100, help="velocity for --replan")
    a = ap.parse_args(argv)

    m = midi.read(a.file)
    t0, t1 = _pos(m, a.start), _pos(m, a.end)
    tracks = {int(x) for x in a.tracks.split(",")} if a.tracks else None
    notes = select(m, t0, t1, tracks)
    r = fit(notes, Pedals.parse(a.pedals) if a.pedals else None)
    print(f"pedals: {r.gliss.pedals}   notes: {len(notes)}   sweeps: {len(r.sweeps)}")
    for s in r.sweeps:
        print(f"  L{s['layer']} {s['dir']:>4} {s['from']:>4} -> {s['to']:<4} n={s['notes']:2} "
              f"{s['start']:7.3f}-{s['end']:7.3f}s  {s['per_second']:4.1f}/s  step {s['step_ms']:4.1f} ms  "
              f"hang {s['hang']:.2f}")
    for w in r.warnings:
        print("  !", w)
    c = compare(notes, r.gliss.notes())
    print(f"regenerated: {c['matched']}/{c['original']} matched, {len(c['missing'])} missing, "
          f"{len(c['extra'])} extra, timing mean {c['mean_ms']:.1f} ms max {c['max_ms']:.1f} ms")
    if a.json:
        with open(a.json, "w") as fh:
            json.dump(r.gliss.to_dict(), fh, indent=1)
    if a.write:
        _write(a.write, m, r.gliss)
    if a.replan:
        args = replan_args(r.gliss, velocity=a.velocity, seed=a.seed)
        g = plan(**args)
        if a.json:
            with open(a.json.removesuffix(".json") + "-replan.json", "w") as fh:
                json.dump({"plan": {**args, "pedals": str(args["pedals"])}, "spec": g.to_dict()}, fh, indent=1)
        _write(a.replan, m, g)
        for w in physical_checks(g):
            print("  ! planned:", w)
        print(f"replanned: {len(g.sweeps)} sweeps, pattern "
              f"{''.join('U' if s.direction > 0 else 'D' for s in g.sweeps)}, {len(g.notes())} notes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
