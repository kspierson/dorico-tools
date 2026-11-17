<script lang="ts">
  import { onMount } from "svelte";
  import SettingsDialog from "./lib/SettingsDialog.svelte";
  import SnapshotDialog from "./lib/SnapshotDialog.svelte";
  import Sidebar from "./lib/Sidebar.svelte";
  import SnapshotDetail from "./lib/SnapshotDetail.svelte";
  import Timeline from "./lib/Timeline.svelte";
  import VariantBoard from "./lib/VariantBoard.svelte";
  import { api, inTauri, onActivity, pickDoricoFiles } from "./lib/api";
  import { stem } from "./lib/format";
  import type { Activity, Family, Snapshot, Status } from "./lib/types";

  let status = $state<Status | null>(null);
  let families = $state<Family[]>([]);
  let familyId = $state<string | null>(null);
  let snapshots = $state<Snapshot[]>([]);
  let selectedId = $state<string | null>(null);
  let loadingSnapshots = $state(false);
  let busy = $state(false);
  let showSettings = $state(false);
  let showSnapshot = $state(!inTauri && location.hash === "#snapshot"); // browser preview hook
  let view = $state<"history" | "variants">(["#variants", "#merge"].includes(location.hash) ? "variants" : "history");
  let toasts = $state<{ id: number; text: string; kind: "info" | "error" }[]>([]);
  let toastSeq = 0;

  let family = $derived(families.find((f) => f.id === familyId) ?? null);
  let selected = $derived(snapshots.find((s) => s.id === selectedId) ?? null);

  function notify(text: string, kind: "info" | "error" = "info") {
    const id = ++toastSeq;
    toasts = [...toasts, { id, text, kind }];
    setTimeout(() => (toasts = toasts.filter((t) => t.id !== id)), kind === "error" ? 12000 : 6000);
  }

  async function refreshFamilies() {
    try {
      families = await api.families();
      if (!familyId && families.length) await selectFamily(families[0].id);
    } catch (e) {
      notify(String(e), "error");
    }
  }

  async function loadSnapshots(keepSelection = true) {
    if (!familyId) return;
    loadingSnapshots = true;
    try {
      const fid = familyId;
      const list = await api.snapshots(fid);
      if (fid !== familyId) return;
      snapshots = list;
      if (!keepSelection || !list.some((s) => s.id === selectedId)) selectedId = list[0]?.id ?? null;
    } catch (e) {
      notify(String(e), "error");
    } finally {
      loadingSnapshots = false;
    }
  }

  async function selectFamily(id: string) {
    familyId = id;
    snapshots = [];
    selectedId = null;
    await loadSnapshots(false);
  }

  function handleActivity(a: Activity) {
    if (a.type === "error") {
      notify(`Couldn't snapshot ${a.path}: ${a.message}`, "error");
      return;
    }
    if (a.outcome.outcome === "created") {
      const s = a.outcome.snapshot;
      notify(`Saved version of ${stem(s.file_name)}: ${s.summary.text}`);
      refreshFamilies();
      if (s.family === familyId) loadSnapshots();
      else if (!familyId) selectFamily(s.family);
    }
  }

  async function importFiles() {
    const paths = await pickDoricoFiles();
    if (!paths.length) return;
    busy = true;
    notify(`Importing ${paths.length} file${paths.length === 1 ? "" : "s"}…`);
    try {
      const results = await api.importFiles(paths);
      const failed = results.filter((r) => r.error);
      const created = results.filter((r) => r.outcome?.outcome === "created").length;
      notify(`Imported ${created} version${created === 1 ? "" : "s"}${failed.length ? `, ${failed.length} failed` : ""}.`, failed.length ? "error" : "info");
      for (const f of failed) notify(`${f.path}: ${f.error}`, "error");
      await refreshFamilies();
      const first = results.find((r) => r.outcome);
      const fam = first?.outcome?.outcome === "created" ? first.outcome.snapshot.family : first?.outcome?.family;
      if (fam) await selectFamily(fam);
    } catch (e) {
      notify(String(e), "error");
    } finally {
      busy = false;
    }
  }

  async function snapshotNow(path: string, milestone: string | null) {
    showSnapshot = false;
    busy = true;
    try {
      const o = await api.snapshotNow(path, milestone);
      notify(
        o.outcome === "created"
          ? `${milestone ? `Milestone “${milestone}” saved` : "Version saved"}: ${o.snapshot.summary.text}`
          : milestone
            ? `No changes since the last version; milestone “${milestone}” not added (mark that version instead).`
            : "No changes since the last version.",
      );
      await refreshFamilies();
      const fam = o.outcome === "created" ? o.snapshot.family : o.family;
      await selectFamily(fam);
    } catch (e) {
      notify(String(e), "error");
    } finally {
      busy = false;
    }
  }

  onMount(() => {
    let unlisten: (() => void) | undefined;
    (async () => {
      try {
        status = await api.status();
      } catch (e) {
        notify(String(e), "error");
      }
      await refreshFamilies();
      unlisten = await onActivity(handleActivity);
    })();
    return () => unlisten?.();
  });
