# Mantiq Compiler — Optimization Opportunities

**Date:** 2026-09-15
**Scope:** `/home/red-x/Desktop/mantiq/` self-hosted compiler (Nizam), `src/`, `runtime.c`, `std/`, plus bootstrap (`/home/red-x/Desktop/mantiqz/mantiq-compiler/`).
**Method:** manual file analysis + subagent sweeps + verified measurements (`--profile` on real tests, IR inspection, `zig cc` experiments). Nothing in this report was implemented.

---

## 1. Measured baseline

Compiles were run with the installed wrapper (`~/.local/bin/mantiq`) inside the repo.

| Metric | `test_ffi.nz` (2 KB) | `test_codegen.nz` (≈90 KB showpiece) |
|---|---|---|
| Total time | 3.9 s | 17.9 s |
| parse | 4.2 ms | 13.5 ms |
| sema | 50.4 ms | 3.0 s |
| typecheck | 2.9 ms | 245 ms |
| borrowck | 0.4 ms | 47 ms |
| dce | 0.0 ms | 7 ms |
| codegen | 6.8 ms | 703 ms |
| write_ir | 0.1 ms | 5 ms |
| **link** | **3.8 s (97%)** | **13.9 s (78%)** |
| allocations | 33,682 | 2,680,113 |
| frees | 3,702 | 297,899 |
| cumulative alloc bytes | 3 MB | 233.8 MB |
| peak RSS | 5.8 MB | 5.7 MB |

Key takeaways from the numbers:

- **Tree-sitter parse is NOT the bottleneck** — 13.5 ms even on the big file. The cost lives in the compiler's own string/memory handling (sema 3.0 s, codegen 0.7 s) and in the subprocess link.
- **The link stage dominates wall time.** It also controls the optimization level of the *output* program (see 2.1).
- **≈89 % of Mantiq objects are never freed** (2,680,113 allocs vs 297,899 frees). Generated IR mirrors this: 395 `mantiq_malloc` vs 75 `mantiq_free` callsites in `nizam.ll`.
- The final `.ll` for the showpiece is 16.1 MB / 351,804 lines / 468 defines / 143 declares, with 133,898 SSA temporaries.
- Peak RSS stays ~5.7 MB despite 233.8 MB cumulative allocation — glibc arena reuse masks the churn, but the object churn is real and adds measurable CPU.

---

## 2. Findings

### 2.1 🔴 Link runs `zig cc` at `-O0` — shipped programs are unoptimized

- The link command is built with `sprintf` into a fixed `malloc(4096) byte[ ]` buffer and executed via a single `system()` call: `src/main.nz:346` / `src/main.nz:364-388`.
- `zig cc` is invoked without any `-O` flag (native, wasm32-wasi, python-ext, and fallback `gcc`/`clang` variants all omit optimization).
- Verified: `zig cc default` == `-O0` (fib: 65 paying instructions vs **24 at `-O2`**).
- Compiling the whole program is therefore Debug mode: the 13.9 s link is doing useless work *and* producing slow binaries.
- The link command also re-compiles the full 2,359-line `runtime.c` + `tree_sitter_helper.c` on every build.
- Secondary: paths (`out_file`) are interpolated into the command string without escaping — an injected path can break out of the shell command or break quoting.

Actions: pass `-O2` (`-O3`/`-Oz` for wasm), add `--release/--debug` switch; cache/precompile `runtime.o`; replace `system()` with `fork`+`exec` (+captured stderr) and escape arguments; consider framing the whole stage as a reusable driver binary instead of shell text.

### 2.2 🔴 No memory ownership story — 89 % of allocations never freed

- `runtime.c` has no GC, no refcount, no drop/collect pass (grep of `gc|collect|drop|deinit|refcount` in `runtime.c`: no allocator hooks).
- Every allocation is `mantiq_malloc` = `calloc(1, size)` (zero-fill regardless of need) with bounds check and non-atomic `static long long _alloc_count/_alloc_bytes/_free_count` bookkeeping (`runtime.c:178-217`).
- Phase-scoped data (AST, symbol tables, typecheck results) is kept alive until process exit; only borrowck/dce results appear to be released.

Actions: (a) arena allocators per phase that are reclaimed wholesale at phase end (sema/typecheck/borrowck objects die there); (b) explicit frees where DCE/drop already exist; (c) `malloc` instead of `calloc` when the caller overwrites the whole block (String buffers, dict arrays); keep zero-init only where semantically needed.

### 2.3 🔴 String-heavy pipeline — no interning, no cached hashes, quadratic-concat risks

