# finale2dorico

Convert Finale scores straight to Dorico projects, without going through MusicXML.

- Input: `.musx` (Finale 2014 and later) and legacy `.mus` (Finale 1.0-2012, via the
  open-source finale-mus-reader).
- Output: a `.dorico` project with the notation from the Finale file, Dorico's own
  instruments (from your installed Dorico) and Dorico's default playback.

**Status: early prototype.** The reader is verified against 59 `.musx` test files and 516
legacy `.mus` test documents; the Dorico files it writes have not yet been opened in Dorico.
See [docs/STATUS.md](docs/STATUS.md).

## Use

```sh
python3 -m f2d convert Score.musx                 # writes Score.dorico next to it
python3 -m f2d convert Old.mus                    # legacy Finale file
python3 -m f2d convert Score.musx -o Out.dorico --force-durations all
python3 -m f2d ir Score.musx                      # print the intermediate model as JSON
```

Requires Python 3.12+ and the shared engine's `doricokit` package (the Dorico file format,
Rust inside; built once with `. engine/scripts/dev-env.sh && uv sync` at the repo root, see
[engine/docs/DEV_SETUP.md](../engine/docs/DEV_SETUP.md)), Dorico installed on the same machine
(found automatically; or `--dorico-dir "C:\Program Files\Steinberg\Dorico5"`), and the
small C++ extractor in [extract/](extract/) built once (instructions in
[docs/STATUS.md](docs/STATUS.md)). Without it, `.musx` files are read by a simpler Python
reader (`--reader bootstrap`) and `.mus` files can't be read.

Options: `--force-durations ties|all|none` (how strictly to keep Finale's notated
durations), `--seed X.dorico --library seed --options-from-seed` (borrow settings from an
existing project), `--dtn` (binary score), `--no-parts`.

## Docs

- [docs/DESIGN.md](docs/DESIGN.md): architecture and decisions
- [docs/RESEARCH.md](docs/RESEARCH.md): what we know about both file formats, and how
- [docs/STATUS.md](docs/STATUS.md): current state, gaps, next steps, session log
- [experiments/README.md](experiments/README.md): Dorico test rounds (current: round6) and their results

## Credits

Finale format knowledge comes from the MIT-licensed [openmusx](https://github.com/openmusx)
projects by Robert G. Patterson (musxdom, denigma, finale-mus-reader, smufl-mapping).
Not affiliated with MakeMusic or Steinberg. No Steinberg data is included: Dorico
definitions are read from your own installation at run time.