</script>

<div class="layout">
  <Sidebar
    {status}
    {families}
    selected={familyId}
    {busy}
    onselect={selectFamily}
    onimport={importFiles}
    onsnapshot={() => (showSnapshot = true)}
    onsettings={() => (showSettings = true)}
  />

  {#if family}
    <div class="main">
      <nav class="views" aria-label="View">
        <button class:on={view === "history"} onclick={() => (view = "history")}>History</button>
        <button class:on={view === "variants"} onclick={() => (view = "variants")}>Variants</button>
      </nav>
      <div class="panes">
        {#if view === "variants"}
          <VariantBoard family={family.id} {snapshots} onchanged={() => loadSnapshots()} {notify} />
        {:else}
          <Timeline {snapshots} {selectedId} loading={loadingSnapshots} onselect={(s) => (selectedId = s.id)} />
          {#if selected}
            <SnapshotDetail snapshot={selected} {snapshots} onchanged={() => loadSnapshots()} {notify} />
          {:else}
            <div class="blank muted">Select a version.</div>
          {/if}
        {/if}
      </div>
    </div>
  {:else}
    <div class="welcome">
      <h1>Every save, kept, and you can see what changed.</h1>
      <p>
        dorigit watches your Dorico projects folder. Each time you save, it records a version and works out what changed
        in musical terms: notes, dynamics, articulations, players, layouts.
      </p>
      <ul>
        <li>Save As (e.g. “Cue v2”) is recognised as the same project, so its history continues.</li>
        <li>Open any earlier version: it's written as a new file, and your current file is never touched.</li>
        <li>Mark milestones (“Sent to orchestrator”) to find important versions quickly.</li>
      </ul>
      <div class="cta">
        <button class="primary" onclick={importFiles} disabled={busy}>Import existing Dorico files…</button>
        <button onclick={() => (showSettings = true)}>Choose folders to watch…</button>
      </div>
      {#if !inTauri}<p class="muted small">(Browser preview with sample data. Run inside Tauri for the real thing.)</p>{/if}
    </div>
  {/if}
</div>

{#if showSnapshot}
  <SnapshotDialog
    initialPath={inTauri ? null : "C:\\Users\\you\\Documents\\Dorico Projects\\1m3 Chase.dorico"}
    onclose={() => (showSnapshot = false)}
    onsave={snapshotNow}
  />
{/if}

{#if showSettings && status}
  <SettingsDialog
    {status}
    onclose={() => (showSettings = false)}
    onsaved={(s) => {
      status = s;
      showSettings = false;
      notify("Settings saved.");
      familyId = null;
      refreshFamilies();
    }}
  />
{/if}

<div class="toasts" aria-live="polite">
  {#each toasts as t (t.id)}
    <div class="toast" class:error={t.kind === "error"}>{t.text}</div>
  {/each}
</div>

<style>
  .layout {
    height: 100vh;
    display: grid;
    grid-template-columns: 260px 1fr;
  }
  .main {
    display: grid;
    grid-template-rows: auto 1fr;
    min-width: 0;
    min-height: 0;
  }
  .panes {
    display: grid;
    grid-template-columns: minmax(340px, 420px) 1fr;
    min-height: 0;
  }
  .views {
    display: flex;
    gap: 4px;
    padding: 8px 12px;
    border-bottom: 1px solid var(--line);
    background: var(--panel);
  }
  .views button {
    background: transparent;
    border-color: transparent;
  }
  .views button.on {
    background: var(--accent-soft);
    color: var(--accent);
    font-weight: 600;
  }
  .blank {
    display: grid;
    place-items: center;
  }
  .welcome {
    grid-column: 2;
    align-self: center;
    justify-self: center;
    max-width: 620px;
    padding: 32px;
    line-height: 1.6;
  }
  .welcome h1 {
    font-size: 24px;
    line-height: 1.3;
    margin: 0 0 12px;
  }
  .welcome ul {
    padding-left: 20px;
  }
  .cta {
    display: flex;
    gap: 10px;
    margin-top: 18px;
  }
  .small {
    font-size: 12px;
  }
  .toasts {
    position: fixed;
    right: 16px;
    bottom: 16px;
    display: flex;
    flex-direction: column;
    gap: 8px;
    z-index: 20;
    max-width: min(520px, calc(100vw - 32px));
  }
  .toast {
    background: var(--panel);
    border: 1px solid var(--line);
    border-left: 3px solid var(--accent);
    box-shadow: var(--shadow);
    border-radius: 6px;
    padding: 10px 14px;
    font-size: 13px;
    word-break: break-word;
  }
  .toast.error {
    border-left-color: var(--del);
  }
</style>
