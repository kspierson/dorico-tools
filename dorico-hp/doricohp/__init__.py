"""Human Playback for Dorico: shape playback of .dorico projects from their notation."""

# Shared engine (Project S): the DTN codec and .dorico container come from `doricokit`
# (engine/python, Rust inside). `uv run ...` from the repo root has it installed. Plain
# `python3 -m doricohp...` also works once `uv sync` has built it: fall back to the
# in-repo package (the compiled extension sits next to it after an editable build).
try:
    import doricokit  # noqa: F401
except ImportError:  # pragma: no cover - depends on how the tool is started
    import sys
    from pathlib import Path

    _kit = Path(__file__).resolve().parents[2] / "engine" / "python"
    if (_kit / "doricokit").is_dir():
        sys.path.insert(0, str(_kit))
    try:
        import doricokit  # noqa: F401
    except ImportError as e:
        raise ImportError("doricokit is not built yet: run `uv sync` at the repo root "
                          "(after `. engine/scripts/dev-env.sh`); see engine/docs/DEV_SETUP.md") from e
