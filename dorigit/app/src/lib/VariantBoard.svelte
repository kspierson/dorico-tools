<script lang="ts">
  // The variant board (docs/MERGE.md §3): every variant of a project, the bars where it
  // differs from where it started, its notes and tags. Variants are made here too.
  import DiffView from "./DiffView.svelte";
  import MergePreviewView from "./MergePreview.svelte";
  import { api, inTauri } from "./api";
  import { stem } from "./format";
  import type { MergePreview, ScoreDiff, Snapshot, VariantStatus } from "./types";

  let {
    family,
    snapshots,
    onchanged,
    notify,
  }: {
    family: string;
    snapshots: Snapshot[];
    onchanged: () => void;
    notify: (text: string, kind?: "info" | "error") => void;
  } = $props();

  let board = $state<VariantStatus[]>([]);
  let loading = $state(false);
  let error = $state<string | null>(null);
  let busy = $state(false);

  // browser preview only: "#merge" opens the first variant's merge preview (screenshots)
  $effect(() => {
    if (!inTauri && location.hash === "#merge" && board[0] && merging === null) toggleMerge(board[0]);
  });

  // "New variant" form
  let making = $state(false);
  let mainPath = $state("");
  let newName = $state("");
  let fromBar = $state("");
  let toBar = $state("");

  // comparing one variant (its branch) with where it started
  let comparing = $state<string | null>(null);
  let compareDiff = $state<ScoreDiff | null>(null);
  let compareError = $state<string | null>(null);

  let tagDraft = $state<Record<string, string>>({});

  // merge preview of one variant with its main version
  let merging = $state<string | null>(null);
  let mergeResult = $state<MergePreview | null>(null);
  let mergeError = $state<string | null>(null);

  async function toggleMerge(b: VariantStatus) {
    if (merging === b.variant.branch) {
      merging = null;
      return;
    }
    merging = b.variant.branch;
    mergeResult = null;
    mergeError = null;
    if (!b.tip || !b.main_tip) return;
    try {
      const p = await api.mergePreview(family, b.main_tip, b.tip, b.fork_point);
      if (merging === b.variant.branch) mergeResult = p;
    } catch (e) {
      mergeError = String(e);
    }
  }

  // the files of this project, newest version first: what a variant can be made from
  let files = $derived.by(() => {
    const seen = new Map<string, Snapshot>();
    for (const s of snapshots) if (s.branches.length && !seen.has(s.path)) seen.set(s.path, s);
    return [...seen.values()];
  });

  async function load() {
    loading = true;
    error = null;
    try {
      const fam = family;
      const b = await api.variantBoard(fam);
      if (fam === family) board = b;
    } catch (e) {
      error = String(e);
    } finally {
      loading = false;
    }
  }

  $effect(() => {
    void family;
    void snapshots; // reload when new versions arrive (a variant may have been saved)
    load();
  });

  function startMaking() {
    making = true;
    mainPath = files[0]?.path ?? "";
    newName = "";
    fromBar = "";
    toBar = "";
  }

  async function make(open: boolean) {
    const name = newName.trim();
    if (!name || !mainPath) return;
    const bars = fromBar.trim() ? { from: fromBar.trim(), to: (toBar || fromBar).trim() } : null;
    busy = true;
    try {
      const r = await api.newVariant(mainPath, name, bars);
      notify(`Made ${stem(r.variant.file_name)}`);
      making = false;
      if (open) await api.openPath(r.path);
      onchanged();
      await load();
    } catch (e) {
      notify(String(e), "error");
    } finally {
      busy = false;
    }
  }

  async function update(b: VariantStatus, change: Parameters<typeof api.updateVariant>[2]) {
    try {
      const v = await api.updateVariant(family, b.variant.branch, change);
      board = board.map((x) => (x.variant.branch === v.branch ? { ...x, variant: v } : x));
    } catch (e) {
      notify(String(e), "error");
    }
  }

  function saveNotes(b: VariantStatus, value: string) {
    if (value !== b.variant.notes) update(b, { notes: value });
  }

  function addTag(b: VariantStatus) {
    const t = (tagDraft[b.variant.branch] ?? "").trim();
    if (!t || b.variant.tags.includes(t)) return;
    tagDraft[b.variant.branch] = "";
    update(b, { tags: [...b.variant.tags, t] });
  }

  async function toggleCompare(b: VariantStatus) {
    if (comparing === b.variant.branch) {
      comparing = null;
      return;
    }
    comparing = b.variant.branch;
    compareDiff = null;
    compareError = null;
    if (!b.tip || !b.fork_point || b.tip === b.fork_point) return;
    try {
      const d = await api.diff(family, b.tip, b.fork_point);
      if (comparing === b.variant.branch) compareDiff = d;
    } catch (e) {
      compareError = String(e);
    }
  }

  function bars(from: string, to: string) {
    return from === to ? `b.${from}` : `b.${from}–${to}`;
  }

  function isOutside(b: VariantStatus, flow: string, from: string, to: string) {
    return b.outside_range.includes(`${flow} ${from === to ? `b.${from}` : `b.${from}-${to}`}`);
  }
