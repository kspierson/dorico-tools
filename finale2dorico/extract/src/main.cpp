// f2d-extract: read a Finale document with musxdom (EnigmaXML) or finale-mus-reader (.mus)
// and print the "facts" JSON that f2d/finale/facts.py turns into finale2dorico's Score IR.
//
//   f2d-extract FILE.mus            legacy Finale 1.0-2012 file
//   f2d-extract FILE.enigmaxml      EnigmaXML (the Python side unpacks .musx into this)
//
// The facts are what musxdom calculates (concert pitches, positions, tuplets, ties,
// instruments, names) plus raw codes (glyphs, clef shapes, expression text) that the Python
// side interprets with the same tables as the bootstrap reader. All times are in crotchets,
// written as "n/d" strings. See docs/DESIGN.md.
//
// Copyright notice: uses musxdom and finale-mus-reader (MIT, Robert G. Patterson).

#include <algorithm>
#include <cstdio>
#include <fstream>
#include <iostream>
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <vector>

#include "finale_mus_reader/reader.h"
#include "musx/musx.h"
#include "musx/factory/FactoryBase.h"
#include "musx/xml/PugiXmlImpl.h"
#include "smufl_mapping.h"

using namespace musx::dom;
using musx::util::Fraction;

// musxdom's xml-name tables for these enums live in its factory sources; declaring the
// specializations here lets us turn enum values back into Finale's own names.
namespace musx::factory {
template <> const XmlEnumMappingElement<others::SmartShape::ShapeType> XmlEnumMapping<others::SmartShape::ShapeType>::mapping;
template <> const XmlEnumMappingElement<others::MarkingCategory::CategoryType> XmlEnumMapping<others::MarkingCategory::CategoryType>::mapping;
template <> const XmlEnumMappingElement<others::PlaybackType> XmlEnumMapping<others::PlaybackType>::mapping;
} // namespace musx::factory

template <typename E>
static std::string enumName(E value)
{
    for (const auto& [name, v] : musx::factory::XmlEnumMapping<E>::mapping) {
        if (v == value) return std::string(name);
    }
    return std::to_string(static_cast<int>(value));
}

// ------------------------------------------------------------------ minimal JSON writer
class Json
{
public:
    explicit Json(std::ostream& out) : m_out(out) {}

    Json& beginObject() { value(); m_out << '{'; m_first.push_back(true); return *this; }
    Json& endObject() { m_out << '}'; m_first.pop_back(); return *this; }
    Json& beginArray() { value(); m_out << '['; m_first.push_back(true); return *this; }
    Json& endArray() { m_out << ']'; m_first.pop_back(); return *this; }
    Json& key(const char* k)
    {
        comma();
        str(k);
        m_out << ':';
        m_afterKey = true;
        return *this;
    }
    Json& v(const std::string& s) { value(); str(s); return *this; }
    Json& v(const char* s) { value(); str(s); return *this; }
    Json& v(bool b) { value(); m_out << (b ? "true" : "false"); return *this; }
    Json& v(int i) { value(); m_out << i; return *this; }
    Json& v(long i) { value(); m_out << i; return *this; }
    Json& v(unsigned i) { value(); m_out << i; return *this; }
    Json& v(size_t i) { value(); m_out << i; return *this; }
    Json& v(Fraction f) { value(); str(frac(f)); return *this; }
    Json& v(double d) { value(); m_out << d; return *this; }
    Json& null() { value(); m_out << "null"; return *this; }
    Json& raw(const std::string& text) { value(); m_out << text; return *this; }

    template <typename T> Json& kv(const char* k, const T& x) { key(k); return v(x); }

    // crotchets from a musxdom whole-note fraction
    static std::string frac(Fraction wholes)
    {
        Fraction q = wholes * Fraction(4);
        if (q.denominator() == 1) return std::to_string(q.numerator());
        return std::to_string(q.numerator()) + "/" + std::to_string(q.denominator());
    }

private:
    void comma()
    {
        if (!m_first.empty()) {
            if (!m_first.back()) m_out << ',';
            m_first.back() = false;
        }
    }
    void value()
    {
        if (m_afterKey) { m_afterKey = false; return; }
        comma();
    }
    void str(const std::string& s)
    {
        m_out << '"';
        for (unsigned char c : s) {
            switch (c) {
            case '"': m_out << "\\\""; break;
            case '\\': m_out << "\\\\"; break;
            case '\n': m_out << "\\n"; break;
            case '\r': m_out << "\\r"; break;
            case '\t': m_out << "\\t"; break;
            default:
                if (c < 0x20) {
                    char buf[8];
                    std::snprintf(buf, sizeof buf, "\\u%04x", c);
                    m_out << buf;
                } else {
                    m_out << c;
                }
            }
        }
        m_out << '"';
    }

    std::ostream& m_out;
    std::vector<bool> m_first;
    bool m_afterKey{};
};

// ------------------------------------------------------------------ helpers
static const int STEP_SEMI[7] = {0, 2, 4, 5, 7, 9, 11};
static const char* STEP_NAMES = "CDEFGAB";

static std::string fileInfo(const DocumentPtr& doc, texts::FileInfoText::TextType type)
{
    auto t = doc->getTexts()->get<texts::FileInfoText>(Cmper(type));
    return t ? musx::util::EnigmaString::trimTags(t->text) : std::string();
}

// UTF-8 -> codepoints
static std::vector<char32_t> codepoints(const std::string& s)
{
    std::vector<char32_t> out;
    for (size_t i = 0; i < s.size();) {
        unsigned char c = s[i];
        char32_t cp = c;
        int extra = c >= 0xF0 ? 3 : c >= 0xE0 ? 2 : c >= 0xC0 ? 1 : 0;
        if (extra) cp = c & (0x3F >> extra);
        for (int k = 1; k <= extra && i + k < s.size(); ++k) cp = (cp << 6) | (s[i + k] & 0x3F);
        out.push_back(cp);
        i += 1 + extra;
    }
    return out;
}

// SMuFL glyph name of a character in a (legacy or SMuFL) music font, or "".
static std::string glyphName(const std::string& font, char32_t cp, bool smufl)
{
    if (const auto* name = smufl_mapping::getGlyphNameForFont(font, cp, smufl)) return std::string(*name);
    return {};
}

struct TextChunk
{
    std::string text;
    bool music{};   // a music font (default music font or SMuFL)
    bool smufl{};
    std::string font;
};

