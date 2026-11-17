"""finale2dorico command line.

    python3 -m f2d convert Score.musx|Score.mus [-o Score.dorico] [options]
    python3 -m f2d ir Score.musx            # print the intermediate score model (JSON)
    python3 -m f2d enigma Score.musx        # print Finale's EnigmaXML
    python3 -m f2d dump Project.dorico      # print a Dorico project's score as XML
    python3 -m f2d review Project.dorico    # list places worth a look (report only)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _read(path: str, reader: str = "auto"):
    """Read a .mus / .musx / IR .json file into the Score IR.

    reader: "musxdom" = full reader (C++ extractor on musxdom + finale-mus-reader),
    "bootstrap" = the small Python reader (.musx only), "auto" = musxdom when the extractor
    is built, else bootstrap. Legacy .mus always needs the full reader.
    """
    from . import ir
    from .finale.extract import find_extractor
    p = Path(path)
    if p.suffix.lower() == ".json":
        return ir.from_json(p.read_text())
    is_mus = p.suffix.lower() == ".mus"
    if reader == "auto":
        reader = "musxdom" if (is_mus or find_extractor()) else "bootstrap"
    if reader == "bootstrap" and is_mus:
        raise SystemExit("Legacy .mus files need the full reader (--reader musxdom).")
    if reader == "musxdom":
        from .finale.extract import ExtractorMissing
        from .finale.facts import read_finale
        try:
            return read_finale(p)
        except ExtractorMissing as e:
            raise SystemExit(str(e))
    from .finale.enigma import read_musx
    return read_musx(p)


def cmd_convert(a) -> int:
    from .dorico.install import DoricoInstall
    from .dorico.writer import DoricoWriter, Options
    score = _read(a.input, a.reader)
    if not a.no_explode:
        from .explode import explode
        for line in explode(score, initial=a.single_line):
            print("  " + line)
    if not a.no_doublings:
        from .doublings import apply_doublings
        for line in apply_doublings(score):
            print("  " + line)
    out = Path(a.output) if a.output else Path(a.input).with_suffix(".dorico")
    opts = Options(force_durations=a.force_durations, seed=a.seed, library=a.library,
                   options_from_seed=a.options_from_seed, playback_from_seed=a.playback_from_seed,
                   write_dtn=a.dtn, parts=not a.no_parts)
    w = DoricoWriter(score, DoricoInstall(a.dorico_dir), opts)
    w.write(out)
    if a.report:
        import json
        side = out.with_suffix(".f2d-report.json")
        side.write_text(json.dumps({"source": str(a.input), "output": str(out),
                                    "notes": w.report, "warnings": score.warnings},
                                   indent=1, ensure_ascii=False))
        print(f"wrote {side}")
    print(f"wrote {out}")
    for line in w.report:
        print("  " + line)
    for wmsg in score.warnings:
        print("  warning: " + wmsg)
    return 0


def cmd_review(a) -> int:
    from .review import format_text, review, to_json
    findings = review(a.input)
    if a.json:
        Path(a.json).write_text(to_json(findings, a.input))
        print(f"wrote {a.json}")
    print(format_text(findings, None if a.all else 12))
    return 0


def cmd_clean(a) -> int:
    from doricokit import findings
    from .clean import after_check, clean, default_rules, format_text, to_json
    known = findings.rules()
    rules = [r.strip() for r in a.rules.split(",") if r.strip()] if a.rules else default_rules()
    unknown = [r for r in rules if r not in known]
    if unknown:
        print(f"unknown rule(s): {', '.join(unknown)} (known: {', '.join(known)})", file=sys.stderr)
        return 2
    out = a.output
    if not a.dry_run and not out:
        out = str(Path(a.input).with_name(Path(a.input).stem + " (cleaned).dorico"))
    changes = clean(a.input, None if a.dry_run else out, rules, dry_run=a.dry_run)
    if a.json:
        Path(a.json).write_text(to_json(changes, a.input))
        print(f"wrote {a.json}")
    print(format_text(changes, None if a.all else 12))
    if not a.dry_run:
        print(f"wrote {out}")
        left = after_check(out, rules)
        if left:
            print(f"note: {len(left)} could-link / duplicate finding(s) remain (see `f2d review`)")
    return 0


def cmd_ir(a) -> int:
    from . import ir
    sys.stdout.write(ir.to_json(_read(a.input, a.reader)) + "\n")
    return 0


def cmd_enigma(a) -> int:
    from .finale.musx import enigma_xml
    sys.stdout.write(enigma_xml(a.input))
    return 0


def cmd_dump(a) -> int:
    from doricokit import container
    from doricokit import format as dtn
    sys.stdout.write(dtn.to_xml(container.open_score(a.input), with_marker=False))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="f2d", description="Convert Finale scores to Dorico projects.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("convert", help="convert a .mus/.musx (or IR .json) to .dorico")
    c.add_argument("input")
    c.add_argument("-o", "--output")
    c.add_argument("--dorico-dir", help="Dorico install folder (default: auto-detect)")
    c.add_argument("--force-durations", choices=["ties", "all", "none"], default="ties")
    c.add_argument("--seed", help="a Dorico project to borrow library/options from")
    c.add_argument("--library", choices=["factory", "seed", "instruments", "none"], default="factory",
                   help="project library (default: a new project's, built from your Dorico install)")
    c.add_argument("--options-from-seed", action="store_true")
    c.add_argument("--playback-from-seed", action="store_true")
    c.add_argument("--dtn", action="store_true", help="write score.dtn (binary) instead of score.xml")
    c.add_argument("--no-parts", action="store_true")
    c.add_argument("--reader", choices=["auto", "musxdom", "bootstrap"], default="auto",
                   help="Finale reader (default: musxdom if f2d-extract is built)")
    c.add_argument("--report", action="store_true",
                   help="also write <output>.f2d-report.json (converter notes; read by `review`)")
    c.add_argument("--no-explode", action="store_true",
                   help="keep shared staves (e.g. Horns 1+3 in layers) as one player")
    c.add_argument("--no-doublings", action="store_true",
                   help="keep doubling staves (e.g. 'Piccolo (Flute 3)' with 'To Flute' texts) as one instrument")
    c.add_argument("--single-line", choices=["a2", "solo1"], default="a2",
                   help="who plays an unmarked single line on a shared staff before any a2/1./2. marking")
    c.set_defaults(fn=cmd_convert)
    r = sub.add_parser("review", help="list places in a .dorico project worth a look (changes nothing)")
    r.add_argument("input")
    r.add_argument("--json", help="also write the findings as JSON")
    r.add_argument("--all", action="store_true", help="list every finding (default: 12 per check)")
    r.set_defaults(fn=cmd_review)
    k = sub.add_parser("clean", help="fix what the reviewer reports, in a copy of a .dorico project")
    k.add_argument("input")
    k.add_argument("-o", "--output", help="cleaned project (default: '<input> (cleaned).dorico'; never the input)")
    k.add_argument("--rules", help="comma-separated rules (default: dedupe,link)")
    k.add_argument("--dry-run", action="store_true", help="list the changes, write nothing")
    k.add_argument("--json", help="also write the changes as JSON")
    k.add_argument("--all", action="store_true", help="list every change (default: 12 per rule)")
    k.set_defaults(fn=cmd_clean)
    for name, fn in (("ir", cmd_ir), ("enigma", cmd_enigma), ("dump", cmd_dump)):
        p = sub.add_parser(name)
        p.add_argument("input")
        if name == "ir":
            p.add_argument("--reader", choices=["auto", "musxdom", "bootstrap"], default="auto")
        p.set_defaults(fn=fn)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
