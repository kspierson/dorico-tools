# Development setup

Two supported ways to build. WSL is how sessions 1–2 were done. Native Windows is needed for installers and for running `tauri dev` with hot reload.

## A. WSL / Linux (current setup)

> **Since 2026-10-29 (Project S):** the Cargo workspace is the **repo root** (`../Cargo.toml`,
> one `Cargo.lock`, one `target/`), shared with the engine crates in `../engine/crates`
> (`dorico-format` moved there). The toolchain scripts live in `../engine/scripts/`;
> `scripts/dev-env.sh` here forwards to them. Cargo commands work from any folder in the repo.

This WSL has no system C compiler and no sudo, so everything is installed in user space:

```sh
../engine/scripts/setup-wsl-toolchain.sh   # rustup (minimal) + Windows GNU target, zig 0.17, cargo-zigbuild, cc/ar shims
. scripts/dev-env.sh             # puts ~/.cargo/bin, zig, the shims, cmake/ninja and uv on PATH (run in each new shell)
```

What lives where (outside the repo):
- `~/.cargo`, `~/.rustup`: Rust toolchain (not added to your shell profile; `dev-env.sh` adds it per shell).
- `~/.local/opt/zig-x86_64-linux-0.17.0/`: zig.
- `~/.local/opt/zig-shims/{cc,gcc,c++,g++,ar}`: tiny scripts running `zig cc` etc. They drop `--target=…` (cc-rs passes LLVM triples zig rejects) and `-Wl,-O1`.
- `~/.cargo/bin/cargo-zigbuild`.

To remove all of it: `rustup self uninstall` and `rm -rf ~/.local/opt/zig-* ~/.local/opt/zig-shims`.

### Everyday commands

```sh
cargo test                                         # all crates except the app
cargo clippy -p dorico-format -p dorigit-core -p dorigit-cli --all-targets
cargo fmt --all                                    # rustfmt.toml: 120 columns
DORICO_SAMPLES="/mnt/c/Users/kspie/Documents/Dorico Projects" \
  cargo test -p dorico-format --release --test real_files
cargo run --release -p dorigit-cli -- diff OLD.dorico NEW.dorico
cargo run --release -p dorico-format --example playback_setup -- FILE.dorico

cd app && npm install && npm run check && npm run dev   # UI with mock data in a browser
```

The Tauri app can't be built for Linux here (needs webkit2gtk system packages). Build it for Windows instead:

### Windows build from WSL

```sh
scripts/build-windows.sh    # → dist/windows/{dorigit-app.exe, dorigit.exe, WebView2Loader.dll}
```

How it works:
- `cargo zigbuild --target x86_64-pc-windows-gnu` links with zig, so no Windows SDK or MSVC is needed.
- Tauri embeds the icon and manifest with a resource compiler. `embed-resource` looks for `x86_64-w64-mingw32-windres`. We set `RC_x86_64_pc_windows_gnu=scripts/zig-rc-as-llvm-rc`, an adapter that answers like llvm-rc and runs `zig rc`.
- GNU builds load `WebView2Loader.dll` at runtime (MSVC links it statically). The script copies it from the build dir (it comes from the `webview2-com-sys` crate).
- You can run Windows exes from WSL (interop), e.g. `dist/windows/dorigit.exe --help`. Pass Windows paths (`C:\…`). To pass env vars, list them in `WSLENV`.

### Screenshots of the UI without a desktop

```sh
cd app && npm run build && npx vite preview --port 4173 --host 127.0.0.1 &
"/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe" --headless=new --disable-gpu \
  --user-data-dir='C:\Users\kspie\AppData\Local\Temp\shots\profile' --window-size=1320,840 \
  --virtual-time-budget=4000 --screenshot='C:\Users\kspie\AppData\Local\Temp\shots\ui.png' http://127.0.0.1:4173/
# add --force-dark-mode --blink-settings=preferredColorScheme=0 for dark mode
```

## B. Native Windows (for installers and `tauri dev`)

1. Install [Rust](https://rustup.rs) with the default MSVC toolchain.
2. Install Visual Studio Build Tools with "Desktop development with C++".
3. Install Node.js LTS. (WebView2 is preinstalled on Windows 10/11.)
4. Clone or copy the repo to a Windows path (not `\\wsl$`), then:

```powershell
cd dorigit\app
npm install
npm run tauri dev      # hot-reloading app
npm run tauri build    # NSIS installer in target\release\bundle\nsis\ (repo root)
```

MSVC builds don't need `WebView2Loader.dll` beside the exe.

## Layout of the code

See [DESIGN.md](DESIGN.md) §2. Each crate's `lib.rs` / `main.rs` has a module-level doc comment explaining its part.