static std::vector<TextChunk> textChunks(const musx::util::EnigmaParsingContext& ctx)
{
    std::vector<TextChunk> chunks;
    ctx.parseEnigmaText(
        [&](const std::string& text, const musx::util::EnigmaStyles& styles) {
            TextChunk c;
            c.text = text;
            if (styles.font) {
                try {
                    c.smufl = styles.font->calcIsSMuFL();
                    c.font = styles.font->getName();
                    c.music = c.smufl || styles.font->calcIsDefaultMusic() || styles.font->calcIsSymbolFont();
                } catch (...) {
                }
            }
            chunks.push_back(c);
            return true;
        },
        [](const std::vector<std::string>&) -> std::optional<std::string> { return std::nullopt; });
    return chunks;
}

static void writeChunks(Json& j, const std::vector<TextChunk>& chunks)
{
    j.beginArray();
    for (const auto& c : chunks) {
        j.beginObject().kv("text", c.text).kv("music", c.music).kv("smufl", c.smufl).kv("font", c.font);
        if (c.music) {
            j.key("glyphs").beginArray();
            for (char32_t cp : codepoints(c.text)) j.v(glyphName(c.font, cp, c.smufl));
            j.endArray();
        }
        j.endObject();
    }
    j.endArray();
}

static std::string clefTypeName(music_theory::ClefType t)
{
    switch (t) {
    case music_theory::ClefType::G: return "G";
    case music_theory::ClefType::C: return "C";
    case music_theory::ClefType::F: return "F";
    case music_theory::ClefType::Percussion1: return "perc1";
    case music_theory::ClefType::Percussion2: return "perc2";
    case music_theory::ClefType::Tab: return "tab";
    case music_theory::ClefType::TabSerif: return "tab";
    default: return "unknown";
    }
}

// ------------------------------------------------------------------ extraction
class Extractor
{
public:
    Extractor(DocumentPtr doc, Json& j) : m_doc(std::move(doc)), m_j(j) {}

    void run(const std::string& source, const std::string& kind)
    {
        m_j.beginObject();
        m_j.kv("format", "f2d-facts").kv("version", 1).kv("source", source).kv("kind", kind);
        info();
        clefs();
        measures();
        instruments();
        staves();
        expressions();
        smartShapes();
        repeats();
        chords();
        layout();
        pageTexts();
        m_j.key("warnings").beginArray();
        for (const auto& w : m_warnings) m_j.v(w);
        m_j.endArray();
        m_j.endObject();
    }

private:
    // Score page layout: page format defaults, pages, and each page-view system with its staves
    // (a staff missing from every system is not printed in the score). Lengths in Evpu
    // (288 per inch; a staff space is 24 Evpu at 100%).
    static double ratio(Fraction f) { return double(f.numerator()) / double(f.denominator()); }

    /// Score page text: which pages, alignment, the text (inserts expanded) and the inserts used
    /// (^title, ^composer ...), so the converter can tell what Finale actually prints.
    void pageTexts()
    {
        m_j.key("page_texts").beginArray();
        for (const auto& pt : m_doc->getOthers()->getArray<others::PageTextAssign>(SCORE_PARTID)) {
            std::vector<TextChunk> chunks;
            std::vector<std::string> inserts;
            int size = 0;
            std::optional<PageCmper> start, end;
            try {
                start = pt->calcStartPageNumber(SCORE_PARTID);
                end = pt->calcEndPageNumber(SCORE_PARTID);
                auto ctx = pt->getRawTextCtx(SCORE_PARTID, start);
                ctx.parseEnigmaText(
                    [&](const std::string& text, const musx::util::EnigmaStyles& styles, const musx::util::EnigmaTextInsert* ins) {
                        TextChunk c;
                        c.text = text;
                        if (styles.font) {
                            try {
                                c.smufl = styles.font->calcIsSMuFL();
                                c.font = styles.font->getName();
                                c.music = c.smufl || styles.font->calcIsDefaultMusic() || styles.font->calcIsSymbolFont();
                                if (!text.empty()) size = std::max(size, int(styles.font->fontSize));
                            } catch (...) {
                            }
                        }
                        if (ins && (inserts.empty() || inserts.back() != ins->command)) inserts.push_back(ins->command);
                        chunks.push_back(c);
                        return true;
                    },
                    [](const std::vector<std::string>&) -> std::optional<std::string> { return std::nullopt; });
            } catch (...) {
                continue;
            }
            auto align = [](auto a) {
                return a == others::PageTextAssign::HorizontalAlignment::Center ? "center"
                    : a == others::PageTextAssign::HorizontalAlignment::Right ? "right" : "left";
            };
            const auto v = pt->vPos;
            m_j.beginObject()
                .kv("start_page", long(start.value_or(0))).kv("end_page", long(end.value_or(0)))
                .kv("multi", pt->isMultiPage()).kv("hidden", pt->hidden)
                .kv("h_align", align(pt->hPosLp))
                .kv("v_align", v == others::PageTextAssign::VerticalAlignment::Center ? "center"
                    : v == others::PageTextAssign::VerticalAlignment::Bottom ? "bottom" : "top")
                .kv("x", long(pt->xDisp)).kv("y", long(pt->yDisp)).kv("size", size);
            m_j.key("inserts").beginArray();
            for (const auto& i : inserts) m_j.v(i);
            m_j.endArray();
            m_j.key("chunks");
            writeChunks(m_j, chunks);
            m_j.endObject();
        }
        m_j.endArray();
    }