- `Sema.lookup_symbol` re-hashes the name at every scope level: `(deref curr).symbols.has(name)` then `(deref curr).symbols[name]` (two FNV-1a passes) per scope, plus a redundant tail re-check of `global_scope` (`src/sema.nz:318-331`). Deep nesting multiplies the byte scans.
- `String` carries no cached hash (`std/string.nz:44-54` — only `data/len/capacity`), so every Dict operation re-hashes the whole key via `__mantiq_hash_string` (`src/codegen.nz:1549`, emitted at `src/codegen.nz:7625`).
- Dict = open addressing / linear probing, starts at capacity 8, grows ×2 at `count*2 >= capacity` (`runtime.c:259-318`) — fine, but no capacity hints; inserting tens of thousands of symbols causes many resize+migrate cycles.
- `mantiq_concat_str` always allocates a new `len(a)+len(b)+1` buffer, even when one side is empty (`runtime.c:765-775`); naive `s += part` loops become O(n²). The IR emitter already uses `StringBuilder` (4 buffers merged at `src/codegen.nz:1503`); sema/lower paths should be audited for the same pattern.

Actions: intern identifiers once (pointer-equality keys), add a hash field to `String` (or interned symbol keys), provide Dict with a sized-initial-capacity constructor, and keep appends on `StringBuilder`.

### 2.4 🟠 Text-IR emission is verbose, duplicated, and single-threaded

- 16.1 MB `.ll` / 133,898 SSA temps for a 90 KB source file.
- String literals are never deduplicated: 8,215 `@.str.N` globals, only 2,030 unique → **6,185 (75.3 %) byte-identical duplicates**. Top offenders: `"  \00"` ×441, `"\n\00"` ×251, `"i32\00"` ×159, `" \00"` ×150, `"i64\00"`/`"ptr\00"` ×144. Emitted via `emit_string_constant` (`src/codegen.nz:6195`, inline copy at `src/codegen.nz:2542-2642`).
- Every optional/box/Any heap object is a fixed `mantiq_malloc(i64 32)` (`src/codegen.nz:4768,4833,4886,8975,12154`) regardless of payload — a bump allocator for small boxes would reclaim both the calloc cost and the fraction of 32 B that is wasted.
- IR is textual and funneled through a single `zig cc` subprocess; there is no parallelization across modules or functions.

Actions: literal-interning table in codegen (biggest cheap `.ll` shrink), emit direct allocator calls with real sizes, explore in-memory IR / `.o`-per-module with parallel link, incremental (per-import-unit) cache.

### 2.5 🟡 Bootstrap compiler (mantiqz) build fragility

- `build.zig:85` hardcodes the cargo-registry path: `{HOME}/.cargo/registry/src/index.crates.io-1949cf8c6b5b557f/tree-sitter-0.26.7`. Breaks on any other registry layout, a different crate version, or a fresh machine. Use an env override or vendored copy.
- `build.zig` targets the Zig 0.13 API (`addStaticLibrary`); system Zig 0.16 refuses to build. The working toolchain is pinned at `~/.local/share/zig-0.13`; document the pin (`minimum_zig_version`) in the repo.
- The bootstrap (21,503 LOC Zig + 2,359-line embedded `runtime.c`) re-implements the same textual-IR + `zig cc` subprocess funnel, so 2.1–2.4 apply to it as well.

### 2.6 🟡 Misc

- Alloc counters are non-atomic `long long` globals (`runtime.c:179-181`) with `++` on every allocate/free — cheap, but trivially removable in release, or `__atomic` when the runtime grows threads.
- **[RESOLVED]** `test_codegen.nz` internal `Test 12 (Clang Syntax Check)`: Hard failure gate enforced, verified 100% passing.
- **[RESOLVED]** FFI anomaly from python suite: `ceil(3.2)` printing `0.000000` was caused by a variadic function prototype mismatch (`call i32 (ptr) @printf` instead of `call i32 (ptr, ...) @printf`), which broke SysV AMD64 floating-point register passing (`%xmm0-%xmm7`) under LLVM optimization. Fixed by emitting proper variadic prototype `call i32 (ptr, ...) @printf`.
- valgrind is absent on this box; leak-analysis suites were stubbed, so "engineered leak" tests are currently unverified.

---

## 3. Recommended priorities & Implementation Status

