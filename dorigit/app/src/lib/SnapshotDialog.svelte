<script lang="ts">
  // "Snapshot a file now": pick a file, optionally name the version as a milestone.
  import { pickDoricoFiles } from "./api";
  import { stem } from "./format";

  let {
    initialPath = null,
    onclose,
    onsave,
  }: {
    initialPath?: string | null;
    onclose: () => void;
    onsave: (path: string, milestone: string | null) => void;
  } = $props();

  // svelte-ignore state_referenced_locally
  let path = $state<string | null>(initialPath);
  let milestone = $state("");
  let asMilestone = $state(false);

  async function choose() {
    const [p] = await pickDoricoFiles();
    if (p) path = p;
  }

  function save(e: SubmitEvent) {
    e.preventDefault();
    if (!path) return;
    const name = milestone.trim();
    onsave(path, asMilestone && name ? name : null);
  }

  function onkey(e: KeyboardEvent) {
    if (e.key === "Escape") onclose();
  }
</script>

<svelte:window onkeydown={onkey} />

<div class="backdrop" role="presentation" onclick={onclose}>
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <div
    class="dialog"
    role="dialog"
    aria-modal="true"
    aria-label="Save a version now"
    tabindex="-1"
    onclick={(e) => e.stopPropagation()}
  >
    <form class="inner" onsubmit={save}>
      <h2>Save a version now</h2>
      <p class="muted small">
        dorigit already keeps a version every time you save in Dorico. Use this for a file outside your watched folders,
        or to mark the current state as a milestone.
      </p>

      <div class="file">
        {#if path}
          <span class="name" title={path}>{stem(path.split(/[\\/]/).pop() ?? path)}</span>
          <button type="button" class="ghost" onclick={choose}>Change…</button>
        {:else}
          <button type="button" onclick={choose}>Choose a Dorico file…</button>
        {/if}
      </div>

      <label class="check">
        <input type="checkbox" bind:checked={asMilestone} />
        Mark as a milestone
      </label>
      {#if asMilestone}
        <!-- svelte-ignore a11y_autofocus -->
        <input
          class="text"
          bind:value={milestone}
          placeholder="e.g. Sent to orchestrator, Director approved, Cut v3"
          autofocus
        />
        <p class="muted small">Milestones keep the full playback setup, so this version reopens exactly as it sounded.</p>
      {/if}

      <div class="actions">
        <button type="button" class="ghost" onclick={onclose}>Cancel</button>
        <button type="submit" class="primary" disabled={!path || (asMilestone && !milestone.trim())}>
          {asMilestone ? "Save milestone" : "Save version"}
        </button>
      </div>
    </form>
  </div>
</div>

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    background: rgb(0 0 0 / 35%);
    display: grid;
    place-items: center;
    z-index: 10;
  }
  .dialog {
    width: min(520px, calc(100vw - 48px));
    background: var(--panel);
    border-radius: 12px;
    box-shadow: var(--shadow);
    padding: 20px 24px;
  }
  .inner {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  h2 {
    margin: 0;
    font-size: 18px;
  }
  p {
    margin: 0;
  }
  .small {
    font-size: 12px;
    line-height: 1.5;
  }
  .file {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 12px;
    background: var(--panel-2);
    border: 1px solid var(--line);
    border-radius: var(--radius);
  }
  .name {
    flex: 1;
    min-width: 0;
    font-weight: 600;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .check {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .text {
    font: inherit;
    color: inherit;
    background: var(--panel-2);
    border: 1px solid var(--line);
    border-radius: 6px;
    padding: 8px 10px;
  }
  .actions {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
    margin-top: 4px;
  }
</style>
