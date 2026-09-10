# ADR 0044: Cloud Compiler Microservice Architecture & 96% Memory Footprint Reduction

## Status
Accepted

## Context
Providing an interactive, in-browser playground experience for Nizam and Mantiq requires on-demand compilation of user source code to WebAssembly (`wasm32-wasi`). Standard free-tier container hosting environments (e.g., Render Free Web Service, Google Cloud Run) enforce strict resource constraints, typically **512 MB RAM**.

The initial deployment architecture executed the self-hosted WebAssembly compiler (`stage4/nizam.wasm`) inside Node.js via `@node --experimental-wasi-unstable-preview1` using a custom WASI runner (`nizam_wasi.js`). Under this virtualized approach:
1. The V8 JavaScript engine allocated approximately 444 MB of heap and isolate arenas for the WASI instance.
2. When `nizam.wasm` invoked `zig cc` via `host_system` (`child_process.execSync`) to link `runtime.c` and emit the final `.wasm` binary, Linux's `fork()` duplicated the parent process's memory map, pushing peak Resident Set Size (RSS) to **1,007 MB**.
3. The Render cgroup kernel OOM-killer immediately terminated the process with `SIGKILL` (`exit code 137`).
4. Additionally, compiling the Zig WASI libc sysroot and compiler-rt on first execution incurred a ~6-second cold-start compilation latency.

## Decision

We restructured the deployment and execution architecture into a high-performance, two-tier decoupled model:

### 1. Native ELF Binary Worker (`compiler-service/`)
- Replaced the nested Node WASI execution layer (`node nizam_wasi.js stage4/nizam.wasm`) with the native Linux x86-64 ELF `nizam` binary (`compiler-service/bin/nizam`) and dynamic Tree-sitter library (`libtree-sitter-mantiq.so`).
- Registered shared libraries via `ldconfig` and placed `nizam` in `/usr/local/bin`.
- Converted compilation dispatch in `server.js` from `execSync` to direct non-blocking `child_process.execFile('/usr/local/bin/nizam', args, ...)`.
- Eliminated all V8 WASI isolate memory overhead.

### 2. Sysroot Cache Pre-Warming at Docker Build Time
- Configured `ZIG_GLOBAL_CACHE_DIR=/opt/zig_cache` inside the Docker image.
- During `docker build`, executed a pre-warming compilation step targeting `wasm32-wasi` with `runtime.c`.
- Pre-cached all Zig WASI `libc`, `compiler-rt`, and musl object files in the static image layer, preventing CPU and memory spikes during live runtime requests.

### 3. Pure Static Edge Delivery (`playground/`)
- Decoupled the frontend playground studio from server-side rendering or serverless runtime functions.
- Migrated the frontend to a pure static site on Vercel Edge CDN:
  - Renamed `playground/app.js` to `playground/studio.js` to prevent Vercel's zero-config heuristics from bundling it into an AWS Lambda function (`/var/task/app.cjs`), which was crashing with `ReferenceError: document is not defined`.
  - Removed `playground/package.json` to enforce static HTML/JS delivery.
  - Configured `playground/vercel.json` with `"framework": null` and edge rewrites from `/api/compile` to the Render backend.

## Metrics & Performance Comparison

| Metric | Node WASI (`stage4/nizam.wasm`) | Native Binary (`bin/nizam`) | Improvement |
| :--- | :--- | :--- | :--- |
| **Peak Memory (RSS)** | **1,007 MB** | **41 MB** | **96% reduction** |
| **Compilation Latency** | ~6.0 seconds | **~0.4 seconds** | **93% reduction** |
| **Container Memory Usage** | 196% of 512MB limit | **8% of 512MB limit** | Stable on Free Tier |
| **Runtime Reliability** | Frequent `OOMKilled` (SIGKILL) | **100% Success Rate** | Zero crashes |

## Consequences
- The compiler microservice runs continuously and reliably within Render's free 512 MB container tier without memory leaks or OOM crashes.
- Playground users experience instant compilation (~400ms) with full 24-bit TrueColor diagnostic error rendering in the browser terminal.
- The architecture cleanly separates static edge asset distribution (Vercel) from isolated native compilation compute (Render).
