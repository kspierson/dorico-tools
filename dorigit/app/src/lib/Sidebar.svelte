<script lang="ts">
  import { bytes, relative } from "./format";
  import type { Family, Status } from "./types";

  let {
    status,
    families,
    selected,
    busy,
    onselect,
    onimport,
    onsnapshot,
    onsettings,
  }: {
    status: Status | null;
    families: Family[];
    selected: string | null;
    busy: boolean;
    onselect: (id: string) => void;
    onimport: () => void;
    onsnapshot: () => void;
    onsettings: () => void;
  } = $props();

  let watching = $derived(status?.watching.length ?? 0);
  let problems = $derived(status?.watch_errors ?? []);
</script>

<aside>
  <header>
    <img src="/app-icon.png" alt="" class="logo" />
    <div>
      <div class="name">dorigit</div>
      <div class="muted small">history for Dorico</div>
    </div>
  </header>

  <div class="watch" class:off={!watching} title={status?.watching.join("\n") ?? ""}>
    <span class="light"></span>
    {#if !status}
      Starting…
    {:else if !status.settings.auto_snapshot}
      Auto-snapshots off
    {:else if watching}
      Watching {watching} folder{watching === 1 ? "" : "s"}
    {:else}
      Not watching any folder
    {/if}
  </div>
  {#each problems as p}
    <div class="problem">{p}</div>
  {/each}

  <div class="section-title">Projects</div>
  <nav class="scroll">
    {#each families as f (f.id)}
      <button class="family" class:active={f.id === selected} onclick={() => onselect(f.id)}>
        <div class="fname">{f.display_name || f.title || f.id}</div>
        <div class="muted small">
          {f.snapshot_count} version{f.snapshot_count === 1 ? "" : "s"} · {Object.keys(f.files).length} file{Object.keys(f.files).length === 1 ? "" : "s"} · {bytes(f.size)}
        </div>
        <div class="muted small">{relative(f.last_snapshot)}</div>
      </button>
    {:else}
      <div class="empty muted">
        No history yet. Save a project in Dorico (in a watched folder), or import existing files.
      </div>
    {/each}
  </nav>

  <footer>
    <button onclick={onimport} disabled={busy}>Import existing files…</button>
    <button onclick={onsnapshot} disabled={busy}>Save a version now…</button>
    <button class="ghost" onclick={onsettings}>Settings</button>
  </footer>
</aside>

<style>
  aside {
    display: flex;
    flex-direction: column;
    min-height: 0;
    background: var(--panel);
    border-right: 1px solid var(--line);
  }
  header {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 16px 16px 10px;
  }
  .logo {
    width: 34px;
    height: 34px;
  }
  .name {
    font-weight: 650;
    font-size: 17px;
    letter-spacing: 0.2px;
  }
  .small {
    font-size: 12px;
  }
  .watch {
    margin: 4px 16px 8px;
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
  }
  .light {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--add);
    box-shadow: 0 0 0 3px var(--add-soft);
  }
  .watch.off .light {
    background: var(--muted);
    box-shadow: none;
  }
  .problem {
    margin: 0 16px 8px;
    font-size: 12px;
    color: var(--del);
  }
  .section-title {
    padding: 10px 16px 6px;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    color: var(--muted);
  }
  nav {
    flex: 1;
    min-height: 0;
    padding: 0 8px;
  }
  .family {
    display: block;
    width: 100%;
    text-align: left;
    background: transparent;
    border: 1px solid transparent;
    padding: 8px 10px;
    margin-bottom: 2px;
  }
  .family:hover {
    background: var(--panel-2);
  }
  .family.active {
    background: var(--accent-soft);
    border-color: transparent;
  }
  .fname {
    font-weight: 550;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .empty {
    padding: 8px 10px;
    font-size: 13px;
    line-height: 1.5;
  }
  footer {
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 12px 16px 16px;
    border-top: 1px solid var(--line);
  }
</style>
