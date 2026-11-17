<script lang="ts">
  import DiffView from "./DiffView.svelte";
  import Thumb from "./Thumb.svelte";
  import { api } from "./api";
  import { fileColor, playbackLabel, stem, when } from "./format";
  import type { ScoreDiff, Snapshot } from "./types";

  let {
    snapshot,
    snapshots,
    onchanged,
    notify,
  }: {
    snapshot: Snapshot;
    snapshots: Snapshot[];
    onchanged: () => void;
    notify: (text: string, kind?: "info" | "error") => void;
  } = $props();

  let compareTo = $state(""); // "" = the version it was made from (parent)
  let diff = $state<ScoreDiff | null>(null);
  let diffError = $state<string | null>(null);
  let loadingDiff = $state(false);
  let busy = $state(false);
  let naming = $state(false);
  let milestoneName = $state("");

  let byId = $derived(new Map(snapshots.map((s) => [s.id, s])));
  let parent = $derived(snapshot.parents[0] ? byId.get(snapshot.parents[0]) : undefined);
  let borrowed = $derived(snapshot.playback_borrow_from ? byId.get(snapshot.playback_borrow_from) : undefined);
  let others = $derived(snapshots.filter((s) => s.id !== snapshot.id));

  // Reset comparison when switching snapshots.
  let lastId = "";
  $effect(() => {
    if (snapshot.id !== lastId) {
      lastId = snapshot.id;
      compareTo = "";
      naming = false;
    }
  });

  $effect(() => {
    const s = snapshot;
    const against = compareTo || s.parents[0] || "";
    diff = null;
    diffError = null;
    if (!against) return;
    loadingDiff = true;
    api
      .diff(s.family, s.id, against)
      .then((d) => {
        if (s === snapshot) diff = d;
      })
      .catch((e) => {
        if (s === snapshot) diffError = String(e);
      })
      .finally(() => {
        if (s === snapshot) loadingDiff = false;
      });
  });

  async function openVersion(open: boolean) {
    busy = true;
    try {
      const r = await api.restore(snapshot.family, snapshot.id, open);
      let msg = open ? `Opened in Dorico: ${r.path}` : `Saved a copy: ${r.path}`;
      if (r.playback_from) {
        const from = byId.get(r.playback_from);
        msg += ` (playback from ${from ? when(from.time) : "an earlier version"})`;
      }
      notify(msg);
      if (!open) await api.reveal(r.path);
      onchanged();
    } catch (e) {
      notify(String(e), "error");
    } finally {
      busy = false;
    }
  }

  async function addMilestone() {
    const name = milestoneName.trim();
    if (!name) return;
    busy = true;
    try {
      await api.addMilestone(snapshot.family, snapshot.id, name);
      milestoneName = "";
      naming = false;
      onchanged();
    } catch (e) {
      notify(String(e), "error");
    } finally {
      busy = false;
    }
  }

  async function removeMilestone(name: string) {
    try {
      await api.removeMilestone(snapshot.family, snapshot.id, name);
      onchanged();
    } catch (e) {
      notify(String(e), "error");
    }
  }
</script>

