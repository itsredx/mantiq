# Decision 0049: std.sys Native Platform Abstraction & C-Runtime Elimination

// ── Document Metadata ────────────────────────────────────────────────────────
// Number: 0049
// Title: std.sys Native Platform Abstraction & C-Runtime Elimination
// Status: Accepted Architecture Decision
// Supersedes: 0015-std-sys.md
// Related Decisions: 0010-target-assumptions.md, 0013-std-process.md, 0025-std-path.md,
//                    0031-abi-calling-convention.md, 0048-cfg-point-liveness-and-advanced-lifetimes.md
// Related Specs: 0031-std-sys-system-interface.md

---

## 1. Context

Early in Nizam's design, [Decision 0015 (std.sys Module & Platform APIs)](file:///home/red-x/hp/nizam-lang/mantiq/docs/decisions/0015-std-sys.md) defined a minimal, 5-function standard interface (`os`, `arch`, `getenv`, `setenv`, `unsetenv`). Under that early model, all platform queries were implemented by C helpers in `runtime.c` (`mantiq_sys_os`, `mantiq_sys_arch`, `mantiq_sys_getenv`, `mantiq_sys_setenv`, `mantiq_sys_unsetenv`), returning pointers to global static structs.

As the compiler and standard library matured through the **Runtime Elimination Initiative** (Milestone A migrating collections to `std/collections.nz`, Milestone B migrating memory allocators to `std/mem.nz`), this early architecture became a major operational bottleneck:

1. **The Phantom Module Defect**:
   `std/path.nz` was authored to import `os` via `from std.sys import os`, yet no `std/sys.nz` source file existed. Every module touching paths or platform detection either failed to resolve or relied on non-standard build-time shims.
2. **Proliferation of Unsafe `extern fn` in Compiler Source**:
   Because `std.sys` was missing, the self-hosted compiler driver (`src/main.nz`) declared more than 25 raw libc functions (`system`, `getpid`, `access`, `fork`, `execvp`, `_exit`, `waitpid`, `mkdir`, `open`, `close`, `read`, `write`, `clock_gettime`, `getrusage`, `mmap`, `munmap`) directly inside the compiler translation unit. Any user program requiring host interaction had to duplicate these raw declarations.
3. **C Runtime Bloat & Linux-Specific Hacks in `runtime.c`**:
   `runtime.c` retained extensive C code for system interaction:
   - `mantiq_process_args()` parsing `/proc/self/cmdline` using low-level Linux pseudo-filesystem file reads (brittle inside containers, chroot, and non-Linux targets).
   - Lines 2996–3021 (`Direct Process Execution`) implementing ad-hoc fork/execvp and Win32 process spawning.
4. **Sentinel Return Bug in Environment Lookups**:
   The legacy C helper `mantiq_sys_getenv` returned an empty string `""` when a variable was not set, making it impossible to distinguish between an unset variable and an environment variable explicitly set to empty (`VAR=""`).
5. **Command Injection Vulnerability (CWE-78)**:
   The compiler and user programs relied on `system(cmd as cstr)`, which invokes the command through a shell (`/bin/sh -c` or `cmd.exe /c`). Building command strings dynamically introduces catastrophic command injection risks.

---

## 2. Decision

We introduce **`std/sys.nz`** as a first-class, pure Nizam standard library module with **zero dependence on `runtime.c`**, establishing a unified, type-safe, multi-platform systems interface.

### 2.1 Pure Nizam Architecture with Zero C Runtime Dependencies
All platform capabilities are implemented directly in `std/sys.nz` using typed `extern fn` bindings to target libc / Win32 / WASI symbols:
- No helper functions in `runtime.c` are required.
- The compiled module emits pure LLVM IR declarations.
- Enables downstream dead-code elimination (DCE) and Link-Time Optimization (LTO) to inline trivial platform queries.

### 2.2 Dual-Signature Ownership Model (Decision 0025 Parity)
Following the dual-signature pattern established in `std.path` (Decision 0025):
- Every string-accepting function provides both a **by-value** variant (which takes ownership and deallocates the argument) and a **by-reference (`_ref`)** variant (which borrows `ptr[String]`):
  - `getenv(name as String) as Option[String]`
  - `getenv_ref(name as ptr[String]) as Option[String]`
  - `setenv(name as String, val as String) as Result[Void, SysError]`
  - `setenv_ref(name as ptr[String], val as ptr[String]) as Result[Void, SysError]`
