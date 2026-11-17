"""Where were articulations added? Rates by note context (length, beat, rests, peaks).

    python3 tools/marking_context.py SCORE PLAYBACK [flow_a flow_b]

Inputs as for compare_versions.py. Prints % of notes in each context that gained each articulation.
"""
import sys, json
from collections import Counter, defaultdict
from fractions import Fraction
sys.path.insert(0, __import__('os').path.dirname(__file__))
from compare_versions import load
A, B = load(sys.argv[1]), load(sys.argv[2])
fa, fb = int(sys.argv[3]) if len(sys.argv) > 3 else 0, int(sys.argv[4]) if len(sys.argv) > 4 else 0
a, b = A[fa], B[fb]
bars = b["bar_starts"]
def beatpos(pos):
    bs = max((s for s in bars if s <= pos), default=0)
    i = bars.index(bs); blen = (bars[i+1] - bs) if i+1 < len(bars) else 4
    off = pos - bs
    if off == 0: return "downbeat"
    if off.denominator == 1: return "on beat"
    if (off*2).denominator == 1: return "8th off"
    return "16th off"
feat = defaultdict(lambda: [0, Counter()])
for name in a["staves"]:
    if name not in b["staves"]: continue
    ca = a["staves"][name]["chords"]; cb = {(c[0], c[2]): c for c in b["staves"][name]["chords"]}
    slur_a = []  # not available per note; skip
    for i, c in enumerate(ca):
        k = (c[0], c[2]); 
        if k not in cb: continue
        prev = ca[i-1] if i else None
        nxt = ca[i+1] if i+1 < len(ca) else None
        after_rest = prev is None or prev[0] + prev[1] < c[0]
        before_rest = nxt is None or c[0] + c[1] < nxt[0]
        d = c[1]
        dur = "≤16th" if d <= Fraction(1,4) else "8th" if d <= Fraction(1,2) else "crotchet" if d <= 1 else "minim" if d <= 2 else "longer"
        hi = max(c[2])
        peak = prev is not None and nxt is not None and hi > max(prev[2]) and hi > max(nxt[2])
        added = set(cb[k][3]) - set(c[3])
        fs = {"dur " + dur, beatpos(c[0]), "after rest" if after_rest else "legato in", "before rest" if before_rest else "continues", "pitch peak" if peak else "not peak",
              "already marked" if c[3] else "unmarked"}
        for f in fs:
            feat[f][0] += 1
            for x in added: feat[f][1][x] += 1
        feat["ALL"][0] += 1
        for x in added: feat["ALL"][1][x] += 1
arts = ["tenuto", "accent", "marcato", "staccato"]
print(f"{'feature':16} {'notes':>6} " + " ".join(f"{x+'%':>9}" for x in arts))
for f in ["ALL", "dur ≤16th", "dur 8th", "dur crotchet", "dur minim", "dur longer", "downbeat", "on beat", "8th off", "16th off", "after rest", "legato in", "before rest", "continues", "pitch peak", "not peak", "unmarked", "already marked"]:
    n, c = feat[f]
    if n: print(f"{f:16} {n:6} " + " ".join(f"{100*c[x]/n:9.1f}" for x in arts))
