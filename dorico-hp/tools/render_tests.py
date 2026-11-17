"""Render the HP test pieces with the engine, laid out like a Finale capture folder.

    python3 tools/render_tests.py OUT_DIR [STYLE_DIR=STYLE ...]
    e.g. python3 tools/render_tests.py captures/engine 01-standard=Standard 04-romantic=Romantic

Reads the Finale versions of the test pieces (HPCaptures\\finale\\*.musx, through
finale2dorico) so the input notation is exactly what Finale played. Then:
    python3 tools/analyze_capture.py OUT_DIR
    python3 tools/style_report.py OUT_DIR
"""
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from doricohp import engine, model, render  # noqa: E402
from doricohp.profiles import Profiles  # noqa: E402

SRC = Path("/mnt/c/Users/kspie/Documents/HPCaptures/finale")


def main(out: str, pairs: list[str]) -> None:
    pieces = sorted(SRC.glob("[0-9][0-9]-*.musx"))
    scores = {}
    for p in pieces:
        try:
            scores[p.stem] = model.load(str(p))
        except Exception as e:  # noqa: BLE001
            print("skip", p.name, e)
    for pair in pairs:
        d, style = pair.split("=")
        od = Path(out) / d
        od.mkdir(parents=True, exist_ok=True)
        prof = Profiles(style)
        for name, sc in scores.items():
            try:
                render.render(sc, engine.perform(sc, prof), str(od / f"{name}.mid"))
            except Exception:  # noqa: BLE001
                print("fail", d, name)
                traceback.print_exc(limit=2)
        print(d, len(scores), "pieces")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
