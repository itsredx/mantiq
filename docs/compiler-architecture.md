# Compiler Architecture

## Overview

The Mantiq / Nizam compiler is a **fully self-hosted compiler** written in **Nizam** (`src/*.nz`). It translates Mantiq and Nizam source code into LLVM Intermediate Representation (IR) and compiles it into native standalone executables using Clang/LLVM, with full tree-sitter CST parsing, two-pass semantic analysis, type inference & checking, borrow checking with auto-drop injection, rich multi-file diagnostics with error codes, and macro expansion.

```
Source text (*.nz, *.mq)
  │
  ▼
┌────────────────────────────────────────────────────────┐
│ 1. Tree-Sitter Parser (FFI C Binding)                  │
│    Source → Tree-Sitter CST (Concrete Syntax Tree)     │
└────────────────────────────────────────────────────────┘
  │
  ▼
┌────────────────────────────────────────────────────────┐
│ 2. CST Lowering & Macro Expansion (src/lower.nz)       │
│    Tree-Sitter CST → Nizam AST (Node / Span)           │
│    Hygienic macro expansion, strict mode validation    │
└────────────────────────────────────────────────────────┘
  │
  ▼
┌────────────────────────────────────────────────────────┐
│ 3. Semantic Analysis (src/sema.nz)                     │
│    Two-pass: declare_pass → resolve_pass               │
│    Symbol tables, lexical scoping, module loading,     │
│    closure capture detection, multi-file registration  │
└────────────────────────────────────────────────────────┘
  │
  ▼
┌────────────────────────────────────────────────────────┐
│ 4. Type Checking & Monomorphization (src/typecheck.nz) │
│    Bidirectional type inference, coercion rules,       │
│    generic struct/function monomorphization,           │
│    destination-driven literal type inference           │
└────────────────────────────────────────────────────────┘
  │
  ▼
┌────────────────────────────────────────────────────────┐
│ 5. Borrow Checking & Auto-Drops (src/borrowck.nz)      │
│    Move semantics state machine (Owned → Moved)        │
│    Use-after-move / use-after-drop verification        │
│    Scope auto-drop injection at block exits            │
│    Context manager (`with` stmt) lifecycle drop        │
└────────────────────────────────────────────────────────┘
  │
  ▼
┌────────────────────────────────────────────────────────┐
│ 6. LLVM IR Code Generation (src/codegen.nz)            │
│    AST → SSA LLVM IR text emission                     │
│    Struct/union memory layout, mangling, ABI calls,    │
│    closure environment boxing and function pointers    │
└────────────────────────────────────────────────────────┘
  │
  ▼
┌────────────────────────────────────────────────────────┐
│ 7. Native Linkage & Binary Generation (src/main.nz)    │
│    LLVM IR + C Runtime (runtime.c) + Tree-sitter FFI   │
│    Linked via zig cc / clang → Native Executable       │
└────────────────────────────────────────────────────────┘
```

---

## 1. Core Modules

