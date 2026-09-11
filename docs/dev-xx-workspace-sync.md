# DEV-XX: Workspace Synchronization Engine & Root Artifact Matrix

## 1. Overview & Architectural Motivation

The Nizam and Mantiq project is structured as a multi-repository workspace spanning:
- **`mantiq/`**: The primary self-hosted compiler repository, standard library (`std/`), and diagnostic engine.
- **`mantiqz/`**: The Stage 1 Zig reference bootstrap compiler.
- **`stage3/`**: The native self-hosted compiler binary (`mantiq`) and runtime artifacts.
- **`stage4/`**: The bootstrapped WebAssembly compiler (`nizam.wasm`) and WASM modules.
- **`compiler-service/`**: The Docker container microservice deployed to Render / Cloud Run for live in-browser compilation.
- **`playground/`**: The static WebAssembly interactive studio deployed to Vercel Edge CDN.
- **System Environments**: User-local directories (`~/.local/bin`, `~/.local/lib/mantiq`) and system directories (`/usr/local/bin`, `/usr/local/lib/mantiq`).

Prior to this tooling, modifying core files such as `runtime.c`, `nizam_wasi.js`, standard library modules, or rebuilding native binaries required manual multi-destination copying. Inevitably, one or more targets became stale, leading to subtle bugs, broken deployments, or divergence between the CLI compiler and the cloud worker.

To eliminate human error and maintain 100% workspace parity, the project establishes a strict **Canonical ROOT (Source of Truth)** for every replicated asset, driven by an automated synchronization engine: `dev-sync.sh` (aliased as `dev-xx.sh`).

---

## 2. Canonical Root & Target Matrix

Every replicated asset belongs to exactly one canonical root. Edits must be made to the designated ROOT; `dev-sync.sh` propagates changes to all target directories.

```
┌─────────────────────────────────────────────────────────────┐
│                    Canonical ROOT Assets                    │
├──────────────────────────────┬──────────────────────────────┤
│ mantiq/runtime.c             │ C Runtime Library            │
│ mantiq/tree_sitter_helper.c  │ Tree-Sitter FFI Helper       │
│ stage3/libtree-sitter-...so  │ Dynamic Tree-Sitter Parser   │
│ mantiq/libtree-sitter-...a   │ Static Tree-Sitter Parser    │
│ ./nizam_wasi.js              │ Node.js WASI Preview 1 CLI   │
│ mantiq/std/                  │ Standard Library Modules     │
│ stage3/mantiq                │ Self-Hosted Compiler Binary  │
│ stage4/nizam.wasm            │ Bootstrapped WASM Compiler   │
└──────────────────────────────┴──────────────────────────────┘
                               │
                       ./dev-sync.sh
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                   Automated Target Sync                     │
├─────────────────────────────────────────────────────────────┤
│ • mantiq/src/runtime.c                                      │
│ • mantiqz/mantiq-compiler/src/runtime.c                     │
│ • stage3/runtime.c, compiler-service/mantiq/runtime.c       │
│ • compiler-service/bin/nizam, mantiq/nizam, mantiq/mantiq   │
│ • ~/.local/bin/nizam, ~/.local/lib/mantiq/                  │
│ • compiler-service/nizam_wasi.js, mantiq/nizam_wasi.js      │
│ • stage3/std, compiler-service/mantiq/std, compiler-service/std │
│ • mantiqz/std, ~/.local/lib/mantiq/std                      │
│ • compiler-service/stage4/nizam.wasm                        │
└─────────────────────────────────────────────────────────────┘
```

### Detailed Mapping Table

