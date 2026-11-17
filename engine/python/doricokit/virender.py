"""Render MIDI through the user's virtual instruments, outside Dorico (Project C, PLANNED_WORK.md §5).

Wraps `vi-render.exe` (engine/crates/vi-render, a headless VST2 host built for Windows and run
from WSL) and reads plug-in states saved in Dorico projects, so a test renders with exactly the
settings the user has in Dorico.

    from doricokit import virender as vr
    states = vr.plugin_states("HP WW.dorico")        # one per VST rack slot, in slot order
    fl = next(s for s in states if s.name == "SWAM Flute 64bit")
    ev = vr.Events(); ev.cc(0, 11, 80); ev.note(0.05, 74, 90, 1.0)
    vr.render(fl.name, ev, "out.wav", state=fl)     # 32-bit float WAV
    vr.info(fl.name, state=fl)                       # every parameter: name, value, display text

Build the renderer once: `cargo zigbuild --release --target x86_64-pc-windows-gnu -p vi-render`
(after `. engine/scripts/dev-env.sh`). Standard library only.
"""
from __future__ import annotations

import json
import re
import struct
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from . import paths

__all__ = ["PluginState", "Events", "plugin_states", "make_vstpreset", "find_plugin", "exe", "render",
           "info", "sweep", "read_wav"]

REPO = Path(__file__).resolve().parents[3]
VST2_DIRS = ["/mnt/c/Program Files/Steinberg/VstPlugins", "/mnt/c/Program Files/VSTPlugins",
             "/mnt/c/Program Files/VstPlugins", "/mnt/c/Program Files/Common Files/VST2",
             "/mnt/c/Program Files/Native Instruments/VSTPlugins 64 bit"]


@dataclass
class PluginState:
    slot: int              # rack slot as enginedata numbers it (1 = first slot, DoricoBeep)
    name: str              # plug-in name, e.g. "SWAM Flute 64bit"
    uid: str               # Dorico's plug-in uid (VST2 plug-ins: "VST" + 4-char id + name)
    kind: str = ""         # "FBCh" (bank chunk) / "FPCh" (program chunk) for VST2, "VST3", "" if none
    fx_id: str = ""        # VST2 4-char id ("FltC")
    chunk: bytes = b""     # VST2: what getChunk returned when Dorico saved; VST3: the component state
    component: bytes = b"" # the VST3 component state as stored (VST2: Dorico's "VstW" wrapper around the fxb)
    vstpreset: bytes = b"" # the whole state as a .vstpreset file (Cubase loads it on the same plug-in)

    @property
    def fxb(self) -> bytes:
        """VST2 plug-ins: the state as a standard .fxb/.fxp file (any VST2 host imports it)."""
        c = self.component.find(b"CcnK") if self.component[:4] == b"VstW" else -1
        if c < 0:
            return b""
        size = struct.unpack(">I", self.component[c + 4:c + 8])[0]
        return self.component[c:c + 8 + size]

    @property
    def vst2(self) -> bool:
        """VST2 plug-in (state in Dorico's "VstW" wrapper). Not the class id: VST2 ids are "VST" +
        4-char id + name, but some VST3 plug-ins use the same form (Kontakt 7: "VSTNiK7kontakt 7")."""
        return self.component[:4] == b"VstW"

    def kontakt7_state(self) -> bytes:
        """The state as Kontakt 7 (VST3) loads it: Kontakt 7's own component state, or a Kontakt
        5/6 (VST2) chunk, which is the same NI container (u64 size + "hsin" ...); Kontakt 7 loads
        it (checked 2026-11-01: Spitfire Harp, same sound and mics as in Dorico)."""
        if self.uid == KONTAKT7_CLASS_ID:
            return self.component
        if self.fx_id == "Ni$D":
            return self.chunk
        return b""

    def kontakt7_vstpreset(self) -> bytes:
        """Any Kontakt state as a Kontakt 7 .vstpreset (b"" if not Kontakt)."""
        st = self.kontakt7_state()
        return make_vstpreset(KONTAKT7_CLASS_ID, st) if st else b""

    def labels(self, min_len: int = 8) -> list[str]:
        """Readable strings in the state (patch/library names in Kontakt states, ...), in order."""
        out = []
        for m in re.finditer(rb"(?:[\x20-\x7e]\x00){%d,}|[\x20-\x7e]{%d,}" % (min_len, min_len), self.chunk):
            t = m.group(0).decode("utf-16le") if m.group(0)[1:2] == b"\x00" else m.group(0).decode("latin-1")
            t = t.strip()
            if t and t not in out:
                out.append(t)
        return out

    @property
    def dorico_slot(self) -> int:
        """The slot as score.dtn numbers it (`pluginRackContents` slotID, endpoint id >> 10): one lower."""
        return self.slot - 1

    @property
    def xml(self) -> str | None:
        """JUCE-style chunks ("VC2!" + size + XML), e.g. SWAM: the XML text."""
        if self.chunk[:4] == b"VC2!":
            n = struct.unpack("<I", self.chunk[4:8])[0]
            return self.chunk[8:8 + n].rstrip(b"\0").decode("utf-8", "replace")
        return None


