"""Draw the dorigit app icon (stdlib only): a branch graph whose nodes are note heads.

    python3 assets/make_icon.py assets/app-icon.png && npx tauri icon assets/app-icon.png
"""
import math, struct, sys, zlib

N, SS = 1024, 3  # output size, supersampling
W = N * SS

def rr(x, y, r):  # rounded-square mask
    m = 0.06 * W
    cx, cy = min(max(x, m + r), W - m - r), min(max(y, m + r), W - m - r)
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r and m <= x <= W - m and m <= y <= W - m

def seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    t = max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)

def head(px, py, cx, cy, r):  # tilted ellipse note head
    a = math.radians(-22)
    x, y = px - cx, py - cy
    xr, yr = x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)
    return (xr / (r * 1.32)) ** 2 + (yr / r) ** 2 <= 1

s = W / 1024
main_x = 380 * s
nodes = [(main_x, 760 * s), (main_x, 470 * s), (main_x, 250 * s)]  # main line, bottom->top
branch = (650 * s, 400 * s)
lines = [(nodes[0], nodes[1]), (nodes[1], nodes[2]), (nodes[0], branch)]
stems = [(n[0] + 52 * s, n[1] - 8 * s, n[0] + 52 * s, n[1] - 190 * s) for n in [branch]]
BG1, BG2 = (28, 33, 52), (44, 52, 86)
LINE, HEAD, ACC = (150, 170, 230), (245, 240, 230), (240, 178, 74)

rows = []
for oy in range(N):
    row = bytearray([0])
    for ox in range(N):
        acc = [0, 0, 0, 0]
        for sy in range(SS):
            for sx in range(SS):
                x, y = ox * SS + sx + 0.5, oy * SS + sy + 0.5
                if not rr(x, y, 0.18 * W):
                    continue
                t = y / W
                c = tuple(int(BG1[i] * (1 - t) + BG2[i] * t) for i in range(3))
                if any(seg_dist(x, y, *a, *b) < 22 * s for a, b in lines):
                    c = LINE
                if any(seg_dist(x, y, *st[:2], *st[2:]) < 12 * s for st in stems):
                    c = ACC
                if any(head(x, y, nx, ny, 62 * s) for nx, ny in nodes):
                    c = HEAD
                if head(x, y, *branch, 62 * s):
                    c = ACC
                acc[0] += c[0]; acc[1] += c[1]; acc[2] += c[2]; acc[3] += 255
        k = SS * SS
        a = acc[3] // k
        row += bytes([acc[0] // max(1, acc[3] // 255), acc[1] // max(1, acc[3] // 255), acc[2] // max(1, acc[3] // 255), a]) if a else bytes(4)
    rows.append(bytes(row))

def chunk(t, d):
    return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", N, N, 8, 6, 0, 0, 0))
png += chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + chunk(b"IEND", b"")
open(sys.argv[1], "wb").write(png)
