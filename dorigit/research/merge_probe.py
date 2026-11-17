"""Three-way merge feasibility probe (see docs/MERGE.md §1, §8).

    uv run python dorigit/research/merge_probe.py BASE.dorico A.dorico B.dorico

Moved from the retired Python prototype (prototype/experiments/) on 2026-10-30 and switched to
the shared engine: events come from `doricokit.listing`, the same Rust model `dorigit show` and
`dorigit diff` use. Same numbers as the prototype on both MERGE.md cases (HP Plus 5, Obi-Wan End
Credits). To be re-implemented in Rust as `dorigit merge-preview` (MERGE.md M1).
"""
import collections
import sys

from doricokit import container, listing


def load(p):
    return container.open_score(p).root, listing.read(p)


def events(score):
    out = {}
    for f in score["flows"]:
        for e in f["events"]:
            if e["kind"] in ("time signature", "barline"): continue
            out[(f["flow_id"], e["event_id"])] = e
    return out

def changes(base, side):
    eb, es = events(base), events(side)
    ch = {}
    for k in eb.keys() | es.keys():
        a, b = eb.get(k), es.get(k)
        if a is None: ch[k] = ("add", b)
        elif b is None: ch[k] = ("del", a)
        elif (a["owner"], a["lane"], a["position"], a["text"], a["props"]) != (b["owner"], b["lane"], b["position"], b["text"], b["props"]): ch[k] = ("mod", b)
    return ch

def bar(e):
    w = e["where"].split()
    return w[1] if w and w[0] == "bar" else e["where"]

base_p, a_p, b_p = sys.argv[1:4]
(bd, base), (ad, A), (bdoc, B) = load(base_p), load(a_p), load(b_p)
ca, cb = changes(base, A), changes(base, B)
print(f"A: {len(ca)} event changes   B: {len(cb)} event changes")
# 1. same event changed on both sides
both = ca.keys() & cb.keys()
same_add = [k for k in both if ca[k][0] == "add" and cb[k][0] == "add"]
diff_add = [k for k in same_add if (ca[k][1]["owner"], ca[k][1]["text"], ca[k][1]["position"]) != (cb[k][1]["owner"], cb[k][1]["text"], cb[k][1]["position"])]
print(f"event IDs touched on both sides: {len(both)}  (both 'added' the same ID: {len(same_add)}, of which DIFFERENT events: {len(diff_add)})")
true_conf = [k for k in both if not (ca[k][0]=='add' and cb[k][0]=='add') and (ca[k][0], ca[k][1].get('text'), ca[k][1].get('position')) != (cb[k][0], cb[k][1].get('text'), cb[k][1].get('position'))]
print(f"existing events changed differently on both sides: {len(true_conf)}")
# 2. region overlap: (flow, owner, bar)
ra = collections.Counter((k[0], c[1]["owner"], bar(c[1])) for k, c in ca.items())
rb = collections.Counter((k[0], c[1]["owner"], bar(c[1])) for k, c in cb.items())
overlap = ra.keys() & rb.keys()
print(f"part-bars changed: A {len(ra)}, B {len(rb)}, changed on BOTH sides (conflict regions): {len(overlap)}")
parts = collections.Counter((f, o) for f, o, _ in overlap)
for (f, o), n in parts.most_common(6): print(f"   flow {f} / {o}: {n} bars")
# 3. id generators
def gens(d): return {c.tag: int(c.value) for c in d.child("idGenerators").children}
gb, ga, gbb = gens(bd), gens(ad), gens(bdoc)
print("idGenerators grown on both sides (collision risk):", {k: (gb[k], ga.get(k), gbb.get(k)) for k in gb if ga.get(k, 0) > gb[k] and gbb.get(k, 0) > gb[k]})
# 4. players / flows / meters
pa, pb, p0 = set(A["players"].items()), set(B["players"].items()), set(base["players"].items())
print("players changed A:", len(pa ^ p0), " B:", len(pb ^ p0))
for f0 in base["flows"]:
    fa = next((f for f in A["flows"] if f["flow_id"] == f0["flow_id"]), None); fb = next((f for f in B["flows"] if f["flow_id"] == f0["flow_id"]), None)
    ma = fa and [m["label"] + '@' + str(m["bar"]) for m in fa["meters"]] != [m["label"] + '@' + str(m["bar"]) for m in f0["meters"]]
    mb = fb and [m["label"] + '@' + str(m["bar"]) for m in fb["meters"]] != [m["label"] + '@' + str(m["bar"]) for m in f0["meters"]]
    if ma or mb: print(f"   flow {f0["name"]}: bar structure changed A={bool(ma)} B={bool(mb)}")
oa = {k for k in A["options"].keys() | base["options"].keys() if A["options"].get(k) != base["options"].get(k)}
ob = {k for k in B["options"].keys() | base["options"].keys() if B["options"].get(k) != base["options"].get(k)}
print(f"options changed A {len(oa)}, B {len(ob)}, both {len(oa & ob)}, both-but-different {sum(1 for k in oa & ob if A["options"].get(k) != B["options"].get(k))}")

print("--- after setting aside identical changes on both sides ---")
def sig(c): e = c[1]; return (c[0], e["owner"], e["lane"], e["position"], e["text"], e["props"])
same = {k for k in both if sig(ca[k]) == sig(cb[k])}
ra2 = collections.Counter((k[0], c[1]["owner"], bar(c[1])) for k, c in ca.items() if k not in same)
rb2 = collections.Counter((k[0], c[1]["owner"], bar(c[1])) for k, c in cb.items() if k not in same)
ov2 = ra2.keys() & rb2.keys()
print(f"identical on both: {len(same)}; remaining A {sum(ra2.values())} changes / {len(ra2)} part-bars, B {sum(rb2.values())} / {len(rb2)}")
print(f"part-bars with DIFFERENT changes on both sides (real conflict regions): {len(ov2)}")
parts = collections.Counter((f, o) for f, o, _ in ov2)
for (f, o), n in parts.most_common(5): print(f"   flow {f} / {o}: {n} bars")
ex = sorted(ov2)[:1]
for f, o, b in ex:
    print(f"   example, flow {f} / {o} / bar {b}:")
    for side, cs in (("A", ca), ("B", cb)):
        for k, c in cs.items():
            if k not in same and (k[0], c[1]["owner"], bar(c[1])) == (f, o, b): print(f"      {side}: {c[0]} {c[1]["where"]} {c[1]["kind"]} {c[1]["text"]} (id {k[1]})")
