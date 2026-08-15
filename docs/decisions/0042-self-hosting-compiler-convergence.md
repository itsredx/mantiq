# ADR 0042: Self-Hosting Compiler Convergence & Memory Invariants

## Status
Accepted

## Context
A major milestone for a systems programming language compiler is full self-hosting. In a self-hosting compiler, compiler stage $N$ compiles the compiler source to produce stage $N+1$, and stage $N+1$ compiles the same source to produce stage $N+2$. Deterministic convergence requires that the generated LLVM IR at stage $N+1$ and stage $N+2$ are 100% byte-for-byte identical (`diff -u stage4.ll stage5.ll == 0`).

During self-hosting verification, several critical memory invariants and struct layout issues were uncovered that caused segmentation faults and non-deterministic IR output across stages.

## Decision
We established and verified key memory invariants across the compiler codebase and runtime:

### 1. Heap Zero-Initialization via `calloc`
- **Issue**: `mantiq_malloc` in `src/runtime.c` originally used `sys_malloc(size)`. Memory returned by `malloc` contained uninitialized heap garbage. When AST node data structs (e.g. `FunDeclData`) were allocated via `make[FunDeclData]`, pointer fields (such as `body`) contained garbage non-null pointers rather than `NULL` (`None`). Subsequent passes checking `if node_body(n) != None:` attempted to traverse invalid heap pointers, triggering segmentation faults.
- **Resolution**: Updated `mantiq_malloc` to use `calloc(1, size ? size : 1)`, guaranteeing all heap-allocated AST nodes and symbol records are cleanly zero-initialized.

### 2. Copy Semantics for `Option[T]` Values
- **Issue**: `Option[T]` is represented as a 16-byte struct `{ i8, ptr }`. In `src/types.nz`, `is_copy_type` originally inspected the option payload, marking `Option[String]` as a move type. Consequently, the borrow checker injected `auto_drops` for local `Option[String]` variables. In LLVM codegen, auto-drops emitted `mantiq_free(ptr %opt)`, passing the stack address or unaligned discriminator of the option struct directly to `free()`, causing `free(): invalid pointer` aborts.
- **Resolution**: Marked `TypeKind.Option` unconditionally as a copy type in `is_copy_type` (`src/types.nz`), ensuring option wrappers passed by value are never sent to `mantiq_free`.

### 3. Struct Field Registration Parity
- **Issue**: In `src/codegen.nz`, `Symbol` and `Scope` struct field index registrations omitted newer fields (`sym_type`, `resolved_type`, `closure_node`), causing GEP (GetElementPtr) field indexing offsets to misalign with struct definitions in `src/symbols.nz`.
- **Resolution**: Aligned all field registrations in `LLVMCodegen.init_type_layouts` with exact struct field ordering in `src/symbols.nz`.

### 4. Statement Temporaries Isolation
- **Issue**: In the reference Zig compiler (`mantiqz/mantiq-compiler/src/codegen.zig`), `statement_temporaries` were not cleared when entering a new `FunDecl`, causing temporary variables from preceding functions to leak into subsequent function prologues as undefined SSA values (e.g. `%t.78`).
- **Resolution**: Added `self.statement_temporaries.clearRetainingCapacity()` on entering and exiting `FunDecl` in `codegen.zig`.

### 5. Multi-Stage Bootstrap Fixpoint Verification
We established a strict 5-stage bootstrap test:
$$\text{Stage 1 (Zig reference compiler)} \longrightarrow \text{Stage 2 (AOT Nizam compiler)}$$
$$\text{Stage 2} \longrightarrow \text{Stage 3} \longrightarrow \text{Stage 4} \longrightarrow \text{Stage 5}$$
- `diff -u /tmp/nizam_stage4.ll /tmp/nizam_stage5.ll` verified 0 differences.
- Replaced `./nizam` with the verified converged Stage 5 binary.

## Consequences
- The compiler binary `./nizam` is completely self-hosted, independent, and produces deterministic, reproducible binaries.
- All 14 unit test suites in `src/tests/run_tests.sh` pass with 100% parity.
