// Decompile every function whose entry point lies in [start, end) to text files.
// Args: <outdir> <startHex> <endHex>
// Output: <outdir>/functions/<addr>_<name>.c, <outdir>/index.tsv, <outdir>/calls.tsv
//@category dorico-hp

import ghidra.app.decompiler.*;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.*;
import ghidra.program.model.listing.*;
import java.io.*;

public class ExportRange extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] a = getScriptArgs();
        File out = new File(a[0]);
        new File(out, "functions").mkdirs();
        Address start = toAddr(a[1]), end = toAddr(a[2]);
        DecompInterface dec = new DecompInterface();
        dec.openProgram(currentProgram);
        PrintWriter index = new PrintWriter(new FileWriter(new File(out, "index.tsv")));
        PrintWriter calls = new PrintWriter(new FileWriter(new File(out, "calls.tsv")));
        index.println("address\tname\tsize");
        int n = 0;
        for (Function f : currentProgram.getFunctionManager().getFunctions(start, true)) {
            if (f.getEntryPoint().compareTo(end) >= 0) break;
            if (f.isThunk()) continue;
            for (Function c : f.getCalledFunctions(monitor))
                calls.println(f.getEntryPoint() + "\t" + f.getName(true) + "\t" + c.getEntryPoint() + "\t" + c.getName(true));
            DecompileResults r = dec.decompileFunction(f, 90, monitor);
            String code = r.decompileCompleted() ? r.getDecompiledFunction().getC() : "// decompile failed: " + r.getErrorMessage();
            String safe = f.getName(true).replaceAll("[^A-Za-z0-9_]+", "_");
            if (safe.length() > 120) safe = safe.substring(0, 120);
            try (PrintWriter w = new PrintWriter(new FileWriter(new File(out, "functions/" + f.getEntryPoint() + "_" + safe + ".c")))) {
                w.println("// " + f.getName(true) + " @ " + f.getEntryPoint());
                w.print(code);
            }
            index.println(f.getEntryPoint() + "\t" + f.getName(true) + "\t" + f.getBody().getNumAddresses());
            if (++n % 250 == 0) println("decompiled " + n);
        }
        index.close(); calls.close();
        println("done: " + n + " functions -> " + out);
    }
}