    void layout()
    {
        m_j.key("layout").beginObject();
        try {  // "Display in Concert Pitch" for the score (PartGlobals cmper 65534)
            if (auto pg = m_doc->getOthers()->get<others::PartGlobals>(SCORE_PARTID, 65534))
                m_j.kv("concert_pitch", !pg->showTransposed);
        } catch (...) {}
        try {
            if (auto pf = m_doc->getOptions()->get<options::PageFormatOptions>()) {
                if (auto f = pf->pageFormatParts) {
                    m_j.key("part_page_format").beginObject()
                        .kv("width", f->pageWidth).kv("height", f->pageHeight)
                        .kv("scaling", ratio(f->calcCombinedSystemScaling()))
                        .endObject();
                }
                if (auto f = pf->pageFormatScore) {
                    m_j.key("page_format").beginObject()
                        .kv("width", f->pageWidth).kv("height", f->pageHeight)
                        .kv("page_percent", f->pagePercent).kv("sys_percent", f->sysPercent)
                        .kv("raw_staff_height", f->rawStaffHeight)
                        .kv("scaling", ratio(f->calcCombinedSystemScaling()))
                        .kv("margin_top", f->leftPageMarginTop).kv("margin_left", f->leftPageMarginLeft)
                        .kv("margin_bottom", f->leftPageMarginBottom).kv("margin_right", f->leftPageMarginRight)
                        .kv("sys_distance", f->sysDistanceBetween)
                        .endObject();
                }
            }
            m_j.key("pages").beginArray();
            for (const auto& pg : m_doc->getOthers()->getArray<others::Page>(SCORE_PARTID)) {
                m_j.beginObject().kv("id", unsigned(pg->getCmper())).kv("width", pg->width)
                    .kv("height", pg->height).kv("percent", pg->percent)
                    .kv("first_system", int(pg->firstSystemId))
                    .kv("margin_top", pg->margTop).kv("margin_left", pg->margLeft)
                    .kv("margin_bottom", pg->margBottom).kv("margin_right", pg->margRight)
                    .endObject();
            }
            m_j.endArray();
            m_j.key("systems").beginArray();
            for (const auto& sys : m_doc->getOthers()->getArray<others::StaffSystem>(SCORE_PARTID)) {
                m_j.beginObject().kv("id", unsigned(sys->getCmper())).kv("page", unsigned(sys->pageId))
                    .kv("start", unsigned(sys->startMeas)).kv("end", unsigned(sys->endMeas))
                    .kv("percent", sys->ssysPercent).kv("staff_height", sys->staffHeight)
                    .kv("scaling", ratio(sys->calcEffectiveScaling()))
                    .kv("top", sys->top).kv("left", sys->left).kv("right", sys->right)
                    .kv("bottom", sys->bottom).kv("distance_to_prev", sys->distanceToPrev);
                m_j.key("staves").beginArray();
                for (const auto& su : m_doc->getOthers()->getArray<others::StaffUsed>(SCORE_PARTID, sys->getCmper())) {
                    m_j.beginObject().kv("id", unsigned(su->staffId)).kv("top", su->distFromTop)
                        .kv("scaling", ratio(sys->calcStaffScaling(su->staffId))).endObject();
                }
                m_j.endArray();
                m_j.endObject();
            }
            m_j.endArray();
        } catch (const std::exception& ex) {
            m_warnings.push_back(std::string("layout: ") + ex.what());
        }
        m_j.endObject();
    }

    void info()
    {
        using TT = texts::FileInfoText::TextType;
        m_j.key("info").beginObject()
            .kv("title", fileInfo(m_doc, TT::Title))
            .kv("subtitle", fileInfo(m_doc, TT::Subtitle))
            .kv("composer", fileInfo(m_doc, TT::Composer))
            .kv("arranger", fileInfo(m_doc, TT::Arranger))
            .kv("lyricist", fileInfo(m_doc, TT::Lyricist))
            .kv("copyright", fileInfo(m_doc, TT::Copyright))
            .endObject();
    }

    void clefs()
    {
        m_j.key("clefs").beginArray();
        auto opts = m_doc->getOptions()->get<options::ClefOptions>();
        if (opts) {
            for (size_t i = 0; i < opts->clefDefs.size(); ++i) {
                const auto& def = opts->clefDefs[i];
                auto [type, octave] = def->calcInfo();
                m_j.beginObject()
                    .kv("index", i)
                    .kv("type", clefTypeName(type))
                    .kv("octave", octave)
                    .kv("middle_c", def->middleCPos)
                    .kv("char", unsigned(def->clefChar))
                    .endObject();
            }
        }
        m_j.endArray();
    }

    void measures()
    {
        m_j.key("measures").beginArray();
        Fraction pos{};
        m_measures = m_doc->getOthers()->getArray<others::Measure>(SCORE_PARTID);
        for (const auto& m : m_measures) {
            const auto id = m->getCmper();
            m_measStart[id] = pos;
            const Fraction dur = m->calcDuration();
            auto ts = m->createTimeSignature();
            auto dts = m->createDisplayTimeSignature();
            auto key = m->createKeySignature();
            m_j.beginObject().kv("id", unsigned(id)).kv("pos", pos).kv("duration", dur);
            m_j.key("time");
            timeSig(ts);
            m_j.key("display_time");
            timeSig(dts);
            m_j.kv("display_duration", dts ? dts->calcTotalDuration() : dur);
            m_j.kv("legacy_pickup_spacer", m->calcMinLegacyPickupSpacer());
            m_j.key("key").beginObject()
                .kv("fifths", key->getAlteration(KeySignature::KeyContext::Concert))
                .kv("mode", unsigned(key->getKeyMode()))
                .kv("linear", key->isLinear())
                .kv("keyless", key->keyless)
                .kv("hide_keysig_show_accis", key->hideKeySigShowAccis)
                .endObject();
            // barlines and repeat signs (Round 7 items)
            m_j.kv("barline", barlineName(m->barlineType)).kv("left_barline", barlineName(m->leftBarlineType))
                .kv("forward_repeat", m->forwardRepeatBar).kv("backward_repeat", m->backwardsRepeatBar);
            m_j.endObject();
            pos += dur;
        }
        m_j.endArray();
        m_j.kv("length", pos);
    }

    static const char* barlineName(others::Measure::BarlineType t)
    {
        using B = others::Measure::BarlineType;
        switch (t) {
        case B::None: return "none";
        case B::OptionsDefault: return "default";
        case B::Normal: return "normal";
        case B::Double: return "double";
        case B::Final: return "final";
        case B::Solid: return "solid";
        case B::Dashed: return "dashed";
        case B::Tick: return "tick";
        case B::Custom: return "custom";
        }
        return "normal";
    }

    static const char* repeatAction(others::RepeatActionType a)
    {
        using A = others::RepeatActionType;
        switch (a) {
        case A::JumpAuto: return "auto";
        case A::JumpAbsolute: return "absolute";
        case A::JumpRelative: return "relative";
        case A::JumpToMark: return "to_mark";
        case A::Stop: return "stop";
        case A::NoJump: return "none";
        }
        return "auto";
    }