KONTAKT7_CLASS_ID = "5653544E694B376B6F6E74616B742037"  # "VSTNiK7kontakt 7"


def make_vstpreset(class_id: str, component: bytes, controller: bytes = b"") -> bytes:
    """A .vstpreset file: "VST3", version 1, 32-char class id, offset of the chunk list; the
    component ("Comp") and controller ("Cont") states; "List" + (id, offset, size) entries."""
    head = 48
    body = component + controller
    lst = b"List" + struct.pack("<I", 2) + struct.pack("<4sQQ", b"Comp", head, len(component)) \
        + struct.pack("<4sQQ", b"Cont", head + len(component), len(controller))
    return b"VST3" + struct.pack("<I", 1) + class_id.encode() + struct.pack("<Q", head + len(body)) + body + lst


def plugin_states(project: str | Path) -> list[PluginState]:
    """Plug-in states of a project's VST instrument rack (`enginedata`), in slot order."""
    with zipfile.ZipFile(project) as z:
        data = z.read("supplementary_data/vstaudioengine/enginedata")
    # the mixer XML lists the rack: <instrument ... name=".." slot="N" uid="..">
    slots = [(int(m.group(2)), m.group(1).decode(), m.group(3).decode())
             for m in re.finditer(rb'<instrument id="\d+" name="([^"]*)"[^>]*? slot="(\d+)" uid="([0-9A-F]+)"', data)]
    # then binary "PluginState" records (instruments and effects), each naming its plug-in uid;
    # slots with the same plug-in take that plug-in's records in order
    starts = [m.start() for m in re.finditer(rb"PluginState", data)] + [len(data)]
    by_uid: dict[str, list[tuple[int, int]]] = {}
    for a, b in zip(starts, starts[1:]):
        m = re.compile(rb"VST3\x01\x00\x00\x00([0-9A-F]{32})").search(data, a, b)
        if m:
            by_uid.setdefault(m.group(1).decode(), []).append((a, b))
    out = []
    for slot, name, uid in slots:
        st = PluginState(slot, name, uid)
        if not by_uid.get(uid):
            out.append(st)
            continue
        start, end = by_uid[uid].pop(0)
        # The record holds a complete .vstpreset: "VST3", version, class id, offset of the chunk
        # list; the data; "List" + entries (id, offset, size): "Comp" (component state), "Cont".
        v = data.find(b"VST3\x01\x00\x00\x00", start, end)
        list_off = struct.unpack("<Q", data[v + 40:v + 48])[0]
        lst = v + list_off
        if data[lst:lst + 4] == b"List":
            count = struct.unpack("<I", data[lst + 4:lst + 8])[0]
            st.vstpreset = data[v:lst + 8 + 20 * count]
            for i in range(count):
                cid, off, size = struct.unpack("<4sQQ", data[lst + 8 + 20 * i:lst + 28 + 20 * i])
                if cid == b"Comp":
                    st.component = data[v + off:v + off + size]
        c = st.component.find(b"CcnK") if st.component[:4] == b"VstW" else -1
        if c >= 0:  # a VST2 plug-in in the VST3 wrapper: an fxBank / fxProgram inside
            kind = st.component[c + 8:c + 12].decode()
            st.kind, st.fx_id = kind, st.component[c + 16:c + 20].decode("latin-1")
            # "opaque chunk" layouts: chunk size at +156 (bank) / +56 (program)
            off = 156 if kind == "FBCh" else 56
            n = struct.unpack(">I", st.component[c + off:c + off + 4])[0]
            st.chunk = st.component[c + off + 4:c + off + 4 + n]
        elif st.component:
            st.kind, st.chunk = "VST3", st.component
        out.append(st)
    return out


def find_plugin(name: str) -> Path:
    """The VST2 DLL for a plug-in name (`<name>.dll`, or `<name> (64-bit).dll` etc.) in the usual folders."""
    for pattern in (f"{name}.dll", f"{name} (*).dll", f"{name} 64*.dll"):
        for d in VST2_DIRS:
            for p in Path(d).rglob(pattern) if Path(d).is_dir() else ():
                return p
    raise FileNotFoundError(f"VST2 plug-in {name!r} not found under {VST2_DIRS}")


def exe() -> Path:
    p = REPO / "target/x86_64-pc-windows-gnu/release/vi-render.exe"
    if not p.exists():
        raise FileNotFoundError(f"{p} missing: build it (module docstring)")
    return p


