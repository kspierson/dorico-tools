"""Read factory data from the user's own Dorico installation.

The converter never ships Steinberg data. Instrument definitions, instrument names
and other factory content are read at run time from the Dorico install folder
(e.g. C:\\Program Files\\Steinberg\\Dorico5), which also keeps the output matched
to the Dorico version the user actually has.
"""
from __future__ import annotations

import difflib
import os
import re
import sys
import xml.etree.ElementTree as ET
from functools import cached_property
from pathlib import Path

from doricokit import format as dtn

from .. import keys

CANDIDATE_DIRS = [
    "/mnt/c/Program Files/Steinberg/Dorico6",
    "/mnt/c/Program Files/Steinberg/Dorico5",
    "/mnt/c/Program Files/Steinberg/Dorico4",
    r"C:\Program Files\Steinberg\Dorico6",
    r"C:\Program Files\Steinberg\Dorico5",
    r"C:\Program Files\Steinberg\Dorico4",
    "/Applications/Dorico 6.app/Contents/Resources",
    "/Applications/Dorico 5.app/Contents/Resources",
]


def find_dorico_dir(override: str | None = None) -> Path:
    for c in [override, os.environ.get("F2D_DORICO_DIR"), *CANDIDATE_DIRS]:
        if c and (Path(c) / "instruments.xml").is_file():
            return Path(c)
    raise FileNotFoundError(
        "Could not find a Dorico installation (looked for instruments.xml). "
        "Pass --dorico-dir or set F2D_DORICO_DIR.")


def norm_sound(s: str | None) -> str:
    """Normalise a MusicXML sound ID so 'wind.reed.clarinet.b-flat' == 'windReedClarinetBflat'."""
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _load_tree(path: Path) -> dtn.Node:
    return dtn.from_xml(path.read_bytes()).root