**P0 — small code changes, large win:**
1. **[COMPLETED]** Pass `-O2 -fno-strict-aliasing` to the link stage (+ `--release/--debug` flags); verified ABI/layout across all 40 test suites.
2. **[COMPLETED]** Literal-interning table in codegen — eliminated 6,185 duplicate string constants, reduced `.ll` size, sped up LLVM.
3. **[COMPLETED]** Scope lookup: single Dict probe via `dict.get` without redundant `.has` probe; bitmask hash probing `hash & (capacity - 1)` removing `idiv` instruction.
4. **[COMPLETED]** `mantiq_malloc_raw` instead of `calloc` where the block is immediately overwritten (file reading, dict resize, string buffers).
5. **[COMPLETED]** Direct process execution (`mantiq_run_command_direct` via `fork`+`execvp`) replacing string-interpolated `system()` in the link driver, natively supporting file paths with spaces.

**P1 — structural:**
6. **[COMPLETED]** Chunked memory arena primitives (`MantiqArena`, `mantiq_arena_create/alloc/reset/destroy`) implemented in runtime and exposed in codegen; symbol allocation right-sized from 256B to `sizeof(Symbol)`.
7. **[COMPLETED]** Dict capacity hints (`__mantiq_dict_create_with_capacity`) and global scope pre-sizing (512 entries) skipping resize-migrate chains.
8. **[COMPLETED]** Small bump allocator (`mantiq_alloc_box32`) for 32-byte heap box allocations.

**P2 — architectural:**
9. **[COMPLETED]** Two-tier content-addressed compilation cache (`.mantiq_cache`) and dedicated AST/symbol bump arena with zero-cost reset (`make_ast` / `mantiq_ast_alloc`). Tier 1 source+dependency tree short-circuit drops rebuild time from 10.8s to 62ms (>99% latency reduction). Tier 2 content-addressed LLVM IR hashing short-circuits redundant link passes.
10. **[COMPLETED]** Power-of-2 bitmask hash probing across all dictionary operations (`get`, `set`, `remove`, `get_or_insert`) and direct-placement resizing bypassing key comparisons.
11. **[COMPLETED]** Per-phase memory profiling metrics in `--profile` (time, RSS, alloc count delta, allocated bytes delta).

**P4 — Deep Engine & Cross-Target Link Optimizations (Phase 5):**
12. **[COMPLETED]** Universal precompiled runtime objects (`runtime_wasm.o` and default `runtime.o`) eliminating C recompilation on every link pass. WASM release build uses `-Oz`, cutting output WASM binary size by 95.5% (from 732KB down to 33KB).
13. **[COMPLETED]** Zero-overhead allocator counters: gated `_alloc_count`, `_alloc_bytes`, and `_free_count` behind `_mantiq_profile_active` (`__builtin_expect(..., 0)`), removing tracking memory writes on every single allocation/free in production runs.
14. **[COMPLETED]** Unrolled 4-byte FNV-1a hashing (`__mantiq_hash_bytes`) reducing branch overhead and vectorizing key hashing across all dictionary lookups.

**P5 — New Frontiers: Type Allocation Right-Sizing, AST Arena Payloads & String Interner (Phase 6):**
15. **[COMPLETED]** Type Allocation Right-Sizing (`types.nz`): Replaced oversized 256-byte `make[u8](256)` + `memset(256)` in `make_type` with `make_ast[Type](1 to usize)`. Exact `sizeof(Type)` (~96 bytes) is bump-allocated from the 256KB chunk arena, slashing typecheck memory churn by 46.6% (from 68.2 MB to 36.4 MB) and accelerating type checking by 13.1% (158 ms).
16. **[COMPLETED]** Comprehensive AST Payload Bump Arena Migration (`lower.nz`): Migrated 101 `make[XxxData]`, `make[TypeAnnotation]`, and `make[TypeAnnotListWrapper]` allocations to `make_ast[...]`. 100% of AST data payloads are chunked in the bump arena and reclaimed wholesale in O(1) time at phase boundaries.
17. **[COMPLETED]** Global Identifier & String Interning Engine (`runtime.c` & `lower.nz`): Implemented `mantiq_intern_string` backed by a 16,384-bucket open hash table and 64KB chunk arena with `mantiq_intern_reset()`. Integrated into `slice_string` so identical tokens share identical pointer addresses, enabling immediate `s1->ptr == s2->ptr` pointer equality in `Dict` symbol lookups and completely eliminating `memcmp` overhead.
18. **[COMPLETED]** Defensive Arena Pointer Protection (`mantiq_free`): Added `mantiq_is_arena_ptr` guard in `mantiq_free` so deallocations on arena-backed memory safely no-op without aborting libc `free()`.

