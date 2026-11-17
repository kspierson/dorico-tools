// Decompile Finale's Human Playback code to C-like text files.
//
// Seeds: every function in a namespace under "humanplayback" (from RTTI), plus every
// function that references one of the HP-related strings below. From the seeds it
// follows calls (callees) up to MAX_DEPTH levels and decompiles everything reached.
//
// Output (args[0], default ~/tools/ghidra-out):
//   functions/<address>_<name>.c   decompiled code
//   index.tsv                      address, name, namespace, depth, size, seed reason
//   calls.tsv                      caller -> callee edges
//   strings.tsv                    string -> referencing functions
//
// Run headless:
//   analyzeHeadless ~/tools/ghidra-projects Finale -process Finale.exe -noanalysis \
//     -scriptPath <this dir> -postScript ExportHP.java <outdir>
//@category dorico-hp

import ghidra.app.decompiler.*;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;
import ghidra.program.model.data.StringDataInstance;
import java.io.*;
import java.util.*;

public class ExportHP extends GhidraScript {
    static final int MAX_DEPTH = 3;
    static final int MAX_FUNCS = 6000;
    static final String[] KEYS = {
        "hpOptions", "selectedPreset", "interpretSlurs", "interpretHairpins", "rhythmicFeel", "rhythmicAccents",
        "rubato", "swing", "mood", "baroqueStyle", "automaticEspressivo", "emphasizeShortSyncops",
        "adjustDottedEighth", "vienneseWaltzFeel", "interpretCadences", "softenBasses", "adjustChordBalance",
        "detectAccompaniment", "autoDetectSolo", "strumChords", "automaticPedaling", "hpPrefData",
        "hairpinPairEmphasis", "autoExpressionEmphasis", "volumeBaseValue", "trillCentiSpeed",
        "tremoloCentiSpeed", "fermataMinCentiDura", "garritanSoloStringsAutoVibrato",
        "garritanSoloStringsOptimize", "midiAnticipation", "continuousDynamicApproach", "hairpinCurve",
        "classical", "romantic", "baroque", "21stCentury", "vienneseWaltz", "lightWaltz", "marchingBand",
        "process-interpret", "process-ornaments", "process-techniques", "process-hairpins", "process-gliss",
        "save-note_data", "save-continuous-data", "get-notes", "get-expressions", "get-shapes",
        "STRINGS.HUMANPLAYBACK", "DEFAULTS.HUMANPLAYBACK", "humanplayback-defaults", "HP:swing",
        "ritardandoBeforeFermata", "humanizeRollsAndTrills", "keepTimingSafe", "delayGliss",
    };

    File out;
    PrintWriter index, calls, strs;
    DecompInterface dec;
    Map<Function, Integer> depth = new LinkedHashMap<>();
    Map<Function, String> reason = new HashMap<>();

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        out = new File(args.length > 0 ? args[0] : System.getProperty("user.home") + "/tools/ghidra-out");
        new File(out, "functions").mkdirs();
        index = new PrintWriter(new FileWriter(new File(out, "index.tsv")));
        calls = new PrintWriter(new FileWriter(new File(out, "calls.tsv")));
        strs = new PrintWriter(new FileWriter(new File(out, "strings.tsv")));
        index.println("address\tname\tnamespace\tdepth\tsize\treason");

        // seeds 1: namespaces under humanplayback (and fcdlg HP dialogs)
        SymbolTable st = currentProgram.getSymbolTable();
        FunctionManager fm = currentProgram.getFunctionManager();
        for (Function f : fm.getFunctions(true)) {
            String ns = f.getParentNamespace().getName(true);
            if (ns.contains("humanplayback") || ns.contains("HumanPlayback") || ns.contains("HPOptions")
                    || ns.contains("HPCustomStyle") || ns.contains("ApplyHP") || ns.contains("HP_DataFetcher")) {
                seed(f, "namespace " + ns);
            }
        }
        println("namespace seeds: " + depth.size());

