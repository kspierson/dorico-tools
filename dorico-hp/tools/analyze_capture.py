"""Compare Finale Human Playback MIDI captures with the written test pieces.

    python3 tools/analyze_capture.py CAPTURE_DIR [PIECE ...]

CAPTURE_DIR holds one folder per style (00-none, 01-standard, ...) of .mid files
named after the test pieces. Writes, per style folder:

    <piece>.notes.tsv   one row per written note: what was played
    <piece>.cc.tsv      controller / pitch bend events per channel

and prints a per-bar summary (velocity, length ratio, onset offset, CC11/CC1/CC7).
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from doricohp import smf  # noqa: E402

PIECES = Path(__file__).resolve().parents[1] / "test-pieces"


def match(expected: list[dict], played: list[smf.NoteEv], ppq: int):
    """Pair written notes with played ones (same pitch, nearest start)."""
    used = set()
    pairs = []
    by_pitch: dict[int, list[int]] = {}
    for i, n in enumerate(played):
        by_pitch.setdefault(n.pitch, []).append(i)
    for e in sorted(expected, key=lambda e: (e["pos"], e["pitch"])):
        target = e["pos"] * ppq
        best, best_d = None, ppq * 0.75
        for i in by_pitch.get(e["pitch"], ()):
            if i in used:
                continue
            d = abs(played[i].start - target)
            if d < best_d:
                best, best_d = i, d
        if best is not None:
            used.add(best)
        pairs.append((e, played[best] if best is not None else None))
    extras = [n for i, n in enumerate(played) if i not in used]
    return pairs, extras


def cc_value_at(ctrls: list[smf.CtrlEv], number: int, tick: int) -> int | None:
    v = None
    for c in ctrls:
        if c.tick > tick:
            break
        if c.kind == "cc" and c.number == number:
            v = c.value
    return v


def analyze(style_dir: Path, piece: str, verbose: bool = True) -> list[dict]:
    mid = style_dir / f"{piece}.mid"
    if not mid.exists():
        return []
    meta = json.loads((PIECES / f"{piece}.expected.json").read_text())
    m = smf.read(mid)
    groups: dict[tuple[int, int], list[dict]] = {}
    for e in meta["notes"]:
        groups.setdefault((e["part"], e["stave"]), []).append(e)
    tracks = sorted({n.track for n in m.notes}, key=lambda t: min(n.start for n in m.notes if n.track == t))
    rows = []
    cc_lines = ["track\tchannel\tkind\tnumber\tvalue\ttick\tbeat"]
    for c in m.ctrls:
        cc_lines.append(f"{c.track}\t{c.channel}\t{c.kind}\t{c.number}\t{c.value}\t{c.tick}\t{c.tick / m.ppq:.3f}")
    for gi, (key, exp) in enumerate(sorted(groups.items())):
        if gi >= len(tracks):
            break
        tr = tracks[gi]
        played = [n for n in m.notes if n.track == tr]
        ctrls = [c for c in m.ctrls if c.track == tr or (c.channel == (played[0].channel if played else -1))]
        pairs, extras = match(exp, played, m.ppq)
        for e, p in pairs:
            r = dict(e)
            r["marks"] = ",".join(e["marks"])
            r["words"] = ",".join(e["words"])
            if p is None:
                r.update(played=False)
            else:
                written_tick = e["pos"] * m.ppq
                r.update(played=True, vel=p.velocity, start_tick=p.start, end_tick=p.end,
                         onset_ticks=p.start - written_tick,
                         onset_ms=round((m.seconds(p.start) - m.seconds(int(written_tick))) * 1000, 1),
                         len_ratio=round(p.length / (e["dur"] * m.ppq), 3) if e["dur"] else None,
                         len_ms=round((m.seconds(p.end) - m.seconds(p.start)) * 1000, 1),
                         bpm=round(m.bpm_at(p.start), 2),
                         cc1=cc_value_at(ctrls, 1, p.start), cc7=cc_value_at(ctrls, 7, p.start),
                         cc11=cc_value_at(ctrls, 11, p.start))
            rows.append(r)
        for x in extras:
            rows.append(dict(part=key[0], stave=key[1], bar=int(x.start / m.ppq // (meta["time"][0] * 4 / meta["time"][1])) + 1,
                             extra=True, pitch=x.pitch, vel=x.velocity, start_tick=x.start, end_tick=x.end))
    cols = ["part", "stave", "bar", "beat", "pitch", "dur", "marks", "dyn", "wedge", "slur", "words", "grace",
            "played", "vel", "onset_ticks", "onset_ms", "len_ratio", "len_ms", "bpm", "cc1", "cc7", "cc11",
            "start_tick", "end_tick", "extra"]
    lines = ["\t".join(cols)] + ["\t".join("" if r.get(c) is None else str(r.get(c, "")) for c in cols) for r in rows]
    out_dir = style_dir / "analysis"
    out_dir.mkdir(exist_ok=True)
    (out_dir / f"{piece}.notes.tsv").write_text("\n".join(lines) + "\n")
    (out_dir / f"{piece}.cc.tsv").write_text("\n".join(cc_lines) + "\n")
    if verbose:
        summarize(piece, style_dir.name, rows, m)
    return rows


def summarize(piece: str, style: str, rows: list[dict], m: smf.Midi) -> None:
    print(f"\n== {piece}  [{style}]  ppq={m.ppq}  tempo events={len(m.tempos)}  "
          f"cc events={sum(1 for c in m.ctrls if c.kind == 'cc')}")
    bars: dict[tuple[int, int], list[dict]] = {}
    for r in rows:
        bars.setdefault((r.get("part", 0), r.get("bar", 0)), []).append(r)
    print("part bar  n  extra  vel(min-max)  len%   onset_ms   bpm    cc11  cc1  cc7  marks/dyn")
    for (part, bar), rs in sorted(bars.items()):
        pl = [r for r in rs if r.get("played")]
        ex = [r for r in rs if r.get("extra")]
        if not pl:
            print(f"{part:4} {bar:3} {0:2} {len(ex):5}")
            continue
        vels = [r["vel"] for r in pl]
        lens = [r["len_ratio"] for r in pl if r.get("len_ratio")]
        ons = [r["onset_ms"] for r in pl]
        tags = sorted({r.get("marks") or "" for r in pl} | {r.get("dyn") or "" for r in pl} |
                      {("<" if r.get("wedge") == "cresc" else ">") for r in pl if r.get("wedge")} |
                      {r.get("words") for r in pl if r.get("words")})
        def rng(xs):
            return f"{min(xs)}-{max(xs)}" if min(xs) != max(xs) else f"{xs[0]}"
        cc = lambda k: rng([r[k] for r in pl if r.get(k) is not None]) if any(r.get(k) is not None for r in pl) else "-"
        print(f"{part:4} {bar:3} {len(pl):2} {len(ex):5}  {rng(vels):12} "
              f"{(statistics.mean(lens) * 100 if lens else 0):5.0f}  {statistics.mean(ons):8.1f}  "
              f"{statistics.mean(r['bpm'] for r in pl):6.1f}  {cc('cc11'):6} {cc('cc1'):5} {cc('cc7'):5} {' '.join(t for t in tags if t)}")


def main(argv: list[str]) -> None:
    root = Path(argv[0])
    pieces = argv[1:] or sorted(p.name.removesuffix(".expected.json") for p in PIECES.glob("*.expected.json"))
    styles = sorted(d for d in root.iterdir() if d.is_dir()) if not (root / f"{pieces[0]}.mid").exists() else [root]
    for s in styles:
        for p in pieces:
            analyze(s, p)


if __name__ == "__main__":
    main(sys.argv[1:])
