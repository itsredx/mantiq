# WebAssembly (`wasm32-wasi`) Target & Runtime Architecture

## 1. Overview & Capabilities

The Mantiq / Nizam compiler supports compiling code directly to **WebAssembly System Interface (`wasm32-wasi`)**, featuring:

- **Target Architecture**: 32-bit WebAssembly linear memory (`wasm32-unknown-wasi`).
- **Complete Language Parity**: Full support for basic types, structs, enums, dynamic strings (`String`), heap-allocated dynamic collections (`List[T]`, `Dict[K, V]`), closures with heap capture, pattern matching, reflection, and OOP.
- **Cooperative Single-Threaded Concurrency**: Coroutine scheduler supporting `async fn`, `spawn`, `await`, and `Channel[T]` message passing without requiring `pthreads` or shared-memory WebAssembly threads.
- **Recursive Self-Hosted Compilation**: The Nizam compiler compiles itself to a standalone WebAssembly module (`stage3/nizam.wasm`), which runs under WASI and recursively compiles the compiler to produce `stage4/nizam.wasm`.
- **Dual Execution Environments**:
  1. **Node.js WASI**: High-performance CLI execution via `@node --experimental-wasi-unstable-preview1`.
  2. **In-Browser WebAssembly Studio**: Client-side execution via a pure JavaScript WASI Preview 1 engine with interactive terminal emulation, TrueColor ANSI colorizing, and linear memory hex inspection.

---

## 2. Target Layout Abstraction (`src/layout.nz`)

To cleanly support both 64-bit native platforms (x86_64, aarch64) and 32-bit WebAssembly, the compiler abstracts target properties in `src/layout.nz`:

```
┌────────────────────────────────────────────────────────┐
│ Target Configuration (src/layout.nz)                   │
├────────────────────────────────────────────────────────┤
│ • Pointer Width: 32-bit (WASM) vs 64-bit (Native)      │
│ • Size Type: i32 (WASM) vs i64 (Native)                │
│ • Struct Field Alignment & Padding Calculation         │
│ • Accurate GEP (GetElementPtr) Member Offsets          │
└────────────────────────────────────────────────────────┘
```

### 32-bit Data Layout Specifications

```llvm
target datalayout = "e-m:e-p:32:32-p10:8:8-p20:8:8-i64:64-n32:64-S128"
target triple = "wasm32-unknown-wasi"
```

| Type Category | Native (x86_64) Size | WASM (`wasm32-wasi`) Size | Alignment |
| :--- | :--- | :--- | :--- |
| `ptr`, `cstr`, references | 8 bytes | 4 bytes | 4 bytes |
| `usize`, `isize` | 8 bytes (`i64`) | 4 bytes (`i32`) | 4 bytes |
| `String` (`{ ptr, usize, usize }`) | 24 bytes | 12 bytes | 4 bytes |
| `List[T]` (`{ ptr, usize, usize }`) | 24 bytes | 12 bytes | 4 bytes |
| `Option[T]` (`{ i8, T }`) | 16 bytes (with 7-byte pad) | 8 bytes (with 3-byte pad) | 4 bytes |
| Closure fat pointer (`{ fn_ptr, env_ptr }`) | 16 bytes | 8 bytes | 4 bytes |
| `Any` fat pointer (`{ type_id, data_ptr }`) | 16 bytes | 8 bytes | 4 bytes |

### Target Struct in Nizam

```nizam
struct Target:
    public var triple as cstr
    public var pointer_size as i32
    public var is_wasm as bool

    public fn is_32bit(self as ptr[Target]) as bool:
        return (deref self).pointer_size == 4 to i32

    public fn llvm_size_type(self as ptr[Target]) as cstr:
        if self.is_32bit():
            return "i32" to cstr
        return "i64" to cstr
```

---

## 3. LLVM Intermediate Representation Generation (`src/codegen.nz`)

When compiling with `--target wasm32-wasi`, the code generator adapts IR emission:

1. **Target Triple & Header**:
   Emits the WebAssembly 32-bit datalayout and triple header at the top of every generated `.ll` module.
2. **Strict Direct Call Signatures**:
   WebAssembly 1.0 requires function pointers and direct calls to match parameter signatures exactly. Passing untyped integer literals (`0`) to functions expecting `i32` causes LLVM bitcast thunks that trap with `unreachable` at runtime in WASM. Codegen enforces strict 32-bit parameter promotion (`0 to i32`) for all standard library and runtime C FFI functions.
