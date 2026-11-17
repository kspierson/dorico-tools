"""Page-by-page text of a PDF (stdlib only), e.g. to find which pages belong to which cue.

    python3 research/tools/pdf_index.py SCORE.pdf [REGEX]

Walks the page tree (object streams included), decompresses each page's content streams and
prints the text strings drawn on it (Tj/TJ). With REGEX, prints only the first match per page.
Good enough for headers such as "1m1R (bars 1-63)"; not a general text extractor.
"""
import re
import sys
import zlib

data = open(sys.argv[1], "rb").read()
objs: dict[int, bytes] = {}
for m in re.finditer(rb"(?<![0-9])(\d+)\s+0\s+obj\b", data):
    objs[int(m.group(1))] = data[m.end():data.find(b"endobj", m.end())]


def stream(body: bytes) -> bytes | None:
    m = re.search(rb"stream\r?\n", body)
    if not m:
        return None
    raw = body[m.end():]
    raw = raw[:raw.rfind(b"endstream")] if b"endstream" in raw else raw
    if b"/FlateDecode" in body[:m.start()]:
        try:
            return zlib.decompressobj().decompress(raw)
        except zlib.error:
            return None
    return raw


for num, body in list(objs.items()):  # objects packed in object streams
    if re.search(rb"/Type\s*/ObjStm", body):
        s = stream(body)
        n = int(re.search(rb"/N\s+(\d+)", body).group(1))
        first = int(re.search(rb"/First\s+(\d+)", body).group(1))
        nums = list(map(int, s[:first].split()))
        pairs = list(zip(nums[0::2], nums[1::2]))
        for i, (on, off) in enumerate(pairs[:n]):
            end = pairs[i + 1][1] if i + 1 < len(pairs) else len(s) - first
            objs.setdefault(on, s[first + off:first + end])


def refs(body: bytes, key: bytes) -> list[int]:
    m = re.search(rb"/" + key + rb"\s*(\[[^\]]*\]|\d+\s+0\s+R)", body)
    return [int(x) for x in re.findall(rb"(\d+)\s+0\s+R", m.group(1))] if m else []


root = int(re.findall(rb"/Root\s+(\d+)\s+0\s+R", data)[-1])
pages: list[int] = []


def walk(n: int) -> None:
    body = objs.get(n, b"")
    if re.search(rb"/Type\s*/Pages\b", body):
        for k in refs(body, b"Kids"):
            walk(k)
    else:
        pages.append(n)


walk(refs(objs[root], b"Pages")[0])


def text(n: int) -> str:
    out = []
    for c in refs(objs[n], b"Contents"):
        s = stream(objs.get(c, b"")) or b""
        for a, b in re.findall(rb"\(((?:\\.|[^\\)])*)\)\s*Tj|\[((?:\\.|[^\]])*)\]\s*TJ", s):
            out.append(a if a else b"".join(re.findall(rb"\(((?:\\.|[^\\)])*)\)", b)))
    return " | ".join(x.decode("latin-1").replace("\\(", "(").replace("\\)", ")") for x in out)


pat = re.compile(sys.argv[2]) if len(sys.argv) > 2 else None
for i, p in enumerate(pages, 1):
    t = text(p)
    if pat:
        m = pat.search(t)
        print(i, m.group(0) if m else "")
    else:
        print(i, t[:300])