    // Repeat endings ("1.", "2.") and text repeats (segno, coda, D.S., To Coda, Fine)
    void repeats()
    {
        m_j.key("endings").beginArray();
        try {
            for (const auto& e : m_doc->getOthers()->getArray<others::RepeatEndingStart>(SCORE_PARTID)) {
                MeasCmper meas = e->getCmper();
                m_j.beginObject().kv("measure", unsigned(meas)).kv("pos", measStart(meas))
                    .kv("length", e->calcEndingLength()).kv("text", e->createEndingText())
                    .kv("open", e->calcIsOpen()).kv("hidden", e->hidden)
                    .kv("action", repeatAction(e->jumpAction));
                m_j.key("passes").beginArray();
                if (auto pl = m_doc->getOthers()->get<others::RepeatPassList>(SCORE_PARTID, meas)) {
                    for (int v : pl->values) m_j.v(v);
                }
                m_j.endArray();
                m_j.endObject();
            }
        } catch (const std::exception& ex) {
            m_warnings.push_back(std::string("repeat endings: ") + ex.what());
        }
        m_j.endArray();
        m_j.key("text_repeats").beginArray();
        try {
            for (const auto& m : m_measures) {
                if (!m->hasTextRepeat) continue;
                for (const auto& t : m_doc->getOthers()->getArray<others::TextRepeatAssign>(SCORE_PARTID, m->getCmper())) {
                    m_j.beginObject().kv("measure", unsigned(m->getCmper())).kv("pos", measStart(m->getCmper()))
                        .kv("def", unsigned(t->textRepeatId)).kv("hidden", t->hidden)
                        .kv("action", repeatAction(t->jumpAction)).kv("target", t->targetValue)
                        .kv("pass", t->passNumber).kv("horz", int(t->horzPos));
                    auto def = m_doc->getOthers()->get<others::TextRepeatDef>(SCORE_PARTID, t->textRepeatId);
                    auto txt = m_doc->getOthers()->get<others::TextRepeatText>(SCORE_PARTID, t->textRepeatId);
                    if (def) m_j.kv("justify", int(def->justification));
                    TextChunk c;
                    c.text = txt ? txt->text : "";
                    if (def && def->font) {
                        try {
                            c.smufl = def->font->calcIsSMuFL();
                            c.font = def->font->getName();
                            c.music = c.smufl || def->font->calcIsDefaultMusic() || def->font->calcIsSymbolFont();
                        } catch (...) {
                        }
                    }
                    m_j.key("chunks");
                    writeChunks(m_j, {c});
                    m_j.endObject();
                }
            }
        } catch (const std::exception& ex) {
            m_warnings.push_back(std::string("text repeats: ") + ex.what());
        }
        m_j.endArray();
    }

    void timeSig(const MusxInstance<TimeSignature>& ts)
    {
        if (!ts) { m_j.null(); return; }
        m_j.beginObject();
        std::string abbrev;
        try {
            if (ts->getAbbreviatedSymbol()) abbrev = ts->isCommonTime() ? "common" : ts->isCutTime() ? "cut" : "";
        } catch (...) {
        }
        m_j.kv("abbreviation", abbrev);
        m_j.key("components").beginArray();
        for (const auto& c : ts->components) {
            m_j.beginObject();
            m_j.key("counts").beginArray();
            for (auto x : c.counts) m_j.v(Fraction(x) / Fraction(4));  // written as plain numbers
            m_j.endArray();
            m_j.key("units").beginArray();
            for (auto u : c.units) m_j.v(Fraction::fromEdu(u));
            m_j.endArray();
            m_j.endObject();
        }
        m_j.endArray();
        m_j.endObject();
    }

    void instruments()
    {
        m_staffOrder.clear();
        for (const auto& su : m_doc->getScrollViewStaves(SCORE_PARTID)) {
            m_staffOrder.push_back(su->staffId);
        }
        const auto& instMap = m_doc->getInstruments();
        m_j.key("instruments").beginArray();
        std::set<StaffCmper> done;
        for (auto staffId : m_staffOrder) {
            if (done.count(staffId)) continue;
            const auto* info = instMap.getInstrumentForStaff(staffId);
            std::vector<StaffCmper> members = info ? info->getSequentialStaves() : std::vector<StaffCmper>{staffId};
            if (members.empty()) members = {staffId};
            for (auto s : members) done.insert(s);
            auto raw = m_doc->getOthers()->get<others::Staff>(SCORE_PARTID, members[0]);
            m_j.beginObject();
            m_j.key("staves").beginArray();
            for (auto s : members) m_j.v(unsigned(s));
            m_j.endArray();
            if (raw) {
                using AS = musx::util::EnigmaString::AccidentalStyle;
                // plain names (Dorico numbers duplicate players itself) and Finale's displayed,
                // auto-numbered ones
                auto plain = [](musx::util::EnigmaParsingContext ctx) {
                    ctx.affixText.clear();
                    return ctx.getText(true, AS::Unicode);
                };
                m_j.kv("name", plain(raw->getFullInstrumentNameCtx(SCORE_PARTID)))
                    .kv("short_name", plain(raw->getAbbreviatedInstrumentNameCtx(SCORE_PARTID)))
                    .kv("display_name", raw->getFullInstrumentName(AS::Unicode))
                    .kv("display_short_name", raw->getAbbreviatedInstrumentName(AS::Unicode))
                    .kv("staff_name", raw->getFullName(AS::Unicode))
                    .kv("uuid", raw->instUuid)
                    .kv("default_clef", unsigned(raw->defaultClef))
                    .kv("notation", int(raw->notationStyle));
                auto [diatonic, alteration] = raw->calcTranspositionInterval();
                m_j.key("transposition").beginArray().v(diatonic).v(alteration).endArray();
                std::string ttype = "none";
                if (raw->transposition) {
                    ttype = raw->transposition->keysig ? "keysig" : raw->transposition->chromatic ? "chromatic" : "none";
                    if (raw->transposition->keysig) {
                        m_j.key("keysig").beginObject()
                            .kv("interval", raw->transposition->keysig->interval)
                            .kv("adjust", raw->transposition->keysig->adjust)
                            .endObject();
                    }
                    if (raw->transposition->chromatic) {
                        m_j.key("chromatic").beginObject()
                            .kv("diatonic", raw->transposition->chromatic->diatonic)
                            .kv("alteration", raw->transposition->chromatic->alteration)
                            .endObject();
                    }
                    m_j.kv("no_key_sig", raw->transposition->noSimplifyKey);
                }
                m_j.kv("transposition_type", ttype);
                // the smallest named bracket group containing the staff (Finale scores often
                // name staves "1 2" / "3" and put the instrument name on the group)
                std::string group;
                size_t best = SIZE_MAX;
                for (const auto& g : m_doc->getDetails()->getArray<details::StaffGroup>(SCORE_PARTID, BASE_SYSTEM_ID)) {
                    if (!g->fullNameId || !g->staves.count(members[0]) || g->staves.size() >= best) continue;
                    std::string n;
                    try { n = g->getFullName(AS::Unicode); } catch (...) {}
                    if (!n.empty()) { group = n; best = g->staves.size(); }
                }
                if (!group.empty()) m_j.kv("group_name", group);
            }
            // instrument changes (Finale staff styles that change the instrument), each with the
            // effective top-staff state from that point
            if (info) {
                try {
                    auto changes = info->getChanges();
                    if (changes.size() > 1) {
                        m_j.key("changes").beginArray();
                        for (const auto& [point, change] : changes) {
                            const auto& comp = change.topStaffComposite;
                            Fraction start = measStart(point.measureId);
                            m_j.beginObject()
                                .kv("measure", unsigned(point.measureId))
                                .kv("pos", (start < Fraction(0) ? Fraction(0) : start) + point.position)
                                .kv("uuid", change.identity.instUuid);
                            if (comp) {
                                using AS = musx::util::EnigmaString::AccidentalStyle;
                                m_j.kv("name", comp->getFullInstrumentName(AS::Unicode))
                                    .kv("short_name", comp->getAbbreviatedInstrumentName(AS::Unicode));
                                std::string tt = "none";
                                if (comp->transposition) {
                                    tt = comp->transposition->keysig ? "keysig" : comp->transposition->chromatic ? "chromatic" : "none";
                                    if (comp->transposition->keysig)
                                        m_j.key("keysig").beginObject().kv("interval", comp->transposition->keysig->interval)
                                            .kv("adjust", comp->transposition->keysig->adjust).endObject();
                                    if (comp->transposition->chromatic)
                                        m_j.key("chromatic").beginObject().kv("diatonic", comp->transposition->chromatic->diatonic)
                                            .kv("alteration", comp->transposition->chromatic->alteration).endObject();
                                }
                                m_j.kv("transposition_type", tt);
                            }
                            m_j.endObject();
                        }
                        m_j.endArray();
                    }
                } catch (const std::exception& ex) {
                    m_warnings.push_back(std::string("instrument changes: ") + ex.what());
                }
            }
            m_j.endObject();
        }
        m_j.endArray();
    }

