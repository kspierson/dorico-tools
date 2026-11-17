"""doricokit: the shared Dorico engine for the Python tools (Project S, PLANNED_WORK.md §2).

The work is done in Rust (engine/crates); this package is the temporary bridge to it and goes
away when the last Python tool is ported (S14).

    from doricokit import format as dtn     # DTN / XML codec (score tree)
    from doricokit import container          # .dorico zip
    from doricokit import paths              # Dorico install, user data, WSL <-> Windows, corpora
    from doricokit import model, view        # read model; the checking view over it
    from doricokit import edit               # edit an existing project (load -> change -> save)
    from doricokit import findings           # one report format + registry of checks and rules
    from doricokit import review, clean      # the reviewer (checks) and cleaner (rules)
    from doricokit import midi               # Standard MIDI Files: read, write, bars
    from doricokit import harp, gliss        # harp pedals/strings; harp gliss playback (ad lib)

Build: `uv sync` at the repo root compiles the Rust extension (needs `. engine/scripts/dev-env.sh`).
After changing Rust code: `uv sync --reinstall-package doricokit`. See engine/docs/DEV_SETUP.md.
"""
__version__ = "0.1.0"