3. **Discriminator Offsets for `Option[T]`**:
   In `src/dce.nz` and `src/codegen.nz`, pointer-offset calculations for option values dynamically query target layout rather than hardcoding `+ 8` bytes, ensuring clean field indexing across 32-bit boundaries.
4. **Fat Pointers and Closures**:
   Closure environments and interface fat pointers are emitted as pairs of 32-bit pointers `{ ptr, ptr }` totaling 8 bytes.

---

## 4. WASI C Runtime Adaptation (`runtime.c`)

The runtime library (`runtime.c`) automatically adapts when compiled under `__wasi__`:

### Syscall Abstraction

```c
#if defined(__wasi__)
#define _WASI_EMULATED_PROCESS_CLOCKS
#include <wasi/api.h>
#endif
```

- **Standard I/O**: Directs `printf`, `puts`, `fwrite` to WASI `fd_write` (file descriptors 1 for stdout and 2 for stderr).
- **Filesystem Access**: File operations (`fopen`, `fread`, `fclose`) utilize WASI pre-opened directory trees (e.g. `.` and `/`).
- **Memory Allocator**: Allocations are handled through WASI linear memory (`malloc` / `calloc` / `free`) managed by standard `musl`/`dlmalloc` embedded inside `zig cc`'s wasi-libc sysroot.

### Cooperative Concurrency Scheduler

Because standard WebAssembly 1.0 does not support POSIX threads (`pthread`), `runtime.c` provides a **single-threaded cooperative coroutine scheduler**:

- **Coroutine Lifecycle**: `async fn` invocations create lightweight coroutine state records (`MantiqTask`) queued onto an event loop.
- **Yielding & Resumption**: When a task awaits a channel or another coroutine via `await`, it suspends execution and yields control back to the runner event loop.
- **Channels**: `Channel[T]` implements an in-memory bounded ring buffer. If a task reads from an empty channel, it yields until a producer pushes data.
- **Execution Model**: Deterministic, zero-overhead concurrency requiring no thread locks or atomic memory barriers.

---

## 5. Self-Hosted WASM Compilation & Bootstrapping

The Nizam compiler achieves recursive self-compilation targeting WebAssembly:

```
                  ┌─────────────────────────────────────┐
                  │ 1. Native Nizam Compiler            │
                  │    (x86_64-unknown-linux-gnu)       │
                  └──────────────────┬──────────────────┘
                                     │
                 compiles mantiq/src/main.nz --target wasm32-wasi
                                     │
                                     ▼
                  ┌─────────────────────────────────────┐
                  │ 2. Stage 3 Compiler (nizam.wasm)    │
                  │    Runs inside Node.js WASI         │
                  └──────────────────┬──────────────────┘
                                     │
                 compiles mantiq/src/main.nz inside WASI VM
                                     │
                                     ▼
                  ┌─────────────────────────────────────┐
                  │ 3. Stage 4 Compiler (nizam.wasm)    │
                  │    Fully bootstrapped WASM compiler │
                  └─────────────────────────────────────┘
```

### V8 Engine GC Tuning for Node.js WASI (Development CLI)

In Node.js v20 (V8 v11.3+), concurrent garbage collection triggers an assertion crash (`unreachable code`) inside `MarkCompactCollector::CollectGarbage` during dynamic linear memory growth (`memory.grow`). 

To execute the compiler reliably inside Node.js WASI for local testing, `nizam_wasi.js` configures:

```bash
node --no-incremental-marking --stack-size=16384 --max-old-space-size=384 nizam_wasi.js stage4/nizam.wasm [args...]
```

### Compiling with `nizam_wasi.js`

The runner script `./nizam_wasi.js` acts as a universal binary launcher for WASM binaries:

```bash
# Display compiler version
./nizam_wasi.js stage4/nizam.wasm version

# Compile a user program to WebAssembly under WASI
./nizam_wasi.js stage4/nizam.wasm build program.nz -o program.wasm --target wasm32-wasi --lib-dir mantiq

# Run the compiled WebAssembly binary
./nizam_wasi.js program.wasm
```

---

## 6. WebAssembly Studio & Cloud Compiler Architecture