<article class="scroll">
  <header>
    <Thumb {snapshot} width={92} />
    <div class="head">
      <div class="when">{when(snapshot.time)}</div>
      <div class="file">
        <span class="chip" title={snapshot.path}>
          <span class="dot" style:background={fileColor(snapshot.file_name)}></span>{stem(snapshot.file_name)}
        </span>
        <span class="muted small">Dorico {snapshot.dorico_version} · {snapshot.short_id}</span>
      </div>
      <div class="milestones">
        {#each snapshot.milestones as m}
          <span class="badge milestone">
            ★ {m.name}
            <button class="x" title="Remove milestone" onclick={() => removeMilestone(m.name)}>×</button>
          </span>
        {/each}
        {#if naming}
          <form
            onsubmit={(e) => {
              e.preventDefault();
              addMilestone();
            }}
          >
            <!-- svelte-ignore a11y_autofocus -->
            <input bind:value={milestoneName} placeholder="e.g. Sent to orchestrator" autofocus />
            <button type="submit" class="primary" disabled={busy || !milestoneName.trim()}>Add</button>
            <button type="button" class="ghost" onclick={() => (naming = false)}>Cancel</button>
          </form>
        {:else}
          <button class="ghost small-btn" onclick={() => (naming = true)}>★ Mark as milestone…</button>
        {/if}
      </div>
      <div class="actions">
        <button class="primary" disabled={busy} onclick={() => openVersion(true)}>Open this version in Dorico</button>
        <button disabled={busy} onclick={() => openVersion(false)}>Save a copy…</button>
        <button class="ghost" onclick={() => api.reveal(snapshot.path)}>Show original file</button>
      </div>
    </div>
  </header>

  <section class="playback">
    <div class="label">Playback</div>
    <div>
      {playbackLabel(snapshot)}{#if !snapshot.playback_stored && snapshot.playback_reason === "skipped"}: opening this version
        uses the playback setup saved {borrowed ? when(borrowed.time) : "with an earlier version"} (same plugins; plugin
        settings may differ){/if}.
      {#if snapshot.playback_setup_changes.length}
        <div class="setup">
          {#each snapshot.playback_setup_changes as c}
            <span class="chip" class:plus={c.startsWith("+")} class:minus={c.startsWith("-")}>{c}</span>
          {/each}
        </div>
      {/if}
    </div>
  </section>

  <section class="changes">
    <div class="compare">
      <span class="label">Changes compared with</span>
      <select bind:value={compareTo}>
        <option value="">
          {parent ? `the version it came from (${when(parent.time)}, ${stem(parent.file_name)})` : "— (first version)"}
        </option>
        {#each others as o (o.id)}
          {#if o.id !== snapshot.parents[0]}
            <option value={o.id}>{when(o.time)} · {stem(o.file_name)}{o.milestones.length ? ` ★ ${o.milestones[0].name}` : ""}</option>
          {/if}
        {/each}
      </select>
    </div>
    {#if loadingDiff}
      <p class="muted">Comparing…</p>
    {:else if diffError}
      <p class="error">{diffError}</p>
    {:else if diff}
      <DiffView {diff} notation={(flowId) => api.notationDiff(snapshot.family, snapshot.id, compareTo || snapshot.parents[0] || null, flowId)} />
    {:else if !snapshot.parents.length && !compareTo}
      <p class="muted">This is the first version in this project's history. Pick another version above to compare.</p>
    {/if}
  </section>
</article>

<style>
  article {
    min-height: 0;
    padding: 20px 24px 40px;
    display: flex;
    flex-direction: column;
    gap: 18px;
  }
  header {
    display: flex;
    gap: 18px;
  }
  .head {
    display: flex;
    flex-direction: column;
    gap: 8px;
    min-width: 0;
  }
  .when {
    font-size: 20px;
    font-weight: 650;
  }
  .file {
    display: flex;
    gap: 10px;
    align-items: center;
    flex-wrap: wrap;
  }
  .small {
    font-size: 12px;
  }
  .milestones {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    align-items: center;
  }
  .milestones form {
    display: flex;
    gap: 6px;
  }
  .x {
    border: none;
    background: transparent;
    padding: 0 0 0 4px;
    color: inherit;
    cursor: pointer;
  }
  .small-btn {
    padding: 2px 8px;
    font-size: 12px;
  }
  .actions {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    margin-top: 4px;
  }
  .label {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    color: var(--muted);
    margin-bottom: 4px;
  }
  .playback {
    font-size: 13px;
    line-height: 1.5;
    padding: 10px 12px;
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: var(--radius);
  }
  .setup {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    margin-top: 6px;
  }
  .chip.plus {
    color: var(--add);
  }
  .chip.minus {
    color: var(--del);
  }
  .compare {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 10px;
  }
  .compare .label {
    margin: 0;
    white-space: nowrap;
  }
  .compare select {
    min-width: 0;
    flex: 1;
    max-width: 560px;
  }
  .error {
    color: var(--del);
  }
</style>