class DoricoInstall:
    def __init__(self, path: str | Path | None = None):
        self.dir = find_dorico_dir(str(path) if path else None)

    @property
    def version_folder(self) -> str:
        return self.dir.name

    # --- instruments ------------------------------------------------------
    @cached_property
    def instruments(self) -> dict[str, dtn.Node]:
        root = _load_tree(self.dir / "instruments.xml")
        ents = root.find("instruments/entities")
        return {e.text("entityID"): e for e in ents.children or []}

    @cached_property
    def instrument_names(self) -> dict[str, dtn.Node]:
        """nameID -> InstrumentNameEntityDefinition (English)."""
        p = self.dir / "l10n" / "instrumentnames_en.xml"
        root = _load_tree(p)
        ents = root.find("instrumentNames/entities")
        return {e.text("entityID"): e for e in ents.children or []}

    @cached_property
    def by_sound(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for eid, e in self.instruments.items():
            out.setdefault(norm_sound(e.text("musicXMLSoundID")), []).append(eid)
        return out

    def name_data(self, entity_id: str) -> dict[str, str]:
        e = self.instruments[entity_id]
        n = self.instrument_names.get(e.text("nameID"))
        data = n.find("data") if n is not None else None
        keys = ["uiName", "singularFullName", "singularShortName", "pluralFullName",
                "pluralShortName", "gender", "language"]
        if data is None:
            nm = e.text("name")
            return {"uiName": nm, "singularFullName": nm, "singularShortName": nm,
                    "pluralFullName": nm, "pluralShortName": nm, "gender": "kNeutral",
                    "language": "kEnglish"}
        return {k: data.text(k) for k in keys}

    def transposition(self, entity_id: str) -> tuple[int, int]:
        """(diatonic, chromatic) with written = concert + this, from the factory definition."""
        p = self.instruments[entity_id].find("pitchedInstrumentData")
        if p is None:
            return (0, 0)
        return (int(p.text("transposedDiatonicTransposition") or 0),
                int(p.text("transposedChromaticTransposition") or 0))

    def _names(self, eid: str) -> list[str]:
        nd = self.name_data(eid)
        return [nd["uiName"], nd["singularFullName"], self.instruments[eid].text("name")]

    def resolve(self, sound_id: str | None, name: str, num_staves: int | None = None,
                transposition: tuple[int, int] | None = None, no_key: bool = False,
                clef: str | None = None, key: str | None = None) -> tuple[str, str]:
        """Pick a Dorico instrument entity for a source instrument.

        Candidates come from the MusicXML sound ID when there is one, otherwise from all
        instruments. Ranking: transposition and stave count must match first, then name
        similarity (to 0.1), then plain entities over aliases/variants.
        Returns (entity_id, how) where `how` explains the match for the report.
        """
        fam = keys.family(name)
        key = key or (keys.find_key(name) if fam else None)
        base = _clean_name(keys.strip_key(name) if key else name)
        if fam and base in _FAMILY_ABBREV:
            base = fam
        # no transposition known: the family's standard pitch unless a key is stated
        want = key or (keys.standard_key(fam) if fam and transposition is None else None)
        if _PLACEHOLDER.match(base):  # "Staff 1", "Blank Staff"...: says nothing about the instrument
            base = ""
        by_sound = self.by_sound.get(norm_sound(sound_id), []) if sound_id else []
        alias = ALIAS_INDEX.get(base) or ALIAS_INDEX.get(base.split(" / ")[0].strip())
        if not by_sound and alias in self.instruments and \
                (num_staves is None or int(self.instruments[alias].text("numStaves") or 1) == num_staves):
            return alias, f"standard name '{base}'"
        pool = by_sound or list(self.instruments)

        def sim(eid: str) -> float:
            if not base:
                return 0.0
            return max(difflib.SequenceMatcher(None, base, _clean_name(n)).ratio()
                       for n in self._names(eid) if n)

        sims = {eid: sim(eid) for eid in pool}

        def rank(eid: str) -> tuple:
            e = self.instruments[eid]
            return (transposition is not None and self.transposition(eid) != tuple(transposition),
                    num_staves is not None and int(e.text("numStaves") or 1) != num_staves,
                    -(round(sims[eid], 1) if sims[eid] >= 0.8 or not by_sound else 0),
                    want is not None and want not in eid.split("."),
                    (".nokeysig" in eid) != no_key,
                    ".alias." in eid,
                    bool(e.text("parentEntityID")),
                    -sims[eid], len(eid))

        best = min(pool, key=rank)
        if by_sound:
            return best, f"sound ID {sound_id}"
        if sims[best] >= 0.6:
            extra = f", in {key}" if key else (f", standard {want} (no transposition in source)"
                                                if want and want in best.split(".") else "")
            return best, f"name match {sims[best]:.2f}{extra}"
        if (num_staves or 1) > 1:
            fallback = "instrument.generic.grandstaff"
        elif clef and "percussion" in clef:
            fallback = "instrument.generic.singlelinepercussion"
        elif clef and ("bass" in clef or "tenor" in clef or "alto" in clef):
            fallback = "instrument.generic.bassstaff"
        else:
            fallback = "instrument.generic.treblestaff"
        if not base:
            return fallback, "generic staff (no instrument name)"
        return fallback, f"generic staff (best name match {best} {sims[best]:.2f})"


# Standard orchestral names and abbreviations (English / Italian / German), checked before fuzzy
# matching: "Cello" must not land on "Cowbells", nor an orchestral "Bass" on a bass guitar.
# Names are compared after _clean_name (lower case, no dots/brackets, player numbers dropped).
# Instruments whose transposition is a choice (clarinet, horn, trumpet) are left to the ranking.
ALIASES = {
    "instrument.wind.piccolo": ["picc", "piccolo", "ottavino", "kl fl"],
    "instrument.wind.flute": ["fl", "fls", "flute", "flutes", "flauto", "flauti"],
    "instrument.wind.oboe": ["ob", "obs", "oboe", "oboes", "oboi"],
    "instrument.wind.coranglais.alias.english-horn": ["eh", "e h", "e hn", "eng hn", "english horn",
                                                      "cor anglais", "corno inglese"],
    "instrument.wind.bassoon": ["bsn", "bsns", "bn", "bassoon", "bassoons", "fg", "fag", "fagotto", "fagotti"],
    "instrument.wind.contrabassoon": ["cfg", "cbsn", "cbn", "c bn", "c bsn", "contra bsn", "contrabassoon",
                                      "contrafagotto", "kfg", "kontrafagott"],
    "instrument.brass.trombone": ["tbn", "tbns", "trb", "trombone", "trombones", "tromboni", "pos", "posaune"],
    "instrument.brass.trombone.bass": ["b tbn", "bass tbn", "btbn", "bass trombone"],
    "instrument.brass.tuba": ["tuba", "tba"],
    "instrument.pitchedpercussion.timpani": ["timp", "timps", "timpani", "pk", "pauken"],
    "instrument.pitchedpercussion.harp": ["hp", "harp", "harps", "arpa", "harfe"],
    "instrument.keyboard.piano": ["pno", "pf", "piano", "pianoforte", "klavier"],
    "instrument.keyboard.celesta": ["cel", "cel", "celesta", "celeste"],
    "instrument.pitchedpercussion.glockenspiel": ["glock", "glockenspiel", "orch bells"],
    "instrument.pitchedpercussion.xylophone": ["xyl", "xylo", "xylophone"],
    "instrument.pitchedpercussion.vibraphone.3oct": ["vib", "vibes", "vibraphone"],
    "instrument.pitchedpercussion.bells.tubular": ["chimes", "tubular bells", "campane", "glocken"],
    "instrument.orchestral.unpitched.bass.drum": ["bd", "b d", "bass drum", "gc", "g c", "gran cassa",
                                                  "grosse trommel"],
    "instrument.orchestral.unpitched.snare.drum": ["sd", "s d", "snare", "snare drum", "tamburo",
                                                   "kleine trommel"],
    "instrument.orchestral.unpitched.suspended.cymbal": ["sus cym", "susp cym", "sus cymbal",
                                                         "suspended cymbal", "lg sus cym", "sm sus cym"],
    "instrument.orchestral.unpitched.clash.cymbals": ["piatti", "cymbals", "crash cymbals", "clash cymbals",
                                                      "becken"],
    "instrument.orchestral.unpitched.tamtam": ["tam", "tam tam", "tamtam", "tam-tam"],
    "instrument.orchestral.unpitched.triangle": ["tri", "trgl", "triangle", "triangolo"],
    "instrument.strings.violin": ["vln", "vlns", "vn", "vl", "violin", "violins", "violino", "violini",
                                  "violin i", "violin ii", "vln i", "vln ii", "vn i", "vn ii"],
    "instrument.strings.viola": ["vla", "vlas", "va", "viola", "violas", "viole", "bratsche"],
    "instrument.strings.violoncello": ["vc", "vcs", "vcl", "vlc", "cello", "cellos", "celli", "violoncello",
                                       "violoncelli"],
    "instrument.strings.contrabass": ["cb", "cbs", "db", "kb", "bass", "basses", "bassi", "double bass",
                                      "double basses", "contrabass", "contrabasses", "kontrabass"],
}
_FAMILY_ABBREV = {"tpt", "tpts", "trp", "cl", "cls", "clar", "hn", "hns", "cnt"}
ALIAS_INDEX = {n: eid for eid, names in ALIASES.items() for n in names}


_PLACEHOLDER = re.compile(r"^(staff|blank staff|grand staff|unknown instrument|untitled|new staff)?( \d+)?$")


def _clean_name(name: str) -> str:
    """'Clarinet in B\u266d 1' -> 'clarinet in bb'; drops player numbers and punctuation."""
    n = name.replace("\u266d", "b").replace("\u266f", "#").replace("\u266e", "")
    n = n.split("\n")[0] if "\n" in n.strip() and not re.fullmatch(r"[\d\s,&]+", n.split("\n")[1]) else n
    n = re.sub(r"(\s+\d+([\s,&]+\d+)*)$", "", n.strip())
    n = re.sub(r"[.()]", "", n)
    return re.sub(r"\s+", " ", n).strip().lower()


if __name__ == "__main__":
    inst = DoricoInstall(sys.argv[1] if len(sys.argv) > 1 else None)
    print(inst.dir, len(inst.instruments), "instruments")
    for q in sys.argv[2:]:
        print(q, inst.resolve(q, q))