    void staves()
    {
        m_j.key("staves").beginArray();
        for (auto staffId : m_staffOrder) {
            m_j.beginObject().kv("id", unsigned(staffId));
            if (auto raw = m_doc->getOthers()->get<others::Staff>(SCORE_PARTID, staffId)) {
                m_j.kv("default_clef", unsigned(raw->defaultClef));
                m_j.kv("hide_mode", int(raw->hideMode));  // 0 none, 1 cutaway, 2 score+parts, 3 score
            }
            styleChanges(staffId);
            timeChanges(staffId);
            clefChanges(staffId);
            m_tuplets.clear();
            m_j.key("entries").beginArray();
            for (const auto& m : m_measures) {
                entries(staffId, m);
            }
            m_j.endArray();
            m_j.key("tuplets").beginArray();
            for (const auto& t : m_tuplets) m_j.raw(t);
            m_j.endArray();
            m_j.endObject();
        }
        m_j.endArray();
    }

    void entries(StaffCmper staffId, const MusxInstance<others::Measure>& m)
    {
        details::GFrameHoldContext ctx(m_doc, SCORE_PARTID, staffId, m->getCmper());
        if (!ctx) return;
        const Fraction start = m_measStart[m->getCmper()];
        // staff time -> global time (independent time signatures)
        const Fraction stretch = m->calcDuration() / m->calcDuration(staffId);
        for (LayerIndex layer = 0; layer < 4; ++layer) {
            auto frame = ctx.createEntryFrame(layer);
            if (!frame) continue;
            for (const auto& t : frame->tupletInfo) {
                if (!t.tuplet) continue;
                std::ostringstream os;
                Json tj(os);
                tj.beginObject()
                    .kv("layer", unsigned(layer) + 1)
                    .kv("voice", t.voice2 ? 2 : 1)
                    .kv("pos", start + t.startDura * stretch)
                    .kv("end", start + t.endDura * stretch)
                    .kv("display_num", t.tuplet->displayNumber)
                    .kv("display_dur", Fraction::fromEdu(t.tuplet->displayDuration))
                    .kv("ref_num", t.tuplet->referenceNumber)
                    .kv("ref_dur", Fraction::fromEdu(t.tuplet->referenceDuration))
                    .kv("hidden", t.tuplet->hidden)
                    .kv("tremolo", t.calcIsTremolo());
                if (t.calcIsTremolo()) {  // strokes = beams of the notated (short) notes
                    try { tj.kv("beams", unsigned(EntryInfoPtr(frame, t.startIndex).calcNumberOfBeams())); } catch (...) {}
                }
                tj.endObject();
                m_tuplets.push_back(os.str());
            }
            frame->iterateEntries([&](const EntryInfoPtr& e) {
                entry(e, layer, start, stretch);
                return true;
            });
        }
    }

    void entry(const EntryInfoPtr& e, LayerIndex layer, Fraction start, Fraction stretch)
    {
        auto ent = e->getEntry();
        m_j.beginObject()
            .kv("n", long(ent->getEntryNumber()))
            .kv("measure", unsigned(e.getMeasure()))
            .kv("layer", unsigned(layer) + 1)
            .kv("voice", e.getVoice())
            .kv("pos", start + e->elapsedDuration * stretch)
            .kv("dur", e->actualDuration * stretch)
            .kv("notated", ent->calcFraction())
            .kv("grace", ent->graceNote)
            .kv("hidden", ent->isHidden);
        if (ent->graceNote) m_j.kv("grace_slash", e.calcGraceNoteSlash());
        auto [freeze, up] = e.calcEntryStemSettings();
        if (freeze) m_j.kv("stem", up ? "up" : "down");
        if (ent->checkAccis) m_j.kv("check_accis", true);
        if (e.calcIsSingletonBeamExtraEntry()) m_j.kv("workaround_extra", true);
        if (e.calcIsBeamedRestWorkaroundHiddenRest()) m_j.kv("workaround_hidden_rest", true);
        const bool rest = !ent->isNote;
        m_j.kv("rest", rest);
        m_j.key("notes").beginArray();
        if (!rest) {
            for (size_t i = 0; i < ent->notes.size(); ++i) {
                NoteInfoPtr n(e, i);
                NotePropertiesOptions po;
                po.pitchMode = PitchMode::Concert;
                po.alwaysUseEntryStaff = true;
                auto props = n.calcNoteProperties(po);
                const int step = int(props.noteName);
                const int midi = 12 * (props.octave + 1) + STEP_SEMI[step] + props.alteration;
                m_j.beginObject()
                    .kv("midi", midi)
                    .kv("step", std::string(1, STEP_NAMES[step]))
                    .kv("alter", props.alteration)
                    .kv("tie", n.calcHasTieStart())
                    .kv("tie_end", n.calcHasTieEnd());
                if (n->showAcci) m_j.kv("show_acci", true);
                if (n->freezeAcci) m_j.kv("acc", n->showAcci ? "show" : "hide");
                if (n->parenAcci) m_j.kv("acc", "paren");
                if (ent->noteDetail) {  // notehead override (diamond = touched harmonic note)
                    try {
                        if (auto alt = m_doc->getDetails()->getForNote<details::NoteAlterations>(n, SCORE_PARTID)) {
                            if (alt->altNhead) {
                                std::string font;
                                bool smufl = false;
                                auto fi = alt->useOwnFont && alt->customFont ? alt->customFont
                                                                             : m_doc->getOptions()->get<options::FontOptions>()
                                                                                   ->getFontInfo(options::FontOptions::FontType::Noteheads);
                                try { font = fi ? fi->getName() : ""; smufl = fi && fi->calcIsSMuFL(); } catch (...) {}
                                m_j.kv("notehead", glyphName(font, alt->altNhead, smufl));
                            }
                        }
                    } catch (...) {}
                }
                if (n->crossStaff) {
                    m_j.kv("cross_staff", true);
                    try { m_j.kv("staff", unsigned(n.calcStaff())); } catch (...) {}
                }
                m_j.endObject();
            }
        }
        m_j.endArray();
        if (ent->articDetail) {
            m_j.key("artics").beginArray();
            for (const auto& a : m_doc->getDetails()->getArray<details::ArticulationAssign>(SCORE_PARTID, ent->getEntryNumber())) {
                auto def = m_doc->getOthers()->get<others::ArticulationDef>(SCORE_PARTID, a->articDef);
                if (!def) continue;
                bool smufl = false;
                try { smufl = def->fontMain && def->fontMain->calcIsSMuFL(); } catch (...) {}
                std::string font;
                try { font = def->fontMain ? def->fontMain->getName() : ""; } catch (...) {}
                m_j.beginObject().kv("def", unsigned(a->articDef)).kv("char", unsigned(def->charMain)).kv("smufl", smufl)
                    .kv("font", font).kv("glyph", glyphName(font, def->charMain, smufl))
                    .kv("hidden", a->hide).endObject();
            }
            m_j.endArray();
        }
        if (ent->lyricDetail) lyrics(ent->getEntryNumber());
        m_j.endObject();
    }