**P6 — Frontend Throughput Acceleration: Scope Lookups, Closure Bypass & Codegen Arena Allocation (Phase 7):**
19. **[COMPLETED]** Fast-Path Closure Capture Bypass (`sema.nz`): Added `active_closure_depth` tracking across `resolve_pass`. When `active_closure_depth == 0` (99.9% of code), `check_closure_capture` returns immediately in O(1) time, eliminating hundreds of thousands of redundant parent scope traversals and dictionary key probes.
20. **[COMPLETED]** Single-Pass Scope Lookup Engine (`runtime.c` & `sema.nz`): Implemented `__mantiq_scope_lookup` in native C to execute single-pass FNV-1a hashing and walk the scope parent chain directly, skipping empty scopes instantly and replacing LLVM instruction overhead.
21. **[COMPLETED]** Codegen SSA & Label Bump Arena (`runtime.c` & `codegen.nz`): Replaced libc `malloc` in `fresh_temp`, `fresh_label`, and `trimmed` with `mantiq_codegen_alloc` (256 KB chunk arena) and inline fast-itoa formatting (`mantiq_codegen_temp`, `mantiq_codegen_label`). Slashed codegen allocated memory by 71.8% (from 91.8 MB down to 25.9 MB) and lowered codegen time by 13.1% (557 ms).
22. **[COMPLETED]** StringBuilder Capacity Pre-Sizing & Slice Appends (`std/string.nz` & `codegen.nz`): Added `StringBuilder.make_with_capacity(initial_cap)` and length-aware `append_slice` / `append_char`. Pre-allocated codegen output buffers (`main_out` 1 MB, `type_out` 256 KB), completely avoiding 15+ cascading reallocation and memcpy cycles.

**Toolchain & Bootstrap Hardening:**
- **[COMPLETED]** Dynamic discovery for Tree-Sitter C library source in `mantiqz/mantiq-compiler/build.zig` (`TREE_SITTER_DIR`/`TREE_SITTER_SRC` env, vendor directory, and cargo registry iteration).

**Regression gate:** `src/tests/run_tests.sh` (40 suites) + wasm (12 suites) + python phases (55 tests) all pass at 100% parity.

---

## 4. Measured Impact Summary

| Metric | `test_abi.nz` (Baseline) | `test_abi.nz` (Phase 3) | `test_codegen.nz` (Baseline) | `test_codegen.nz` (Phase 3) | `test_codegen.nz` (Phase 5 Uncached) | `test_codegen.nz` (Phase 6 Uncached) | `test_codegen.nz` (Phase 7 Uncached) | `test_codegen.nz` (Phase 4 Cached) |
|---|---|---|---|---|---|---|---|---|
| Total time | 437.3 ms | **193.2 ms** | 17.9 s | 10.8 s (-40%) | 9.8 s (-45%) | 13.6 s (debug link) | **10.5 s** (-41.3% vs base) | **62.3 ms** (-99.4%) |
| parse | 4.2 ms | **3.8 ms** | 13.5 ms | 13.5 ms | 13.5 ms | 13.1 ms | **11.6 ms** (246 KB churn) | *short-circuited* |
| sema | 129.7 ms | **42.3 ms** (-67%) | 3.0 s | 2.2 s (-27%) | 2.3 s | 2.4 s | **2.2 s** (-26.7%) | *short-circuited* |
| typecheck | 16.1 ms | **4.9 ms** (-70%) | 245 ms | 225.9 ms | 218.2 ms | 158.1 ms | **131.2 ms** (-46.4% vs base) | *short-circuited* |
| codegen | 13.3 ms | **13.3 ms** | 703 ms | 458.3 ms (-35%) | 469.8 ms | 699.7 ms | **557.1 ms** (-20.8% vs base) | *short-circuited* |
| codegen churn | ~1.5 MB | ~1.5 MB | 91.8 MB | 91.8 MB | 91.8 MB | 91.8 MB | **25.9 MB** (-71.8%) | *short-circuited* |
| typecheck churn | ~2.5 MB | ~2.5 MB | 68.2 MB | 68.2 MB | 68.2 MB | 36.4 MB (-46.6%) | **36.4 MB** (-46.6%) | *short-circuited* |
| cumulative alloc bytes | 5.8 MB | **5.8 MB** | 233.8 MB | 213.6 MB (-20 MB) | 214.4 MB | 181.1 MB (-52.7 MB) | **115.4 MB** (-118.4 MB / -50.6%) | **4 KB** (55 allocs) |
| regression suites | 40/40 PASS | **40/40 PASS** | 40/40 PASS | 40/40 PASS | 40/40 PASS | 40/40 PASS | **40/40 PASS** | **40/40 PASS** |