The project features a dual-layer production architecture combining an in-browser studio with a containerized cloud compilation microservice.

```
Browser (Playground UI)
       │
       ├─► Vercel Edge CDN (100% Pure Static Site)
       │     ├─ index.html
       │     ├─ studio.js (UI state & editor engine)
       │     ├─ highlighter.js (Dual-syntax tokenizer)
       │     ├─ wasi_browser.js (In-browser WASI Preview 1 VM)
       │     └─ wasm/*.wasm (12 precompiled demo binaries)
       │
       ├─► Client-Side WASI Execution (0ms compilation, zero server required)
       │     └─ Instant execution of precompiled demos in WebAssembly VM
       │
       └─► Live Compilation (POST /api/compile)
             └─ Proxied by Vercel Edge to external Compiler Worker (Render / Cloud Run)
                 └─ Native Linux 'nizam' binary compiles code in ~0.4s (Peak RAM: ~41MB)
```

### 1. In-Browser WASI Engine (`playground/wasi_browser.js`)
- Implements WASI Preview 1 directly in vanilla JavaScript without external dependencies.
- Intercepts `fd_write` to forward `stdout` and `stderr` directly to the terminal DOM.
- Implements `clock_time_get`, `random_get`, `args_sizes_get`, `args_get`, and `proc_exit`.

### 2. Vercel Static Edge Migration
In default zero-config Node setups, Vercel automatically treats root files named `app.js`, `index.js`, or `server.js` as Express serverless functions (`/var/task/app.cjs`). Because browser DOM globals (`document`, `window`) do not exist in Node, this caused `ReferenceError: document is not defined` crashes.

**Resolution:**
- Renamed `playground/app.js` to `playground/studio.js`.
- Removed `playground/package.json` to inform Vercel that the repository is a pure static asset site.
- Added `playground/.vercelignore` to exclude development scripts (`dev_server.js`).
- Configured `playground/vercel.json` with `"framework": null` and edge rewrites.

### 3. Native Compiler Microservice & 96% Memory Reduction (`compiler-service/`)
When hosting on 512MB RAM free container tiers (Render, Cloud Run), running `stage4/nizam.wasm` inside Node WASI allocated 444MB of V8 arenas, which doubled to **1,007 MB** during `child_process.execSync` fork operations—crashing containers with `OOMKilled`.

**Resolution:**
- **Native Binary Execution:** Bundled the native Linux x86-64 ELF `nizam` binary and `libtree-sitter-mantiq.so` in `compiler-service/bin/`.
- **System Dynamic Linker:** Installed `nizam` to `/usr/local/bin` and registered the shared library via `ldconfig`.
- **Pre-warmed Toolchain:** Pre-compiled the Zig WASI libc, compiler-rt, and `runtime.c` during the Docker image build stage into `/opt/zig_cache`.
- **Direct Child Process Execution:** `server.js` invokes `nizam` directly via `execFile()`, dropping peak memory from **1,007MB to 41MB** (**96% memory reduction**) and latency from **6.0s to 0.4s**.

### Memory & Performance Comparison

| Execution Model | Peak RAM (RSS) | Compile Latency | 512MB Tier Status |
| :--- | :--- | :--- | :--- |
| **Node WASI (`stage4/nizam.wasm`)** | **1,007 MB** | ~6.0s | ❌ OOM Crashes (SIGKILL) |
| **Native Nizam Binary (`bin/nizam`)** | **41 MB** | **~0.4s** | ✅ 100% Stable (< 10% RAM) |

---

## 7. CLI & Development Commands Reference

### Building Programs for WebAssembly

```bash
# Using the native compiler (Recommended, fast, <50MB RAM):
./mantiq/nizam build hello.nz --target wasm32-wasi -o hello.wasm --lib-dir mantiq

# Using the self-hosted WASM compiler under Node WASI:
./nizam_wasi.js stage4/nizam.wasm build hello.nz --target wasm32-wasi -o hello.wasm --lib-dir mantiq
```

### Running WebAssembly Tests

```bash
# Run all dedicated WebAssembly test suites:
./mantiq/src/tests/wasm/run_wasm_tests.sh
```

### Launching the In-Browser Studio Locally

```bash
# Start the local development server:
node playground/dev_server.js

# Open in browser:
google-chrome http://127.0.0.1:8080/
```