@dataclass
class Events:
    """Timed MIDI for one render (seconds; channel 1)."""
    events: list[dict] = field(default_factory=list)
    length: float | None = None

    def cc(self, t: float, num: int, value: int) -> None:
        self.events.append({"t": round(t, 6), "midi": [0xB0, num, max(0, min(127, int(value)))]})

    def note(self, t: float, pitch: int, velocity: int, dur: float) -> None:
        self.events.append({"t": round(t, 6), "midi": [0x90, pitch, max(1, min(127, int(velocity)))]})
        self.events.append({"t": round(t + dur, 6), "midi": [0x80, pitch, 64]})

    def raw(self, t: float, *b: int) -> None:
        self.events.append({"t": round(t, 6), "midi": list(b)})


def _win(p: Path | str) -> str:
    w = paths.to_windows(Path(p).resolve())
    if not w:
        raise RuntimeError("vi-render needs Windows or WSL")
    return w


def _dll(plugin: str | Path) -> str:
    """Windows path of a plug-in given by name, WSL path or Windows path."""
    p = str(plugin)
    if re.match(r"^[A-Za-z]:\\", p):
        return p
    return _win(Path(p) if p.endswith(".dll") else find_plugin(p))


def _common(plugin: str | Path, state: PluginState | bytes | None, sets: dict[int, float] | None,
            tmp: Path) -> list[str]:
    args = ["--plugin", _dll(plugin)]
    if state is not None:
        chunk = state.chunk if isinstance(state, PluginState) else state
        (tmp / "state.bin").write_bytes(chunk)
        args += ["--state", _win(tmp / "state.bin")]
        if isinstance(state, PluginState) and state.kind == "FBCh":
            args.append("--bank")
    for i, v in (sets or {}).items():
        args += ["--set", f"{i}={v}"]
    return args


def _tmp() -> tempfile.TemporaryDirectory:
    # under the repo's target/ so Windows can reach it through \\wsl.localhost
    base = REPO / "target/vi-render-tmp"
    base.mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(dir=base)


def render(plugin: str | Path, events: Events, out_wav: str | Path, state: PluginState | bytes | None = None,
           sets: dict[int, float] | None = None, tail: float = 2.0, sample_rate: int = 48000,
           params_out: str | Path | None = None) -> str:
    """Render `events` to `out_wav`; returns the renderer's log line."""
    with _tmp() as d:
        tmp = Path(d)
        (tmp / "events.json").write_text(json.dumps({"length": events.length, "events": events.events}))
        Path(out_wav).parent.mkdir(parents=True, exist_ok=True)
        args = [str(exe()), "render", *_common(plugin, state, sets, tmp), "--events", _win(tmp / "events.json"),
                "--out", _win(out_wav), "--tail", str(tail), "--sample-rate", str(sample_rate)]
        if params_out:
            args += ["--params-out", _win(params_out)]
        r = subprocess.run(args, capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError(f"vi-render failed: {r.stderr.strip()}")
        return r.stderr.strip().splitlines()[-1]


def info(plugin: str | Path, state: PluginState | bytes | None = None, sets: dict[int, float] | None = None) -> dict:
    """{"info": {...}, "params": [{"index", "name", "label", "display", "value"}]}"""
    with _tmp() as d:
        r = subprocess.run([str(exe()), "info", *_common(plugin, state, sets, Path(d))], capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError(f"vi-render failed: {r.stderr.strip()}")
        return json.loads(r.stdout)


def sweep(plugin: str | Path, param: int, steps: int = 100) -> list[tuple[float, str]]:
    """Display text of one parameter across 0..1: [(value where the text starts, text)]."""
    r = subprocess.run([str(exe()), "sweep", "--plugin", _dll(plugin),
                        "--param", str(param), "--steps", str(steps)], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"vi-render failed: {r.stderr.strip()}")
    return [(float(a), b) for a, b in (ln.split("\t", 1) for ln in r.stdout.splitlines() if "\t" in ln)]


def read_wav(path: str | Path) -> tuple[int, list[list[float]]]:
    """(sample rate, channels) of a 32-bit float WAV as vi-render writes it."""
    b = Path(path).read_bytes()
    if b[:4] != b"RIFF" or b[8:12] != b"WAVE":
        raise ValueError(f"{path}: not a WAV file")
    fmt, nch, sr = struct.unpack("<HHI", b[20:28])
    if fmt != 3:
        raise ValueError(f"{path}: expected 32-bit float")
    d = b.find(b"data", 12)
    n = struct.unpack("<I", b[d + 4:d + 8])[0] // 4
    flat = struct.unpack(f"<{n}f", b[d + 8:d + 8 + n * 4])
    return sr, [list(flat[c::nch]) for c in range(nch)]