    // Lyric syllables on an entry: verse / chorus / section text, line number, hyphens, extension
    template <typename T>
    void lyricsOf(EntryNumber entnum, const char* type, bool& open)
    {
        for (const auto& la : m_doc->getDetails()->getArray<T>(SCORE_PARTID, entnum)) {
            auto text = la->getLyricText();
            if (!text || la->syllable < 1 || la->syllable > text->syllables.size()) continue;
            const auto& syl = text->syllables[la->syllable - 1];
            if (!open) { m_j.key("lyrics").beginArray(); open = true; }
            m_j.beginObject().kv("type", type).kv("number", unsigned(la->lyricNumber))
                .kv("text", syl->syllable).kv("hyphen_before", syl->hasHyphenBefore)
                .kv("hyphen_after", syl->hasHyphenAfter).kv("extension", la->wext != 0 || syl->strippedUnderscores > 0)
                .endObject();
        }
    }

    void lyrics(EntryNumber entnum)
    {
        bool open = false;
        try {
            lyricsOf<details::LyricAssignVerse>(entnum, "verse", open);
            lyricsOf<details::LyricAssignChorus>(entnum, "chorus", open);
            lyricsOf<details::LyricAssignSection>(entnum, "section", open);
        } catch (const std::exception& ex) {
            m_warnings.push_back(std::string("lyrics: ") + ex.what());
        }
        if (open) m_j.endArray();
    }

    // Chord symbols (details::ChordAssign per staff and measure): root/bass as scale degrees of the
    // key plus alteration; the suffix as its glyph/number elements
    void chords()
    {
        m_j.key("chords").beginArray();
        try {
            for (const auto& m : m_measures) {
                if (!m->hasChord) continue;
                for (auto staffId : m_staffOrder) {
                    for (const auto& c : m_doc->getDetails()->getArray<details::ChordAssign>(SCORE_PARTID, staffId, m->getCmper())) {
                        m_j.beginObject().kv("staff", unsigned(staffId)).kv("measure", unsigned(m->getCmper()))
                            .kv("pos", measStart(m->getCmper()) + Fraction::fromEdu(c->horzEdu))
                            .kv("root_degree", c->rootScaleNum).kv("root_alter", c->rootAlter)
                            .kv("root_lower", c->rootLowerCase).kv("show_root", c->showRoot)
                            .kv("show_suffix", c->showSuffix).kv("show_bass", c->showAltBass)
                            .kv("bass_degree", c->bassScaleNum).kv("bass_alter", c->bassAlter)
                            .kv("bass_under", c->bassPosition != details::ChordAssign::BassPosition::AfterRoot);
                        m_j.key("suffix").beginArray();
                        if (c->suffixId) {
                            for (const auto& el : c->getChordSuffix()) {
                                std::string font;
                                bool smufl = false;
                                try { font = el->font ? el->font->getName() : ""; smufl = el->font && el->font->calcIsSMuFL(); } catch (...) {}
                                std::string txt;
                                if (el->isNumber) txt = std::to_string(int(el->symbol));
                                else {
                                    std::u32string u(1, el->symbol);
                                    txt = musx::util::EnigmaString::toU8(u);
                                }
                                m_j.beginObject().kv("text", txt).kv("number", el->isNumber)
                                    .kv("prefix", int(el->prefix)).kv("font", font)
                                    .kv("glyph", el->isNumber ? std::string() : glyphName(font, el->symbol, smufl))
                                    .endObject();
                            }
                        }
                        m_j.endArray();
                        m_j.endObject();
                    }
                }
            }
        } catch (const std::exception& ex) {
            m_warnings.push_back(std::string("chords: ") + ex.what());
        }
        m_j.endArray();
    }

    static std::string transpositionKey(const MusxInstance<others::Staff>& st)
    {
        if (!st || !st->transposition) return "none";
        const auto& t = st->transposition;
        if (t->keysig) return "k" + std::to_string(t->keysig->interval) + "," + std::to_string(t->keysig->adjust);
        if (t->chromatic) return "c" + std::to_string(t->chromatic->diatonic) + "," + std::to_string(t->chromatic->alteration);
        return "none";
    }

    // Bar-by-bar effective staff state (staff styles applied): emit each point where the
    // instrument type, its name or the transposition changes (Finale staff styles such as
    // Piano -> Celesta on one staff).
    void styleChanges(StaffCmper staffId)
    {
        auto raw = m_doc->getOthers()->get<others::Staff>(SCORE_PARTID, staffId);
        if (!raw) return;
        using AS = musx::util::EnigmaString::AccidentalStyle;
        std::string last = raw->instUuid + "|" + transpositionKey(raw) + "|" + raw->getFullInstrumentName(AS::Unicode);
        m_j.key("style_changes").beginArray();
        for (const auto& m : m_measures) {
            MusxInstance<others::Staff> comp;
            try {
                comp = others::StaffComposite::createCurrent(m_doc, SCORE_PARTID, staffId, m->getCmper(), 0);
            } catch (...) {
                continue;
            }
            if (!comp) continue;
            std::string name = comp->getFullInstrumentName(AS::Unicode);
            std::string key = comp->instUuid + "|" + transpositionKey(comp) + "|" + name;
            if (key == last) continue;
            last = key;
            m_j.beginObject().kv("measure", unsigned(m->getCmper())).kv("pos", m_measStart[m->getCmper()])
                .kv("uuid", comp->instUuid).kv("name", name)
                .kv("short_name", comp->getAbbreviatedInstrumentName(AS::Unicode));
            std::string tt = "none";
            if (comp->transposition) {
                tt = comp->transposition->keysig ? "keysig" : comp->transposition->chromatic ? "chromatic" : "none";
                if (comp->transposition->keysig)
                    m_j.key("keysig").beginObject().kv("interval", comp->transposition->keysig->interval)
                        .kv("adjust", comp->transposition->keysig->adjust).endObject();
                if (comp->transposition->chromatic)
                    m_j.key("chromatic").beginObject().kv("diatonic", comp->transposition->chromatic->diatonic)
                        .kv("alteration", comp->transposition->chromatic->alteration).endObject();
            }
            m_j.kv("transposition_type", tt).endObject();
        }
        m_j.endArray();
    }