| Module | Source File | Lines | Responsibilities |
| :--- | :--- | :--- | :--- |
| **AST & Symbols** | `src/symbols.nz` | ~2,000 | `Node`, `Span`, `Symbol`, `Scope`, `NodeType`, `PyObject`, `is_python_extern` |
| **Type System** | `src/types.nz` | ~250 | `Type`, `TypeKind` (including `PyObject`), copy vs move classification |
| **Target & Layout** | `src/layout.nz` | ~300 | Target abstraction (`Target`), 32-bit WASM vs 64-bit native vs `python-ext` (abi3) |
| **Tree-Sitter FFI** | `src/tree_sitter.nz` | ~100 | C FFI bindings to Tree-sitter parser, node navigation, and cursor API |
| **CST Lowering** | `src/lower.nz` | ~3,270 | CST to AST lowering, `extern[python]` blocks/inlines, decorators (`@nogil`), macros |
| **Semantic Analysis** | `src/sema.nz` | ~1,700 | Two-pass symbol declaration, module loading, closure capture, static GIL analysis |
| **Type Checker** | `src/typecheck.nz` | ~2,400 | Type validation, bidirectional inference, generic monomorphization, `PyObject` coercion |
| **Borrow Checker** | `src/borrowck.nz` | ~450 | Move analysis, use-after-move detection, deterministic auto-drop injection |
| **LLVM Codegen** | `src/codegen.nz` | ~14,500 | SSA LLVM IR emission, Vectorcall trampolines, `%PyTypeObject`, PEP 3118 buffer protocol, lazy callable caching |
| **Diagnostic Engine** | `src/error.nz` | ~1,070 | Box-drawing ANSI terminal renderer, multi-file source cache, error codes catalog |
| **CLI Driver** | `src/main.nz` | ~560 | Multi-target driver (`build`, `run`, `version`), `--target`, `--lib-dir`, `--profile`, native/WASI/CPython runners |
| **C Runtime** | `src/runtime.c` | ~2,250 | Task concurrency, hash table, string buffer utils, PEP 3118 buffer bridge, weak CPython C-API stubs |

---

## 2. Diagnostic Engine & Error Reporting (`src/error.nz`)

The compiler incorporates a state-of-the-art terminal diagnostic renderer inspired by modern compiler design (Rust/Clang), featuring:

1. **Standardized Error Codes Catalog**:
   - `[E0101]`: Undeclared variable or symbol.
   - `[E0102]`: Duplicate variable or symbol declaration.
   - `[E0103]`: Symbol not found in module.
   - `[E0201]`: Class usage in Nizam strict mode (`struct` required).
   - `[E0301]`: Unresolved type annotation.
   - `[E0308]`: Type mismatch in expression / assignment / return.
   - `[E0401]`: Use of moved variable (borrow checker).
   - `[E0402]`: Use of dropped variable.
   - `[E0403]`: Cannot borrow mutably.
   - `[E0501]`: Undefined macro invocation.
   - `[E0502]`: Macro argument count mismatch.
   - `[W0012]`: Unused variable warning.

2. **Box-Drawing Terminal Formatting**:
   - Adaptive terminal column width (`COLUMNS` environment variable or standard 80-120 columns).
   - Unicode box-drawing characters (`╭─`, `├─`, `│`, `╰─`).
   - Highlighted source code snippets with exact line and column numbers.
   - Caret underline markers (`▲▲▲▲▲`) pointing directly at erroneous spans.
   - Explanatory diagnosis sections (`💡 Why this happened`).
   - Actionable remediation hints (`⚡ How to fix`).
   - Optional compiler notes (`📌 Note`) and concrete replacement suggestions (`🔧 Suggested Fix`).

3. **Multi-File Source Cache**:
   - `DiagnosticEngine` caches the source text of all parsed files (`main.nz` and imported modules).
   - Resolves exact line and column slices without re-reading files from disk during error emission.

---

## 3. Multi-File Module Resolution (`src/sema.nz`)

1. **Module Import Pipeline**:
   - `import foo` or `from foo import bar, baz`.
   - `Sema.load_imported_module` locates `foo.nz` or `foo.mq` relative to the primary module or library directory (`--lib-dir`).
   - Registers the module source text with `DiagnosticEngine`.
   - Parses and lowers the module into an independent module AST.
   - Executes `declare_pass` and `resolve_pass` under an isolated module `Scope`.
   - Merges top-level module declarations into the root AST program for global codegen.

2. **Accurate Origin Spans**:
   - Each declaration and imported AST node retains its origin file path and local span coordinates.
   - Diagnostic reports accurately point to the imported file and exact line number when errors occur in dependencies.

---

## 4. Self-Hosting Bootstrap & IR Convergence

The Nizam compiler achieves **100% deterministic self-hosting convergence**:

$$\text{Stage 1 (Zig Reference Compiler)} \longrightarrow \text{Stage 2 (Nizam AOT Binary)}$$
$$\text{Stage 2} \longrightarrow \text{Stage 3} \longrightarrow \text{Stage 4} \longrightarrow \text{Stage 5}$$

- **Convergence Invariant**:
  `diff -u /tmp/nizam_stage4.ll /tmp/nizam_stage5.ll` yields **0 diff lines** (byte-for-byte identical LLVM IR).
- **Zero-Initialization Invariant**:
  `mantiq_malloc` in `src/runtime.c` uses `calloc` to guarantee zero-initialized memory for all AST node and symbol allocations, eliminating uninitialized pointer garbage.
- **Copy Semantics for Option**:
  `Option[T]` (`{ i8, ptr }`) is classified as a copy type in `src/types.nz`, preventing borrow checker auto-drop passes from emitting invalid `free()` operations on stack-allocated values.

---

## 5. Test Harness & Verification

The compiler contains a multi-tiered test harness validating all subsystems:

1. **Unit & Subsystem Test Suites (`src/tests/run_tests.sh`)**:
   - 14 foundational suites (`test_types.nz`, `test_abi.nz`, `test_std.nz`, `test_magic.nz`, `test_ast.nz`, `test_error.nz`, `test_macro.nz`, `test_sema.nz`, `test_borrowck.nz`, `test_ffi.nz`, `test_lower.nz`, `test_traverse.nz`, `test_utils.nz`, `test_codegen.nz`).
2. **Language Feature Integration Suites**:
   - Closures & Lambdas (`test_closures_lambdas.mq`), Downcasting & Reflection (`test_reflection_downcast.mq`), List Comprehensions (`test_list_comprehensions.mq`), String Interpolation (`test_string_interpolation.mq`), Channels & Actors (`test_channels_actors.mq`).
3. **WebAssembly Target Test Suites (`src/tests/wasm/run_wasm_tests.sh`)**:
   - 32-bit linear memory collections (`test_wasm_collections.nz`), classes & OOP dispatch (`test_wasm_classes.mq`), ABI layout parity (`test_wasm_abi.nz`).
4. **Python FFI Integration Suites (`src/tests/python/`)**:
   - Phase 1: Primitives & Vectorcall (`run_phase_1_tests.sh`)
   - Phase 2: Struct & Class type synthesis (`run_phase_2_tests.sh`)
   - Phase 3: PEP 3118 buffer protocol (`run_phase_3_tests.sh`)
   - Phase 4: Static GIL safety & `@nogil` (`run_phase_4_tests.sh`)
   - Phase 5: Embedded Python runtime (`run_phase_5_tests.sh`)
   - Phase 6: In-process packaging backend (`run_phase_6_tests.sh`)
   - Tier 2: Static typed `extern[python]` declarations (`run_extern_python_tests.sh`)

---

## 6. WebAssembly Target & Cloud Compiler Microservice

The compiler features full WebAssembly (`wasm32-wasi`) code generation and a dual-tier production deployment pipeline:

```
┌─────────────────────────────────────────────────────────────┐
│ 1. In-Browser Playground (Vercel Edge Static CDN)           │
│    • Pure static assets (index.html, studio.js, WASI VM)   │
│    • 12 precompiled WASM demo modules (0ms compile latency) │
│    • Live ANSI 24-bit TrueColor diagnostic terminal         │
│    • Interactive 32-bit linear memory hex inspector         │
└──────────────────────────────┬──────────────────────────────┘
                               │
               POST /api/compile (Proxied to Render)
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. Cloud Compiler Microservice (Render Docker Container)    │
│    • Native Linux x86-64 ELF nizam binary + tree-sitter .so │
│    • Pre-warmed Zig WASI libc & runtime.c cache             │
│    • Direct execution via child_process.execFile            │
│    • Peak RSS: 41 MB (96% reduction vs Node WASI 1,007 MB)  │
│    • Compilation latency: ~0.4s (93% reduction vs 6.0s)     │
└─────────────────────────────────────────────────────────────┘
```

