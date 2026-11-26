# JIT Design (PROPOSED — not implemented)

Status: **design only**. No code in this plan has been written. This doc is
the engineering record; the research framing lives in `research/jit-design.md`.

## Current State (verified Nov 2026)

- The **legacy Zig compiler** (`mantiqz/mantiq-compiler/src/jit.zig`, 142
  lines) had a working JIT backend: *compile-link-load* — write snippet LLVM
  IR to `.ll`, `zig cc -shared -fPIC` → `.so`, `dlopen`, `dlsym("main")`,
  call, keep the handle. Cross-snippet visibility by passing **all previous
  `.so` files** as linker inputs. REPL architecture in Decision 0035
  (persistent arena/sema/typechecker state, synthetic `main` generation,
  snippet counter). Linkage-error handling in Decision 0020.
- The **self-hosted compiler** (`mantiq/src/`) has **no JIT and no `repl`
  command** — the CLI dispatch is `version | check | fmt | build | run`
  only. The REPL/JIT was never ported past the Zig bootstrap.
- Everything today is AOT: native ELF, wasm32-wasi, python-ext `.so`. `run`
  = `build` + immediate execute of the artifact.
- Codegen emits **textual IR** (StringBuilder → `.ll` file) and shells out to
  clang/zig via `system()`; the compiler binary does **not** link LLVM.

## Goals

1. Restore interactive execution on the self-hosted compiler: `nizam repl`
   (both LanguageModes, per Decision 0035's interface).
2. Keep every existing gate green (chain 50/50, wasm 9/9, zero-runtime 3/3).
3. Phased: land value early (port the proven dlopen design), then deepen.

## Non-Goals (for this plan)

- No wasm JIT. V8 tiering the wasm we emit already; a wasm-hosted JIT of
  native output is incoherent. JIT is **native-only**.
- No interpreter. The language has none, and adding one doubles the
  semantic surface (every borrowck/typecheck rule twice). Tiering starts
  from the AOT pipeline, not from an AST walk.
- No bytecode cache format change.

## Hard Constraints (discovered, not assumed)

1. **Bootstrap**: compiler source must keep compiling under the frozen
   bootstrap chain (`chain_stable.sh` → promote). Any new dependency must
   not break the 50-suite gate.
2. **stage3/stage4 are wasm**: the compiler-as-wasm cannot link libLLVM and
   has no `dlopen`. Any JIT support in `src/main.nz` must be **gated out of
   the wasm build** exactly like python-ext is today ("python FFI is
   64-bit-only" precedent, `src/main.nz` ~line 123).
3. **Textual IR**: codegen has no LLVM-C API usage. An in-process JIT must
   consume `.ll` text (LLVM-C: `LLVMCreateMemoryBuffer` +
   `LLVMParseIRInContext`) or stay out-of-process.
4. **Zero-runtime gates**: Gate A (native, 25080 B, 0 undefined runtime
   symbols) applies to *emitted programs*, not the compiler binary — but a
   JIT'd snippet must still satisfy the same overlay rules (F6 weak-linkage
   overlay) or `run`-mode parity breaks.
5. **Borrowck is per-function CFG**: NLL state does not survive snippet
   boundaries today. REPL cross-snippet loans (a borrowed global in
   snippet 3 used in snippet 7) are semantically uncharted — see research
   doc R2.

## Phased Plan

### J0 — Port the compile-link-load REPL (target: 1–2 slices)

Port `mantiqz jit.zig` semantics into the self-hosted tree, native-only:

- New `nizam repl [nizam|mantiq]` command in `src/main.nz`, gated off for
  wasm targets (constraint 2).
- Persistent objects across snippets, mirroring Decision 0035's table:
  arena (`mantiq_ast_alloc` region), `Sema` (+ `global_scope`), `TypeChecker`,
  globals map (`name -> llvm type string`), snippet counter.
- Per snippet: full pipeline → textual IR → `zig cc -shared -fPIC` (+ all
  previous `.so` files) → `dlopen` → `dlsym` synthetic entry → call.
- Synthetic `main` generation with `external global` decls for prior
  globals (port of Zig codegen 1052–1144 behavior).
- Fresh-eyes check on Decision 0020's failure classes (duplicate symbols
  across `.so`s, missing declares) with the *new* mangled-name scheme.
- Gate impact: none expected — the REPL is an additive CLI path; the 50
  suites don't exercise it. Add a smoke probe under `probes/`.

Exit criteria: `nizam repl` runs the Decision 0035 example session
(`1 + 1`, `let x = 42`, multi-line fn, macro) in both language modes;
native `run`/wasm/zero-runtime gates unchanged.

### J1 — Kill the per-snippet `zig cc` fork (1 slice)

The dominant REPL latency is the out-of-process clang invocation per
snippet. Two options, in preference order:

- **J1a — shared-object reuse**: keep the pipeline per snippet but batch
  into a persistent *session module*: accumulate IR text, only invoke
  clang when the user *executes* something. Fewer, larger `.so`s.
- **J1b — in-process LLVM-C ORC**: link `libLLVM` into the native driver
  (NOT stage4 — constraint 2), `LLVMParseIRInContext` on our own textual
  output, `LLVMOrcLLJIT` lookup + run. No fork, no file I/O. This is the
  real JIT; it is also where libLLVM's size/ABI cost lands on every native
  compiler build, which is why it is not J0.

Measure: snippet→result latency, p50/p95, before/after (J0 baseline vs
J1a vs J1b), session memory growth over 100 snippets.

### J2 — Incremental session state (1–2 slices)

- Redefinition support (0035 explicitly lacks it): shadow-or-error policy
  decision, likely shadow-with-warning, old symbol remains reachable via
  its versioned `.so`.
- Persistent compiled cache: reuse the existing `--cache-dir` machinery to
  key `.so`s by (snippet hash + session lineage), enabling session
  resume (`nizam repl --resume`).
- Cross-snippet `declare` accuracy: emit declares from the *sema symbol
  table*, not from textual scanning.

### J3 — Research tiering (paper-track, see research doc)

Hot-function tiering and checked fast paths for `Any` unboxing (F9): the
JIT can add the null-type-tag checks AOT must omit. This is the research
contribution, not a prerequisite for anything above.

## Risks

| Risk | Mitigation |
|---|---|
| libLLVM link bloats native driver, breaks wrap ulimit assumptions | J1b isolated behind a `--jit` build flag; dlopen libLLVM at runtime instead of linking |
| `.so` chaining explodes link time late in long sessions | batch per N snippets (J1a); cap `prev .so` count, archive older ones into one |
| Borrowck semantics differ REPL vs file mode | research doc R2 first; J0 ships with same-file semantics only |
| Frozen bootstrap rejects new main.nz code paths | all JIT code behind plain branches (no new grammar); chain gate reruns each slice |

## Decision Points Before Implementation

1. J1a vs J1b (measure J0 first; J1b only if p95 > 300 ms target).
2. Redefinition policy (J2).
3. Whether `repl` lands as `nizam repl` or a separate `nizam-jit` driver
   binary (avoids any main.nz/stage4 gating questions entirely).