    static std::string tsKey(const MusxInstance<TimeSignature>& ts)
    {
        if (!ts) return "";
        std::string k;
        for (const auto& c : ts->components) {
            for (auto x : c.counts) k += std::to_string(x.numerator()) + ":" + std::to_string(x.denominator()) + ",";
            k += "/";
            for (auto u : c.units) k += std::to_string(u) + ",";
            k += ";";
        }
        return k;
    }

    // Independent (staff-only) time signatures: every bar where this staff's display time
    // signature differs from the score's (E.T.: 12/8 staves against 4/4).
    void timeChanges(StaffCmper staffId)
    {
        m_j.key("time_changes").beginArray();
        for (const auto& m : m_measures) {
            MusxInstance<TimeSignature> st, sd;
            try {
                st = m->createTimeSignature(staffId);
                sd = m->createDisplayTimeSignature(staffId);
            } catch (...) {
                continue;
            }
            auto gd = m->createDisplayTimeSignature();
            if (tsKey(sd) == tsKey(gd) && tsKey(st) == tsKey(m->createTimeSignature())) continue;
            m_j.beginObject().kv("measure", unsigned(m->getCmper())).kv("pos", m_measStart[m->getCmper()]);
            m_j.key("time");
            timeSig(st);
            m_j.key("display_time");
            timeSig(sd);
            m_j.kv("display_duration", sd ? sd->calcTotalDuration() : Fraction{});
            m_j.endObject();
        }
        m_j.endArray();
    }

    // Clef as musxdom sees it on this staff at this point (a percussion staff gets a
    // percussion clef whatever the glyph; staff styles can change that mid-piece).
    void clefInfo(StaffCmper staffId, MeasCmper meas, Edu edu, ClefIndex index)
    {
        auto opts = m_doc->getOptions()->get<options::ClefOptions>();
        if (!opts || index >= opts->clefDefs.size()) return;
        MusxInstance<others::Staff> staff;
        try {
            staff = others::StaffComposite::createCurrent(m_doc, SCORE_PARTID, staffId, meas, edu);
        } catch (...) {
        }
        auto [type, octave] = opts->clefDefs[index]->calcInfo(staff);
        m_j.kv("type", clefTypeName(type)).kv("octave", octave).kv("middle_c", opts->clefDefs[index]->middleCPos);
    }

    void clefChanges(StaffCmper staffId)
    {
        if (auto raw = m_doc->getOthers()->get<others::Staff>(SCORE_PARTID, staffId); raw && !m_measures.empty()) {
            m_j.key("default_clef_info").beginObject().kv("index", unsigned(raw->defaultClef));
            clefInfo(staffId, m_measures[0]->getCmper(), 0, raw->defaultClef);
            m_j.endObject();
        }
        m_j.key("clef_changes").beginArray();
        for (const auto& m : m_measures) {
            auto hold = m_doc->getDetails()->get<details::GFrameHold>(SCORE_PARTID, staffId, m->getCmper());
            if (!hold) continue;
            const Fraction start = m_measStart[m->getCmper()];
            if (hold->clefListId) {
                for (const auto& c : m_doc->getOthers()->getArray<others::ClefList>(SCORE_PARTID, hold->clefListId)) {
                    m_j.beginObject()
                        .kv("pos", start + Fraction::fromEdu(c->xEduPos))
                        .kv("index", unsigned(c->clefIndex))
                        .kv("measure", unsigned(m->getCmper()));
                    clefInfo(staffId, m->getCmper(), c->xEduPos, c->clefIndex);
                    m_j.endObject();
                }
            } else if (hold->clefId) {
                m_j.beginObject()
                    .kv("pos", start)
                    .kv("index", unsigned(*hold->clefId))
                    .kv("measure", unsigned(m->getCmper()));
                clefInfo(staffId, m->getCmper(), 0, *hold->clefId);
                m_j.endObject();
            }
        }
        m_j.endArray();
    }

    Fraction stretchFor(MeasCmper meas, int staff) const
    {
        if (staff <= 0) return Fraction(1);
        auto m = m_doc->getOthers()->get<others::Measure>(SCORE_PARTID, meas);
        if (!m) return Fraction(1);
        return m->calcDuration() / m->calcDuration(StaffCmper(staff));
    }

    Fraction measStart(MeasCmper meas) const
    {
        auto it = m_measStart.find(meas);
        return it == m_measStart.end() ? Fraction(-1) : it->second;
    }

    void expressions()
    {
        m_j.key("expressions").beginArray();
        for (const auto& a : m_doc->getOthers()->getArray<others::MeasureExprAssign>(SCORE_PARTID)) {
            const MeasCmper meas = MeasCmper(a->getCmper());
            if (measStart(meas) < 0) continue;
            m_j.beginObject()
                .kv("measure", unsigned(meas))
                .kv("staff", int(a->staffAssign))
                .kv("pos", measStart(meas) + Fraction::fromEdu(a->eduPosition) * stretchFor(meas, a->staffAssign))
                .kv("layer", a->layer)
                .kv("hidden", a->hidden);
            Cmper catId = 0;
            if (a->textExprId) {
                auto def = m_doc->getOthers()->get<others::TextExpressionDef>(SCORE_PARTID, a->textExprId);
                if (def) {
                    catId = def->categoryId;
                    m_j.kv("kind", "text").kv("def", unsigned(a->textExprId));
                    m_j.key("chunks");
                    try {
                        writeChunks(m_j, textChunks(def->getRawTextCtx(SCORE_PARTID)));
                    } catch (const std::exception& ex) {
                        m_j.beginArray().endArray();
                        m_warnings.push_back(std::string("expression text: ") + ex.what());
                    }
                    m_j.kv("playback", enumName(def->playbackType)).kv("value", def->value).kv("aux", def->auxData1)
                        .kv("description", def->description).kv("enclosure", def->hasEnclosure);
                }
            } else if (a->shapeExprId) {
                auto def = m_doc->getOthers()->get<others::ShapeExpressionDef>(SCORE_PARTID, a->shapeExprId);
                if (def) catId = def->categoryId;
                m_j.kv("kind", "shape").kv("def", unsigned(a->shapeExprId));
            }
            if (catId) {
                auto cat = m_doc->getOthers()->get<others::MarkingCategory>(SCORE_PARTID, catId);
                if (cat) m_j.kv("category", enumName(cat->categoryType)).kv("category_name", cat->getName());
            }
            m_j.endObject();
        }
        m_j.endArray();
    }