- The by-value functions are thin zero-cost inline wrappers over the `_ref` functions that call `.deinit()` on their inputs, guaranteeing zero logic duplication.

### 2.3 Option & Result Semantics over Sentinel Values
- `getenv` returns `Option[String]` (`Some(val)` if set, `None` if unset).
- `setenv` and `unsetenv` return `Result[Void, SysError]`.
- All system failures map into typed `SysError` structs with clear categorization (`SysErrorKind`).

### 2.4 Injection-Safe Subprocess Spawning (`Command`)
- We introduce `struct Command` with a fluent builder pattern:
  ```nizam
  var cmd as Command = Command.new(String.make("clang" to cstr))
  cmd.arg(String.make("-O2" to cstr))
  cmd.arg(String.make("source.c" to cstr))
  let res = cmd.status()
  ```
- Subprocesses are spawned directly using `posix_spawnp` (POSIX) or `CreateProcessA` (Windows) without intermediate `/bin/sh` or `cmd.exe` shells, eliminating command injection vulnerabilities (CWE-78).
- Output streams can be captured into `ProcessOutput` buffers (`.output()`) or piped.
- `system(cmd)` remains available as a convenience wrapper for legacy scripts.

### 2.5 Multi-Target Platform Abstraction Strategy
`std.sys` dynamically branches according to the target triple:
- **POSIX (Linux, macOS, FreeBSD)**: Uses standard POSIX APIs (`getenv`, `setenv`, `getpid`, `posix_spawnp`, `clock_gettime`, `ioctl`, `nanosleep`).
- **Windows (Win32)**: Uses `kernel32.dll` and MSVCRT APIs (`GetEnvironmentVariableA`, `SetEnvironmentVariableA`, `GetCurrentProcessId`, `CreateProcessA`, `QueryPerformanceCounter`, `Sleep`).
- **WebAssembly (WASI)**: Uses WASI Snapshot Preview 1 intrinsics (`args_get`, `environ_get`, `proc_exit`, `clock_time_get`).

### 2.6 Startup Arguments Initialization Protocol
Rather than reading `/proc/self/cmdline` at runtime:
1. The compiler's code generator updates `@main` to accept `(argc as i32, argv as ptr[cstr])`.
2. `@main` invokes `__nizam_sys_init_args(argc, argv)` on startup, initializing an internal immutable `List[String]`.
3. If invoked in an environment where `@main` arguments are unavailable (e.g. dynamic libraries, custom runners), `std.sys.args()` seamlessly falls back to platform-specific query APIs (`GetCommandLineW` on Windows, `/proc/self/cmdline` on Linux).

---

## 3. Consequences

### 3.1 Positive Impacts
- **Resolves Broken Imports**: `std/path.nz` (`from std.sys import os`) now links against a genuine, self-contained standard library module.
- **Cleans Compiler Driver**: Removes 25+ raw `extern fn` libc declarations from `src/main.nz`, replacing them with structured imports (`from std.sys import Command, exit, pid, now_monotonic_ns`).
- **C-Runtime Shrinkage**: Eliminates ~200 lines of legacy C code from `runtime.c` (`mantiq_sys_*`, `mantiq_process_*`, lines 2996–3021).
- **Security & Reliability**: Eliminates shell command injection hazards across the entire toolchain and resolves the empty-vs-unset environment variable ambiguity.

### 3.2 Compliance & Migration Strategy
- **Phase 1 (Complete)**: Specifications (`0031-std-sys-system-interface.md`) and Decisions (`0049-std-sys-platform-abstraction-and-runtime-elimination.md`) recorded.
- **Phase 2**: Author `std/sys.nz` with dual signatures and multi-platform bindings.
- **Phase 3**: Update `std/path.nz` and `src/main.nz` to import from `std.sys`.
- **Phase 4**: Mark legacy `mantiq_sys_*` functions in `runtime.c` as `weak` with deprecation notices, ensuring existing binaries continue to link.
- **Phase 5**: Remove deprecated shims once self-hosting verification passes.