### Key Architectural Optimizations
1. **Layout & Struct Realignment (`src/layout.nz`)**:
   Switches pointer sizes to 4 bytes (`i32`), adjusts alignment, and re-computes struct field offsets (`String`, `List`, closures, fat pointers) for 32-bit linear memory.
2. **Native Binary Worker Isolation**:
   Replaces nested Node WASI virtualization with direct invocation of the native Linux ELF `nizam` compiler binary, eliminating 444MB of V8 isolate overhead and OS `fork()` memory duplication.
3. **Pre-Warmed Sysroot Cache**:
   The compiler Docker image pre-compiles WASI `libc`, `compiler-rt`, and `runtime.c` during build time into `/opt/zig_cache`, ensuring zero runtime compilation overhead and preventing kernel OOM events on 512MB RAM free cloud tiers.

---

## 7. Bidirectional Python FFI Subsystem & C-Extension Generation

The compiler includes an end-to-end bidirectional Python Foreign Function Interface enabling seamless interoperation between Nizam and CPython:

```
┌───────────────────────────────────────────────────────────────────────────────┐
│                        Bidirectional Python FFI Engine                        │
├────────────────────────────────────────┬──────────────────────────────────────┤
│ 1. Nizam -> Python Extension (Export)  │ 2. Python -> Nizam Embedding (Import)│
├────────────────────────────────────────┼──────────────────────────────────────┤
│ • Flag: --target python-ext            │ • Syntax: extern[python] "mod":      │
│ • Standard: PEP 384 Limited API (abi3) │ • Syntax: import[python] mod as py   │
│ • Zero Python.h dependency             │ • Static pointer caching (@__cached) │
│ • Fast Vectorcall trampolines          │ • Type unboxing (f64, i64, bool, ...)│
│ • PEP 3118 zero-copy buffer protocol   │ • Weak C-API linkage in runtime.c    │
│ • Transitive static @nogil analysis    │ • Dynamic PyObject unboxing          │
└────────────────────────────────────────┴──────────────────────────────────────┘
```

### 1. PEP 384 Limited API (`abi3`) Generation (`--target python-ext`)
- Compiles Nizam code directly into standard C-extension shared libraries (`.abi3.so`) compatible across all Python 3.8+ versions without recompilation.
- Generates `%PyMethodDef`, `%PyModuleDef`, and `PyInit_<module>` entirely within SSA LLVM IR without requiring local Python headers (`Python.h`).

### 2. Struct & Class CPython Type Synthesis
- Generates native `%PyTypeObject` descriptors for Nizam structs and classes with `tp_members`, `tp_methods`, `tp_init`, `tp_new`, and `tp_dealloc`.
- Enables Python code to instantiate, inspect, and invoke methods on native Nizam types with zero wrapper boilerplate.

### 3. Shared-Ownership PEP 3118 Buffer Protocol
- Implements `bf_getbuffer` and `bf_releasebuffer` handlers for Nizam structs containing raw memory buffers.
- Permits zero-copy conversion into Python `memoryview` and NumPy `ndarray` types, maintaining reference-counted memory safety.

### 4. Transitive Static GIL Safety & `@nogil`
- The compiler sema pass enforces compile-time GIL independence: functions marked `@nogil` cannot touch Python runtime APIs or allocate managed objects.
- At the call boundary, the runtime invokes `Py_BEGIN_ALLOW_THREADS` and `Py_END_ALLOW_THREADS`, enabling multi-threaded CPU parallel execution across GIL boundaries.

### 5. In-Process Packaging Backend (`nizam_build`)
- Provides a PEP 517 standard build backend (`mantiq/python/nizam_build`) enabling pure `pyproject.toml` integration (`pip install .` / `python -m build --wheel`).
