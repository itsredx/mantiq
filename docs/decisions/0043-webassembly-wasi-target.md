# ADR 0043: WebAssembly WASI Target Support & In-Browser Self-Hosting

## Status
Accepted

## Context
Deploying Nizam and Mantiq programs to serverless edges, isolated sandboxes, and modern web browsers requires targeting WebAssembly. Prior to this decision, the compiler exclusively assumed 64-bit native architectures (`x86_64`, `aarch64`), with 8-byte pointer widths, 64-bit `usize`/`isize`, POSIX threads (`pthread`), and platform-dependent system calls.

Supporting WebAssembly (`wasm32-wasi`) required addressing:
1. 32-bit linear memory layout and struct alignment differences.
2. Direct system call abstraction under WASI Preview 1.
3. Concurrency runtime execution without POSIX threads or shared-memory atomics.
4. Self-hosted compilation fixpoint verification inside WebAssembly runtime environments.
5. In-browser client-side execution and interactive debugging.

## Decision

We designed and implemented a full WebAssembly target abstraction layer and execution pipeline:

### 1. Target Abstraction Layer (`src/layout.nz`)
- Defined a first-class `Target` struct encapsulating pointer size (4 bytes for WASM, 8 bytes for native), size types (`i32` vs `i64`), and target data layout string (`e-m:e-p:32:32-p10:8:8-p20:8:8-i64:64-n32:64-S128`).
- Standardized composite layout calculations (`String`, `List`, `Dict`, closures, fat pointers) to dynamically adjust padding, field offsets, and GEP indices based on target pointer width.

### 2. WASI C Runtime Adaptation (`runtime.c`)
- Implemented `#if defined(__wasi__)` conditional bindings with `-D_WASI_EMULATED_PROCESS_CLOCKS`.
- Redirected file and console I/O through WASI Preview 1 system calls (`fd_write`, `fd_read`, `args_get`).
- Designed a cooperative single-threaded coroutine scheduler (`async fn`, `spawn`, `await`, `Channel[T]`) on top of an event loop, enabling full asynchronous concurrency without requiring `pthread` support in WebAssembly.

### 3. Strict Function Signature Enforcement
- Enforced strict 32-bit type promotions (`0 to i32`) for integer parameters passed to C FFI functions to eliminate LLVM bitcast call thunks that trap with `unreachable` at runtime in WebAssembly 1.0.

### 4. Recursive Self-Hosted Bootstrapping (`stage3` -> `stage4`)
- Compiled the self-hosted Nizam compiler to `stage3/nizam.wasm` using the native compiler.
- Solved V8 concurrent garbage collection crashes during dynamic linear memory expansion (`memory.grow`) by tuning Node.js execution flags (`--no-incremental-marking --stack-size=65536 --max-old-space-size=4096`).
- Successfully executed recursive compilation inside Node.js WASI to produce `stage4/nizam.wasm`, which compiles and runs the complete WASM test suite.

### 5. In-Browser WASI Studio & TrueColor ANSI Diagnostics
- Developed a zero-dependency in-browser WASI Preview 1 implementation (`playground/wasi_browser.js`).
- Built an interactive studio with a 24-bit TrueColor Catppuccin ANSI-to-HTML parser, live 32-bit linear memory hex inspector, and interactive demo suite.
- Provided a local bridge (`POST /api/compile`) allowing in-browser code to be compiled on demand by the self-hosted `stage4/nizam.wasm` compiler.

## Consequences
- The compiler can target native 64-bit systems and 32-bit WebAssembly with zero code changes in user programs.
- The entire native test suite continues to pass with 100% parity (40/40 test suites passing).
- Nizam programs can be compiled and executed directly inside modern web browsers with microsecond execution times and visual memory inspection.