</script>

<section class="board scroll">
  <header>
    <div>
      <h2>Variants</h2>
      <p class="muted small">
        Alternatives of a cue, each its own file beside it. dorigit shows where each one differs from the version it was
        made from.
      </p>
    </div>
    {#if !making}
      <button class="primary" onclick={startMaking} disabled={!files.length}>New variant…</button>
    {/if}
  </header>

  {#if making}
    <form
      class="card make"
      onsubmit={(e) => {
        e.preventDefault();
        make(true);
      }}
    >
      <label>
        Make a variant of
        <select bind:value={mainPath}>
          {#each files as f (f.path)}
            <option value={f.path}>{stem(f.file_name)}</option>
          {/each}
        </select>
      </label>
      <label>
        Name
        <!-- svelte-ignore a11y_autofocus -->
        <input bind:value={newName} placeholder="e.g. horns, strings only, director's cut" autofocus />
      </label>
      <div class="range">
        <span>About bars <span class="muted">(optional)</span></span>
        <input bind:value={fromBar} placeholder="17" size="5" aria-label="from bar" />
        <span>to</span>
        <input bind:value={toBar} placeholder="32" size="5" aria-label="to bar" />
      </div>
      {#if newName.trim() && mainPath}
        <p class="muted small">
          Creates “{stem(files.find((f) => f.path === mainPath)?.file_name ?? "")} [{newName.trim()}].dorico” beside it.
        </p>
      {/if}
      <div class="actions">
        <button type="submit" class="primary" disabled={busy || !newName.trim()}>Make and open in Dorico</button>
        <button type="button" disabled={busy || !newName.trim()} onclick={() => make(false)}>Make</button>
        <button type="button" class="ghost" onclick={() => (making = false)}>Cancel</button>
      </div>
    </form>
  {/if}

  {#if error}
    <p class="error">{error}</p>
  {:else if loading && !board.length}
    <p class="muted">Loading…</p>
  {:else if !board.length && !making}
    <div class="empty muted">
      <p>No variants yet.</p>
      <p class="small">
        Try an idea without touching the cue: “New variant…” copies it to a file like “1m3 Chase [horns].dorico” and opens
        it in Dorico. Save as usual; the board shows the bars where it differs.
      </p>
    </div>
  {/if}

  {#each board as b (b.variant.branch)}
    <article class="card">
      <div class="title">
        <h3>{b.variant.name}</h3>
        <span class="muted small">{b.variant.file_name}</span>
        {#if b.variant.bars}
          <span class="pill given" title="The bars you said this variant is about">
            about {bars(b.variant.bars.from, b.variant.bars.to)}
          </span>
        {/if}
      </div>

      <div class="tags">
        {#each b.variant.tags as t (t)}
          <span class="pill tag">
            {t}
            <button
              class="x"
              title="Remove tag"
              onclick={() => update(b, { tags: b.variant.tags.filter((x) => x !== t) })}>×</button
            >
          </span>
        {/each}
        <input
          class="tag-input"
          placeholder="+ tag"
          bind:value={tagDraft[b.variant.branch]}
          onkeydown={(e) => e.key === "Enter" && addTag(b)}
          onblur={() => addTag(b)}
        />
      </div>

      {#if !b.tip}
        <p class="muted small">Its file has no history on this machine yet.</p>
      {:else if !b.differs.length}
        <p class="muted small">Same as where it started: no changes saved yet.</p>
      {:else}
        <div class="differs">
          {#each b.differs as f (f.flow)}
            <div class="flow">
              <span class="flow-name">{f.flow}</span>
              {#each f.ranges as r (r.from + r.to)}
                <span
                  class="pill range"
                  class:outside={isOutside(b, f.flow, r.from, r.to)}
                  title={`${r.changes} change${r.changes === 1 ? "" : "s"}: ${r.players.join(", ")}`}
                >
                  {bars(r.from, r.to)}
                  <span class="muted">· {r.players.slice(0, 2).join(", ")}{r.players.length > 2 ? ` +${r.players.length - 2}` : ""}</span>
                </span>
              {/each}
            </div>
          {/each}
        </div>
      {/if}

      {#if b.outside_range.length}
        <p class="warn small">Also changed outside its bars: {b.outside_range.join(", ")}</p>
      {/if}
      {#if b.main_changes_since > 0}
        <p class="muted small">
          The main version has {b.main_changes_since} change{b.main_changes_since === 1 ? "" : "s"} since this variant started.
        </p>
      {/if}

      <textarea
        rows="2"
        placeholder="Notes (e.g. what the director said)"
        value={b.variant.notes}
        onblur={(e) => saveNotes(b, (e.currentTarget as HTMLTextAreaElement).value)}
      ></textarea>

      <div class="actions">
        <button onclick={() => toggleCompare(b)} disabled={!b.tip}>
          {comparing === b.variant.branch ? "Hide changes" : "Show changes"}
        </button>
        <button onclick={() => toggleMerge(b)} disabled={!b.tip || !b.main_tip}>
          {merging === b.variant.branch ? "Hide merge preview" : "Merge preview with main"}
        </button>
        <button onclick={() => b.path && api.openPath(b.path)} disabled={!b.path}>Open in Dorico</button>
        <span class="muted small">{b.music_changes} musical change{b.music_changes === 1 ? "" : "s"}</span>
      </div>

      {#if merging === b.variant.branch}
        <div class="compare">
          {#if mergeError}
            <p class="error">{mergeError}</p>
          {:else if mergeResult}
            <MergePreviewView preview={mergeResult} oursLabel="main" theirsLabel={b.variant.name} />
          {:else if !b.main_tip}
            <p class="muted small">The main version has no history on this machine.</p>
          {:else}
            <p class="muted">Working out the merge…</p>
          {/if}
        </div>
      {/if}

      {#if comparing === b.variant.branch}
        <div class="compare">
          {#if compareError}
            <p class="error">{compareError}</p>
          {:else if compareDiff}
            <DiffView diff={compareDiff} notation={(flowId) => api.notationDiff(family, b.tip!, b.fork_point, flowId)} />
          {:else if b.tip === b.fork_point}
            <p class="muted small">No changes yet.</p>
          {:else}
            <p class="muted">Comparing…</p>
          {/if}
        </div>
      {/if}
    </article>
  {/each}
</section>

<style>
  .board {
    grid-column: 1 / 3;
    padding: 20px 24px 40px;
    display: flex;
    flex-direction: column;
    gap: 14px;
    max-width: 980px;
  }
  header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 16px;
  }
  h2 {
    margin: 0 0 4px;
    font-size: 20px;
  }
  h3 {
    margin: 0;
    font-size: 16px;
  }
  .small {
    font-size: 12px;
  }
  p {
    margin: 0;
  }
  .card {
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: var(--radius);
    box-shadow: var(--shadow);
    padding: 14px 16px;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .make label {
    display: flex;
    flex-direction: column;
    gap: 4px;
    font-size: 13px;
  }
  .range {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
    flex-wrap: wrap;
  }
  input,
  select,
  textarea {
    font: inherit;
    color: inherit;
    background: var(--panel-2);
    border: 1px solid var(--line);
    border-radius: 6px;
    padding: 6px 8px;
  }
  textarea {
    resize: vertical;
  }
  .title {
    display: flex;
    align-items: baseline;
    gap: 10px;
    flex-wrap: wrap;
  }
  .pill {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    border-radius: 999px;
    padding: 2px 10px;
    font-size: 12px;
    border: 1px solid var(--line);
    background: var(--panel-2);
  }
  .pill.given {
    background: var(--accent-soft);
    border-color: transparent;
    color: var(--accent);
  }
  .pill.range {
    background: var(--mod-soft);
    border-color: transparent;
  }
  .pill.range.outside {
    background: var(--amber-soft);
    outline: 1px solid var(--amber);
  }
  .tags {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    align-items: center;
  }
  .tag-input {
    border: 1px dashed var(--line);
    background: transparent;
    padding: 2px 8px;
    border-radius: 999px;
    font-size: 12px;
    width: 90px;
  }
  .x {
    border: none;
    background: transparent;
    padding: 0 0 0 2px;
    cursor: pointer;
  }
  .differs {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .flow {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    align-items: center;
  }
  .flow-name {
    font-size: 12px;
    font-weight: 600;
    margin-right: 4px;
  }
  .warn {
    color: var(--amber);
  }
  .error {
    color: var(--del);
  }
  .actions {
    display: flex;
    gap: 8px;
    align-items: center;
    flex-wrap: wrap;
  }
  .compare {
    border-top: 1px solid var(--line);
    padding-top: 10px;
  }
  .empty {
    padding: 24px 0;
    line-height: 1.6;
  }
</style>