| Asset Category | Canonical ROOT (Source of Truth) | Automated Sync Targets | Verification Method |
| :--- | :--- | :--- | :--- |
| **C Runtime** | `mantiq/runtime.c` | • `mantiq/src/runtime.c`<br>• `mantiqz/mantiq-compiler/src/runtime.c`<br>• `stage3/runtime.c`<br>• `compiler-service/mantiq/runtime.c`<br>• `~/.local/lib/mantiq/runtime.c`<br>• `/usr/local/lib/mantiq/runtime.c` *(system)* | MD5 Checksum |
| **Tree-Sitter Helper** | `mantiq/tree_sitter_helper.c` | • `mantiq/src/tree_sitter_helper.c`<br>• `mantiqz/mantiq-compiler/zig-out/bin/tree_sitter_helper.c`<br>• `stage3/tree_sitter_helper.c`<br>• `~/.local/lib/mantiq/tree_sitter_helper.c`<br>• `/usr/local/lib/mantiq/tree_sitter_helper.c` *(system)* | MD5 Checksum |
| **Tree-Sitter Shared Library** | `stage3/libtree-sitter-mantiq.so` | • `mantiq/libtree-sitter-mantiq.so`<br>• `compiler-service/bin/libtree-sitter-mantiq.so`<br>• `~/.local/lib/mantiq/libtree-sitter-mantiq.so`<br>• `/usr/local/lib/mantiq/libtree-sitter-mantiq.so` *(system)*<br>• `/usr/local/lib/libtree-sitter-mantiq.so` *(system)* | MD5 Checksum |
| **Tree-Sitter Static Library** | `mantiq/libtree-sitter-mantiq.a` | • `stage3/libtree-sitter-mantiq.a`<br>• `compiler-service/mantiq/libtree-sitter-mantiq.a` | MD5 Checksum |
| **WASI Node Runner** | `./nizam_wasi.js` | • `mantiq/nizam_wasi.js`<br>• `compiler-service/nizam_wasi.js` | MD5 Checksum |
| **Standard Library** | `mantiq/std/` | • `stage3/std/`<br>• `compiler-service/mantiq/std/`<br>• `compiler-service/std/`<br>• `mantiqz/std/`<br>• `~/.local/lib/mantiq/std/`<br>• `/usr/local/lib/mantiq/std/` *(system)* | Directory Content MD5 |
| **Native Compiler Executables** | `stage3/mantiq` *(built via `./build.sh`)* | • `mantiq/nizam`<br>• `mantiq/mantiq`<br>• `compiler-service/bin/nizam`<br>• `~/.local/bin/nizam`<br>• `~/.local/bin/mantiq`<br>• `/usr/local/bin/nizam` *(system)*<br>• `/usr/local/bin/mantiq` *(system)* | MD5 (repo) & mtime/RPATH (user/system) |
| **WASM Compiler Module** | `stage4/nizam.wasm` | • `compiler-service/stage4/nizam.wasm` | MD5 Checksum |

---

## 3. CLI Command Reference (`./dev-sync.sh` / `./dev-xx.sh`)

The script is available at the workspace root and can be invoked either as `./dev-sync.sh` or through the `./dev-xx.sh` symlink.

### 1. Parity Audit / Dry Run (`--check` / `-c`)
Audits all root-to-target pathways without modifying any files on disk:
```bash
./dev-sync.sh --check
# or
./dev-xx.sh -c
```
- **Exit Code `0`**: All targets match their canonical roots with 100% parity.
- **Exit Code `1`**: One or more targets are missing, modified, or out-of-date.

### 2. Active One-Shot Synchronization (Default)
Synchronizes all out-of-sync targets, ensures executable permissions (`chmod +x`), and updates ELF `RPATH` on installed user binaries:
```bash
./dev-sync.sh
# or
./dev-xx.sh
```

### 3. Rebuild Compiler & Synchronize (`--build` / `-b`)
Executes `./build.sh` to compile a fresh `stage3/mantiq` executable and rebuild the tree-sitter libraries before synchronizing all binaries, runtime headers, and standard libraries:
```bash
./dev-sync.sh --build
```

### 4. Continuous File-Watcher Daemon (`--watch` / `-w`)
Monitors all canonical roots in real-time. When a developer saves a change in `runtime.c`, edits a file in `mantiq/std/`, or updates `nizam_wasi.js`, `dev-sync` detects the modification within milliseconds and synchronizes all targets automatically:
```bash
./dev-sync.sh --watch
```
*Note: Uses Linux kernel `inotifywait` when available, with an automatic sub-second polling fallback.*

### 5. WebAssembly Compiler Rebuild (`--wasm`)
Compiles `stage3/nizam.wasm` using the native compiler, bootstraps `stage4/nizam.wasm` via Node.js WASI, and synchronizes the resulting binary into `compiler-service/stage4/nizam.wasm`:
```bash
./dev-sync.sh --wasm
```

### 6. System-Wide Installation (`--system` / `-s`)
Propagates binaries and runtime libraries to root-level system paths (`/usr/local/bin` and `/usr/local/lib/mantiq`):
```bash
sudo ./dev-sync.sh --system
```

---

## 4. Developer Guidelines for Contributors

1. **Editing `runtime.c`**:
   - Always make your edits in `mantiq/runtime.c`.
   - Run `./dev-sync.sh` (or keep `./dev-sync.sh --watch` running in a separate terminal).
   - Never manually copy `runtime.c` into `stage3/` or `compiler-service/`.
2. **Modifying Standard Library Modules (`std/`)**:
   - Create or edit `.nz` files directly in `mantiq/std/`.
   - Run `./dev-sync.sh` to update `stage3/std/`, `compiler-service/mantiq/std/`, and the user's installed library.
3. **Updating the Compiler**:
   - Make source changes in `mantiq/src/*.nz`.
   - Run `./dev-sync.sh --build`. This rebuilds `stage3/mantiq` and updates `mantiq/nizam`, `compiler-service/bin/nizam`, and `~/.local/bin/nizam` in a single command.
4. **Validating Parity**:
   - Before submitting pull requests or committing, run:
     ```bash
     ./dev-sync.sh --check
     ```
   - Confirm that the output reports:
     ```
     ✔ [OK] Workspace is 100% synchronized! All targets match their canonical roots.
     ```