        // seeds 1b: virtual methods listed in the vftables of HP classes (RTTI gives the
        // tables names like humanplayback::InfoNote::vftable even when the functions
        // themselves stay in the global namespace)
        int ptr = currentProgram.getDefaultPointerSize();
        for (Symbol s : st.getAllSymbols(true)) {
            if (!s.getName().startsWith("vftable")) continue;
            String ns = s.getParentNamespace().getName(true);
            if (!(ns.contains("humanplayback") || ns.contains("HPOptions") || ns.contains("HPCustomStyle")
                    || ns.contains("ApplyHP") || ns.contains("HumanPlayback") || ns.contains("HP_"))) continue;
            Address a = s.getAddress();
            for (int i = 0; i < 200; i++) {
                long v;
                try { v = ptr == 8 ? getLong(a.add((long) i * ptr)) : getInt(a.add((long) i * ptr)) & 0xffffffffL; }
                catch (Exception e) { break; }
                Address target = a.getNewAddress(v);
                Function f = fm.getFunctionAt(target);
                if (f == null) break;
                seed(f, "vftable " + ns + "[" + i + "]");
            }
        }
        println("after vftables: " + depth.size());

        // seeds 2: functions referencing HP strings (ASCII or UTF-16)
        Set<String> keys = new HashSet<>(Arrays.asList(KEYS));
        Listing listing = currentProgram.getListing();
        for (Data d : listing.getDefinedData(true)) {
            if (!d.hasStringValue()) continue;
            String s;
            try { s = StringDataInstance.getStringDataInstance(d).getStringValue(); } catch (Exception e) { continue; }
            if (s == null || !keys.contains(s)) continue;
            List<String> users = new ArrayList<>();
            for (Reference r : getReferencesTo(d.getAddress())) {
                Function f = fm.getFunctionContaining(r.getFromAddress());
                if (f != null) { seed(f, "string " + s); users.add(f.getName() + "@" + f.getEntryPoint()); }
            }
            strs.println(s + "\t" + d.getAddress() + "\t" + String.join(",", users));
        }
        strs.close();
        println("total seeds: " + depth.size());

        // BFS callees
        ArrayDeque<Function> q = new ArrayDeque<>(depth.keySet());
        while (!q.isEmpty() && depth.size() < MAX_FUNCS) {
            Function f = q.poll();
            int dpt = depth.get(f);
            for (Function c : f.getCalledFunctions(monitor)) {
                calls.println(f.getEntryPoint() + "\t" + f.getName(true) + "\t" + c.getEntryPoint() + "\t" + c.getName(true));
                if (dpt >= MAX_DEPTH || depth.containsKey(c) || boring(c)) continue;
                depth.put(c, dpt + 1);
                reason.put(c, "callee of " + f.getName(true));
                q.add(c);
            }
        }
        calls.close();
        println("functions to decompile: " + depth.size());

        dec = new DecompInterface();
        dec.openProgram(currentProgram);
        int n = 0;
        for (Map.Entry<Function, Integer> e : depth.entrySet()) {
            Function f = e.getKey();
            if (monitor.isCancelled()) break;
            DecompileResults res = dec.decompileFunction(f, 60, monitor);
            String code = res.decompileCompleted() ? res.getDecompiledFunction().getC() : "// decompile failed: " + res.getErrorMessage();
            String safe = f.getName(true).replaceAll("[^A-Za-z0-9_]+", "_");
            if (safe.length() > 120) safe = safe.substring(0, 120);
            try (PrintWriter w = new PrintWriter(new FileWriter(new File(out, "functions/" + f.getEntryPoint() + "_" + safe + ".c")))) {
                w.println("// " + f.getName(true) + " @ " + f.getEntryPoint() + "  depth " + e.getValue() + "  (" + reason.get(f) + ")");
                w.print(code);
            }
            index.println(f.getEntryPoint() + "\t" + f.getName() + "\t" + f.getParentNamespace().getName(true) + "\t"
                    + e.getValue() + "\t" + f.getBody().getNumAddresses() + "\t" + reason.get(f));
            if (++n % 200 == 0) println("decompiled " + n);
        }
        index.close();
        println("done: " + n + " functions -> " + out);
    }

    void seed(Function f, String why) {
        if (!depth.containsKey(f)) { depth.put(f, 0); reason.put(f, why); }
    }

    boolean boring(Function f) {
        String n = f.getName(true);
        return f.isThunk() || f.isExternal() || n.startsWith("std::") || n.contains("juce::")
                || n.startsWith("_") || n.startsWith("Concurrency::") || n.contains("operator_new")
                || n.contains("operator_delete") || n.startsWith("memcpy") || n.startsWith("memset");
    }
}
