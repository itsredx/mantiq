# ADR 0040: Diagnostic Engine & Standardized Error Codes Catalog

## Status
Accepted

## Context
Compilers often present cryptic, unstructured error messages that lack source context, line numbering, or actionable guidance. Developers spending time parsing unformatted output or searching for obscure compiler internals suffer high cognitive overhead. Furthermore, without standardized error identifiers, programmatic error parsing, tooling, and documentation lookup are difficult.

## Decision
We implemented a dedicated **Diagnostic Engine** (`src/error.nz`) and a **Standardized Error Codes Catalog** integrated directly into the self-hosted Nizam compiler pipeline (`Sema`, `TypeChecker`, `BorrowChecker`, and `LLVMCodegen`).

### 1. Diagnostic Architecture
The `DiagnosticEngine` struct manages:
- **Multi-File Source Text Cache**: In-memory mapping (`Dict[String, String]`) of loaded file contents to extract exact lines and spans on demand without redundant disk I/O.
- **Terminal Dimensions & Word Wrapping**: Adaptive width computation (`COLUMNS` environment variable or standard 80–120 columns). Automatic word wrapping at whitespace boundaries for long explanation and remediation text, enclosing each line inside vertical box borders (`│ ... │`).
- **Unicode Box Drawing**: Structured presentation using standard box characters:
  - Top header: `╭─ ✖ ERROR [E0308] : <message> ──╮`
  - File path & position: `│ 📁 File: <path> │` and `│ 📍 Position: Line L, Column C │`
  - Divider: `├─────────────────────────────────┤`
  - Source snippet with line numbers and caret marker:
    ```text
    │   2 │ let count as i32 = "42" │
    │ │ ▲▲▲▲ │
    │ │ mismatched types: expected `i32`, found `String` │
    ```
  - Explanation block: `├─ 💡 Why this happened ───────────┤`
  - Remediation block: `├─ ⚡ How to fix ─────────────────┤`
  - Note block: `├─ 📌 Note ───────────────────────┤`
  - Suggested fix block: `├─ 🔧 Suggested Fix ──────────────┤`
  - Bottom border: `╰─────────────────────────────────╯`

### 2. Error Codes Taxonomy
Error codes are partitioned into standardized ranges:
- **`[E0101] - [E0199]` Scope & Symbol Resolution**:
  - `E0101`: Undeclared variable / identifier.
  - `E0102`: Duplicate variable / function / struct declaration.
  - `E0103`: Symbol not found in imported module.
- **`[E0201] - [E0299]` Language Modes & Strictness**:
  - `E0201`: Class usage in Nizam strict mode (`struct` required).
- **`[E0301] - [E0399]` Types & Coercion**:
  - `E0301`: Unresolved type annotation.
  - `E0308`: Type mismatch in expression / assignment / return.
- **`[E0401] - [E0499]` Ownership & Borrow Checking**:
  - `E0401`: Use of moved variable.
  - `E0402`: Use of dropped variable.
  - `E0403`: Cannot borrow mutably.
- **`[E0501] - [E0599]` Macros**:
  - `E0501`: Undefined macro invocation.
  - `E0502`: Macro argument count mismatch.
- **`[W0001] - [W0099]` Compiler Warnings**:
  - `W0012`: Unused variable.

## Consequences
- **User Experience**: Every compiler error clearly shows the exact source line, explains why the error occurred, and provides actionable remediation guidance.
- **Tooling**: IDEs and build systems can parse error codes `[E0xxx]` for precise diagnostics integration.
- **Maintainability**: Centralized error formatting logic in `src/error.nz` prevents inconsistent `printf` error messages scattered throughout compiler passes.
