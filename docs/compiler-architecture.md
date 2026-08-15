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
| **AST & Symbols** | `src/symbols.nz` | ~1,200 | `Node`, `Span`, `Symbol`, `Scope`, `NodeType` definitions, accessors, and setters |
| **Type System** | `src/types.nz` | ~180 | `Type`, `TypeKind`, primitive/composite types, copy vs move classification |
| **Tree-Sitter FFI** | `src/tree_sitter.nz` | ~100 | C FFI bindings to Tree-sitter parser, node navigation, and cursor API |
| **CST Lowering** | `src/lower.nz` | ~1,700 | Transforms Tree-sitter CST to typed AST, macro definition/invocation handling |
| **Semantic Analysis** | `src/sema.nz` | ~800 | Two-pass symbol declaration and resolution, module import loading, closure detection |
| **Type Checker** | `src/typecheck.nz` | ~1,100 | Type validation, type unification, generic monomorphization, literal inference |
| **Borrow Checker** | `src/borrowck.nz` | ~450 | Move analysis, use-after-move detection, deterministic auto-drop injection |
| **LLVM Codegen** | `src/codegen.nz` | ~6,350 | Generates SSA LLVM IR, type-to-LLVM mapping, struct layouts, function emission |
| **Diagnostic Engine** | `src/error.nz` | ~1,070 | Box-drawing ANSI terminal renderer, multi-file source cache, error codes catalog |
| **CLI Driver** | `src/main.nz` | ~230 | CLI entry point (`build`, `repl`, `run`), pipeline orchestration, native linker invocation |
| **C Runtime** | `src/runtime.c` | ~975 | Task actor concurrency, dictionary hash table, string utilities, memory management |

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

## 5. Test Harness & Verification (`src/tests/run_tests.sh`)

The compiler contains a comprehensive 14-suite test harness executed via `src/tests/run_tests.sh`:

1. `src/tests/test_types.nz`: Type representation, copy/move classification.
2. `src/tests/test_abi.nz`: C calling conventions, struct packing, FFI ABI.
3. `src/tests/test_std.nz`: Standard library `String`, `List`, `Dict`, `Option`.
4. `src/tests/test_magic.nz`: Magic methods (`__add__`, `__eq__`, `__len__`).
5. `src/tests/test_ast.nz`: AST node allocation, span propagation, data getters/setters.
6. `src/tests/test_error.nz`: DiagnosticEngine, box formatting, error codes, word wrapping.
7. `src/tests/test_macro.nz`: Macro expansion, hygienic identifier mangling, strict modes.
8. `src/tests/test_sema.nz`: Lexical scoping, duplicate detection, closure capture, monomorphization.
9. `src/tests/test_borrowck.nz`: Use-after-move detection, auto-drop injection, context manager drops.
10. `src/tests/test_ffi.nz`: Tree-sitter FFI bindings and CST traversal.
11. `src/tests/test_lower.nz`: Tree-sitter CST to Nizam AST lowering.
12. `src/tests/test_traverse.nz`: AST visitor and depth-first traversal.
13. `src/tests/test_utils.nz`: String utilities and helper functions.
14. `src/tests/test_codegen.nz`: LLVM IR generation and Clang validation.

**Result**: 14 / 14 suites pass with 100% parity across self-hosted builds.
