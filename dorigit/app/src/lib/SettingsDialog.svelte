<script lang="ts">
  import { api, pickFolder } from "./api";
  import type { Settings, Status } from "./types";

  let {
    status,
    onclose,
    onsaved,
  }: { status: Status; onclose: () => void; onsaved: (s: Status) => void } = $props();

  // Edit a copy; nothing changes until Save (so capturing the initial value is intended).
  // svelte-ignore state_referenced_locally
  let s = $state<Settings>(structuredClone($state.snapshot(status.settings)));
  // svelte-ignore state_referenced_locally
  let thresholdMb = $state(Math.round((status.settings.playback.keep_if_under_bytes / 1024 / 1024) * 10) / 10);
  let saving = $state(false);
  let error = $state<string | null>(null);

  async function addWatch() {
    const d = await pickFolder("Watch this folder for saved Dorico projects");
    if (d && !s.watch_dirs.includes(d)) s.watch_dirs = [...s.watch_dirs, d];
  }

  async function chooseStore() {
    const d = await pickFolder("Where should dorigit keep history?");
    if (d) s.store_dir = d;
  }

  async function chooseRestore() {
    const d = await pickFolder("Where should restored versions be written?");
    if (d) s.restore_dir = d;
  }

  async function save() {
    saving = true;
    error = null;
    try {
      s.playback.keep_if_under_bytes = Math.round(thresholdMb * 1024 * 1024);
      onsaved(await api.saveSettings($state.snapshot(s)));
    } catch (e) {
      error = String(e);
    } finally {
      saving = false;
    }
  }
</script>

<div class="backdrop" role="presentation" onclick={onclose}>
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <div class="dialog" role="dialog" aria-modal="true" aria-label="Settings" tabindex="-1" onclick={(e) => e.stopPropagation()}>
    <h2>Settings</h2>

    <fieldset>
      <legend>Watching</legend>
      <label class="row"><input type="checkbox" bind:checked={s.auto_snapshot} /> Take a snapshot every time Dorico saves</label>
      <div class="list">
        {#each s.watch_dirs as d, i}
          <div class="item">
            <span class="path">{d}</span>
            <button class="ghost" onclick={() => (s.watch_dirs = s.watch_dirs.filter((_, j) => j !== i))}>Remove</button>
          </div>
        {:else}
          <div class="muted">No folders. Add your Dorico Projects folder.</div>
        {/each}
      </div>
      <button onclick={addWatch}>Add folder…</button>
      <p class="hint">Sub-folders are included. Paths containing {s.ignore.join(", ")} are ignored.</p>
    </fieldset>

    <fieldset>
      <legend>Playback state (VST plugins, mixer)</legend>
      <p class="hint">
        Playback data is large (often 10–25 MB with Kontakt) and changes on every save. The music itself costs only a few
        KB per version.
      </p>
      <label class="row">
        <input type="radio" bind:group={s.playback.mode} value="milestones" />
        <span><b>Keep when it matters</b> (recommended): milestones, the first version, whenever plugins are added /
          removed / swapped, and whenever it's under
          <input class="num" type="number" min="0" step="0.5" bind:value={thresholdMb} /> MB.</span>
      </label>
      <label class="row"><input type="radio" bind:group={s.playback.mode} value="always" /> <span><b>Keep on every save</b> (uses a lot of disk)</span></label>
      <label class="row"><input type="radio" bind:group={s.playback.mode} value="never" /> <span><b>Never keep</b> (restored versions use the nearest earlier copy, if any)</span></label>
    </fieldset>

    <fieldset>
      <legend>Storage</legend>
      <div class="kv">
        <span>History store</span>
        <span class="path">{s.store_dir}</span>
        <button onclick={chooseStore}>Change…</button>
      </div>
      <p class="hint">Avoid cloud-synced folders (OneDrive, Dropbox) for the store. Changing it starts a new, empty history there.</p>
      <div class="kv">
        <span>Restored versions</span>
        <span class="path">{s.restore_dir ?? "Next to the original file"}</span>
        <span class="btns">
          <button onclick={chooseRestore}>Change…</button>
          {#if s.restore_dir}<button class="ghost" onclick={() => (s.restore_dir = null)}>Reset</button>{/if}
        </span>
      </div>
    </fieldset>

    {#if error}<p class="error">{error}</p>{/if}
    <footer>
      <span class="muted small">{status.settings_path}</span>
      <button class="ghost" onclick={onclose}>Cancel</button>
      <button class="primary" disabled={saving} onclick={save}>Save</button>
    </footer>
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
    width: min(720px, calc(100vw - 48px));
    max-height: calc(100vh - 48px);
    overflow: auto;
    background: var(--panel);
    border-radius: 12px;
    box-shadow: var(--shadow);
    padding: 20px 24px;
  }
  h2 {
    margin: 0 0 12px;
    font-size: 18px;
  }
  fieldset {
    border: 1px solid var(--line);
    border-radius: var(--radius);
    padding: 10px 14px 12px;
    margin: 0 0 14px;
    display: flex;
    flex-direction: column;
    gap: 8px;
    align-items: flex-start;
  }
  legend {
    font-weight: 600;
    padding: 0 6px;
  }
  .row {
    display: flex;
    gap: 8px;
    align-items: baseline;
    line-height: 1.5;
  }
  .list {
    width: 100%;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .item,
  .kv {
    width: 100%;
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .kv > span:first-child {
    width: 140px;
    flex: none;
    color: var(--muted);
  }
  .path {
    flex: 1;
    min-width: 0;
    font-family: ui-monospace, "Cascadia Mono", Consolas, monospace;
    font-size: 12px;
    word-break: break-all;
  }
  .btns {
    display: flex;
    gap: 6px;
  }
  .num {
    width: 70px;
    padding: 2px 6px;
  }
  .hint {
    margin: 0;
    font-size: 12px;
    color: var(--muted);
    line-height: 1.5;
  }
  .error {
    color: var(--del);
  }
  footer {
    display: flex;
    gap: 8px;
    align-items: center;
    justify-content: flex-end;
  }
  footer .small {
    margin-right: auto;
    font-size: 11px;
  }
</style>
