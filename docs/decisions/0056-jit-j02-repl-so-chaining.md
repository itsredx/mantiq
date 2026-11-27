# Decision 0056: JIT J0.2 — Cross-Snippet .so Chaining via Persistent ctypes Executor

Date: 2026-11-27
Status: Accepted
Context: JIT roadmap (`docs/jit-design.md` phase J0.2), slices 41–42 (0054, 0055)

## Problem

J0.1's REPL persists *declarations* by re-compiling the accumulated session
source, but *values* reset each snippet: every snippet's synthetic `@main`
re-initializes the globals it re-declares, and mutations executed by earlier
snippets are lost. Cross-snippet value persistence requires the earlier
snippets' code objects to stay alive and be the definitions later code binds
to.

## Options Considered

1. **Host-process dlopen via a C shim linked into the compiler** — a small
   `dlopen`/`dlsym`/call shim on the compiler's link line. Rejected: changes
   the compiler's own link line for every build, needs a new .c file wired
   through every build configuration (native, wasm, freestanding), and the
   dlopen bootstrap cost lands on the first snippet.

2. **JIT-compile the snippet IR in-process (LLVM-C or a hand-rolled
   interpreter)** — largest change, new dependency, deferred by design to
   J1+.

3. **Persistent executor child process + ELF shared objects** (chosen) —
   spawn one `python3` child per REPL session; per snippet, link the
   generated `.ll` as a shared object (`zig cc -shared -fPIC`) and hand the
   path to the child, which `ctypes.CDLL`s it and calls its synthetic
   `@main`. No compiler link-line changes, no shim files, no bootstrap lag.

## Design

### Executor child (start_repl)

- `pipe` ×2 → `fork` → `execvp("python3", ["-u", "-c", py_code])`.
  Child: stdin = command pipe (`.so` paths, one per line), stdout inherited
  (snippet `printf` output goes straight to the terminal), stderr = result
  pipe carrying `RC <n>` or `JITERR <msg>` lines.
- The child keeps every `.so` dlopen'd for the whole session — loaded
  objects are never unloaded, so their globals stay alive.
- SIGPIPE is ignored in the compiler host (`signal(13, SIG_IGN)`); an EPIPE
  write or EOF on the result pipe means the child died, and the session
  degrades gracefully (below).

### .so link (compile_source Phase 6.5)

When `repl_soshared` is set (only from the REPL when the executor is live),
the executable pipeline is short-circuited after IR write:

```
zig cc -O2 -shared -fPIC <snippet.ll> [<prev .so>...] -lm -lpthread -o <out.so> 2>&1
```

- **runtime.c / runtime.o are NOT linked.** The snippet IR already embeds
  the runtime glue (Milestone D, program-local IR); linking the C runtime
  produced duplicate-symbol errors (`nizam_set_target_ptr_size`,
  `format_llvm_float`, …). Redundant glue copies across the chain are
  harmless — interposition resolves them to the first-loaded copy.
- Previous `.so` paths are passed as link inputs. With `ld.lld`'s default
  `--as-needed` they usually do **not** appear as `DT_NEEDED` (each snippet
  re-defines the globals it references, so nothing is undefined for them to
  satisfy) — the chain is not load-bearing; the loader's global scope is
  (below).

### Interposition semantics (the load-bearing detail)

REPL-mode top-level globals are emitted with **default (external) ELF
linkage** (`repl_extern_globals` in codegen) instead of `internal`, so each
snippet's redundant definitions (`var x` re-emitted from accumulated source)
are *preemptible*: references go through the GOT and are resolved at load
time against the lookup scope.

The executor loads every `.so` with **`RTLD_GLOBAL`**. An `RTLD_LOCAL`
dlopen would search the new object *first* in its own scope, so each
snippet's fresh copy of `@x` would shadow the defining snippet —
mutations revert (the exact bug observed mid-implementation: `x=21 y=0`).
With `RTLD_GLOBAL`, every loaded `.so` joins the process-wide global scope
in load order, and lookup starts at the head: the **first-loaded
definition wins**. The defining snippet's copy is bound to for the rest of
the session; later snippets' identical definitions are shadowed dead data.

### Non-constant initializers

`repl_extern_globals` also makes the synthetic main *store* non-constant
initializers (`var z = count * 10`) at runtime — the global definition is
zeroinit and the store binds (by interposition) to the first-loaded copy of
that name, which is the current snippet's. Scalars only (i8/i16/i32/i64/i1/
float/double/ptr); aggregates keep their zeroinit limitation. File mode
(threshold 0) is fully unchanged.

### Failure handling

- Executor spawn failure (`fork`/`execvp` fails): the session runs J0.1
  executables as before.
- Mid-session child death: the EPIPE/EOF is detected (SIGPIPE ignored),
  the session prints a notice and **recompiles the current snippet as an
  executable** (the just-built `.so` is unusable), then continues on the
  J0.1 path.
- A snippet whose link or execution fails (`JITERR`, non-zero RC) is not
  accumulated — session state stays at the last good snippet.

## Verification

- Session test: `var x = 21` / `var y = x + 2` / `x = x + 1` /
  `printf(x, y, triple(x))` → `x=22 y=23 t=66` (mutations, cross-snippet
  reads, and functions from earlier snippets all persist).
- Function-mutation test: `fn inc() { count = count + 1 }` called from a
  later snippet → `a=1 b=2 count=2`, then `inc()` → `count=3`, with a
  non-const global `z = count * 10` reading persisted state (`z=20`).
- Executor-death test (PATH without python3): graceful
  `[repl: executor exited; falling back to executables]`, snippet still
  runs, exit codes preserved (rc=127/141 before the SIGPIPE fix → rc=0).
- `nm -D` on snippet `.so`s: globals exported as `D`/`B` with default
  visibility; `readelf -d` shows only `libc.so.6` NEEDED (as-designed —
  the global scope, not the DT_NEEDED chain, carries resolution).

## Consequences

- Cross-snippet value persistence works for scalar globals and
  global-mutating functions; string/aggregate globals still re-init
  (J1 candidates: richer value model, session-module batching for latency).
- The compiler host never links dlopen code; the only new runtime
  dependency is a `python3` on PATH (optional — degradation is clean).
- Redundant definitions in later `.so`s waste a few bytes each (dead data
  shadowed by interposition); acceptable at REPL scale, revisited in J1.