    void endPoint(const char* name, const std::shared_ptr<others::SmartShape::TerminationSeg>& seg)
    {
        m_j.key(name);
        if (!seg || !seg->endPoint) { m_j.null(); return; }
        const auto& ep = seg->endPoint;
        const MeasCmper meas = ep->calcMeasure();
        m_j.beginObject()
            .kv("staff", unsigned(ep->calcStaff()))
            .kv("measure", unsigned(meas))
            .kv("entry", long(ep->entryNumber))
            .kv("valid", ep->calcIsValid());
        if (measStart(meas) >= 0) {
            try {
                m_j.kv("pos", measStart(meas) + ep->calcGlobalPosition());
            } catch (...) {
            }
        }
        m_j.endObject();
    }

    void smartShapes()
    {
        m_j.key("smart_shapes").beginArray();
        for (const auto& sh : m_doc->getOthers()->getArray<others::SmartShape>(SCORE_PARTID)) {
            m_j.beginObject()
                .kv("id", unsigned(sh->getCmper()))
                .kv("type", enumName(sh->shapeType))
                .kv("entry_based", sh->entryBased)
                .kv("hidden", sh->hidden)
                .kv("line_style", unsigned(sh->lineStyleId));
            endPoint("start", sh->startTermSeg);
            endPoint("end", sh->endTermSeg);
            m_j.endObject();
        }
        m_j.endArray();
        customLines();
    }

    // Custom line definitions (Finale "smartLine" styles): how each is drawn, so the Python
    // side can recognise trill lines (wavy glyph or "tr" text), brackets, etc.
    void customLines()
    {
        m_j.key("custom_lines").beginArray();
        for (const auto& cl : m_doc->getOthers()->getArray<others::SmartShapeCustomLine>(SCORE_PARTID)) {
            m_j.beginObject().kv("id", unsigned(cl->getCmper()));
            const char* style = cl->lineStyle == others::SmartShapeCustomLine::LineStyle::Char ? "char"
                : cl->lineStyle == others::SmartShapeCustomLine::LineStyle::Solid ? "solid" : "dashed";
            m_j.kv("style", style);
            auto cap = [](others::SmartShapeCustomLine::LineCapType t) {
                using T = others::SmartShapeCustomLine::LineCapType;
                return t == T::Hook ? "hook" : t == T::None ? "none" : "arrow";
            };
            // hook lengths are signed: negative points down
            m_j.kv("cap_start", cap(cl->lineCapStartType)).kv("cap_end", cap(cl->lineCapEndType))
                .kv("hook_start", long(cl->lineCapStartHookLength)).kv("hook_end", long(cl->lineCapEndHookLength))
                .kv("arrow_start", unsigned(cl->lineCapStartArrowId)).kv("arrow_end", unsigned(cl->lineCapEndArrowId));
            if (cl->charParams) {
                m_j.kv("char", unsigned(cl->charParams->lineChar));
                bool smufl = false;
                std::string font;
                try {
                    smufl = cl->charParams->font && cl->charParams->font->calcIsSMuFL();
                    font = cl->charParams->font ? cl->charParams->font->getName() : "";
                } catch (...) {}
                m_j.kv("smufl", smufl).kv("font", font).kv("glyph", glyphName(font, cl->charParams->lineChar, smufl));
            }
            auto text = [&](const char* key, Cmper id, auto getCtx) {
                if (!id) return;
                m_j.key(key);
                try {
                    writeChunks(m_j, textChunks(getCtx()));
                } catch (...) {
                    m_j.beginArray().endArray();
                }
            };
            text("start_text", cl->leftStartRawTextId, [&] { return cl->getLeftStartRawTextCtx(SCORE_PARTID); });
            text("center_text", cl->centerFullRawTextId, [&] { return cl->getCenterFullRawTextCtx(SCORE_PARTID); });
            text("end_text", cl->rightEndRawTextId, [&] { return cl->getRightEndRawTextCtx(SCORE_PARTID); });
            m_j.endObject();
        }
        m_j.endArray();
    }

    DocumentPtr m_doc;
    Json& m_j;
    MusxInstanceList<others::Measure> m_measures{m_doc, SCORE_PARTID};
    std::map<MeasCmper, Fraction> m_measStart;
    std::vector<StaffCmper> m_staffOrder;
    std::vector<std::string> m_warnings;
    std::vector<std::string> m_tuplets;
};

static std::vector<char> readFile(const std::string& path)
{
    std::ifstream f(path, std::ios::binary);
    if (!f) throw std::runtime_error("cannot open " + path);
    return std::vector<char>(std::istreambuf_iterator<char>(f), {});
}

int main(int argc, char** argv)
{
    if (argc < 2) {
        std::cerr << "usage: f2d-extract FILE.mus|FILE.enigmaxml\n";
        return 2;
    }
    const std::string path = argv[1];
    try {
        auto data = readFile(path);
        DocumentPtr doc;
        std::string kind;
        auto lower = path;
        std::transform(lower.begin(), lower.end(), lower.begin(), ::tolower);
        const bool looksXml = !data.empty() && (data[0] == '<' || (data.size() > 3 && (unsigned char)data[0] == 0xEF));
        if (looksXml) {
            kind = "enigmaxml";
            doc = musx::factory::DocumentFactory::create<musx::xml::pugi::Document>(data.data(), data.size());
        } else {
            kind = "mus";
            auto reader = finale_mus_reader::Reader::create<musx::xml::pugi::Document>();
            finale_mus_reader::ImportOptions opts;
            opts.sourcePath = std::filesystem::path(path);
            doc = reader.read(std::span<const std::uint8_t>(reinterpret_cast<const std::uint8_t*>(data.data()), data.size()), opts);
        }
        if (!doc) throw std::runtime_error("no document");
        std::ostringstream out;
        Json j(out);
        Extractor(doc, j).run(path, kind);
        std::cout << out.str() << "\n";
    } catch (const std::exception& e) {
        std::cerr << "f2d-extract: " << e.what() << "\n";
        return 1;
    }
    return 0;
}
