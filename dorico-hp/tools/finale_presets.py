"""Read Human Playback's built-in style presets out of Finale.exe (Finale 26).

    python3 -I tools/finale_presets.py [Finale.exe] > research/hp-presets.tsv

The table is 36-byte records at VA 0x14147ec10, indexed by style number - 1
(found via FUN_1401a45e0, which copies a preset into the active settings).
Record layout (from the reader functions, see research/hp-engine.md); bytes 18-35
are not yet mapped and are printed as x18..x34 (16-bit values):
  +0  u16 flags A   +2 u16 flags B   +4 rhythmicFeel  +6 rhythmicAccents
  +8  rubato        +10 reverb       +12 selectedPreset  +14 swing  +16 mood
"""
import struct
import sys

EXE = sys.argv[1] if len(sys.argv) > 1 else "/mnt/c/Program Files/MakeMusic/Finale/26/Finale.exe"
TABLE_VA = 0x14147ec10
STYLE_NAMES_VA = 0x140fe8b38  # 18 shorts: style numbers in menu order (FUN_1401a4e40)

FLAGS_A = {2: "pedalMarkings", 3: "interpretSlurs", 4: "interpretHairpins", 5: "interpretGlissandiAndBends",
           6: "interpretAccRallTexts", 7: "interpretFermatas", 9: "interpretFinalBars", 15: "interpretOrnaments"}
FLAGS_B = {0: "emphasizeShortSyncops", 1: "automaticPedaling", 2: "automaticPanning", 3: "stringHarmonics",
           4: "adjustDottedEighth", 5: "adjustLonger", 6: "baroqueStyle", 7: "automaticEspressivo",
           8: "detectAccompaniment", 9: "adjustChordBalance", 10: "softenBasses", 11: "autoDetectSolo",
           12: "vienneseWaltzFeel", 13: "interpretCadences", 14: "strumChords", 15: "exactDrumRolls"}
NAMES = {1: "None", 2: "Classical", 3: "Romantic", 4: "Baroque", 5: "Jazz", 6: "Rock", 7: "Blues",
         8: "21st Century", 9: "Custom", 10: "Light waltz", 11: "Viennese waltz", 12: "Latin", 13: "Samba",
         14: "Funk", 15: "Ballad", 16: "Reggae", 17: "Pop", 18: "Standard", 19: "Marching band"}
VALUES = ["rhythmicFeel", "rhythmicAccents", "rubato", "reverb", "selectedPreset", "swing", "mood"]


def sections(data):
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    nsec = struct.unpack_from("<H", data, pe + 6)[0]
    opt = struct.unpack_from("<H", data, pe + 20)[0]
    base = struct.unpack_from("<Q", data, pe + 24 + 24)[0]
    out = []
    for i in range(nsec):
        o = pe + 24 + opt + 40 * i
        name = data[o:o + 8].rstrip(b"\0").decode()
        vsize, va, rsize, raw = struct.unpack_from("<IIII", data, o + 8)
        out.append((name, base + va, vsize, raw, rsize))
    return out


def read_va(data, secs, va, n):
    for name, sva, vsize, raw, rsize in secs:
        if sva <= va < sva + vsize:
            off = va - sva
            if off + n > rsize:
                raise ValueError(f"{hex(va)} is in uninitialised part of {name}")
            return data[raw + off: raw + off + n]
    raise ValueError(hex(va))


def main():
    data = open(EXE, "rb").read()
    secs = sections(data)
    order = struct.unpack("<18h", read_va(data, secs, STYLE_NAMES_VA, 36))
    print("# style menu order:", order, file=sys.stderr)
    cols = ["index", "name"] + VALUES + [f"x{o}" for o in range(18, 36, 2)] + list(FLAGS_A.values()) + list(FLAGS_B.values())
    print("\t".join(cols))
    for i in range(19):
        rec = read_va(data, secs, TABLE_VA + 36 * i, 36)
        a, b, *vals = struct.unpack("<HH7h9h", rec)
        if not any(rec):
            continue
        row = [str(i + 1), NAMES.get(i + 1, "?")] + [str(v) for v in vals]
        row += ["1" if a >> bit & 1 else "" for bit in FLAGS_A]
        row += ["1" if b >> bit & 1 else "" for bit in FLAGS_B]
        print("\t".join(row))


if __name__ == "__main__":
    main()
