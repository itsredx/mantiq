# Specification 0030: Code Formatter & Canonical Syntax Representation

// ── Document Specification ──────────────────────────────────────────────────
// Number: 0030
// Title: Code Formatter & Canonical Syntax Representation
// Status: Canonical Specification
// Supersedes: N/A
// Related: 0011-type-system.md, 0014-control-flow.md, 0015-structs.md, 0025-classes-interfaces.md

---

## 1. Scope & Objectives

This specification defines the canonical, machine-enforceable formatting standard for the **Nizam** and **Mantiq** programming languages. It provides the formal reference for implementing the language formatter (`nizam fmt` / `mantiq fmt`) and establishes the exact lexical and syntactic layout transformations applied by the compiler toolchain.

---

## 2. Invariance & Correctness Guarantees

Any conforming implementation of the Nizam/Mantiq formatter MUST satisfy the following formal properties:

### 2.1 The Idempotence Criterion
$$\text{fmt}(\text{fmt}(S)) \equiv \text{fmt}(S) \quad \forall S \in \mathcal{L}_{\text{Nizam}} \cup \mathcal{L}_{\text{Mantiq}}$$
Formatting a source string once and formatting it a second time MUST yield an identical byte sequence.

### 2.2 AST Semantic Preservation
$$\mathcal{AST}(\text{fmt}(S)) \cong \mathcal{AST}(S)$$
The formatter is purely a trivia-normalizing transformation. Under no circumstances may the formatter alter:
- Node kind or expression precedence.
- Evaluation order of subexpressions.
- Variable bindings, symbol resolutions, or lifetime annotations.
- String literal contents or raw bytes.

### 2.3 Comment & Trivia Attachment
Every comment (line comment `//`, block comment `/* ... */`, and section banner `// ── ...`) MUST be attached to either a leading or trailing AST node and preserved with exact relative position.

---

## 3. Formatting Rules by Grammar Rule

### 3.1 Indentation & Whitespace
- **Unit**: Exactly 4 spaces (`0x20 0x20 0x20 0x20`). Tab characters (`0x09`) are rejected and normalized to 4 spaces.
- **Line Feed**: Strictly LF (`0x0A`). CR (`0x0D`) characters are stripped.
- **Trailing Whitespace**: Stripped from every line.
- **File Termination**: Exactly one terminating LF (`0x0A`).

### 3.2 Maximum Column Width
- **Hard Limit**: 100 UTF-8 columns.
- **Soft Target**: 88 UTF-8 columns.

### 3.3 Module Imports (`import_decl`)
Imports MUST be partitioned into three sorted groups separated by exactly 1 blank line:
1. Standard library modules (`import std.*`, `from std.* import ...`).
2. External and vendor bindings (`import vendor.*`, `link "..."`).
3. Local project modules (`import ...`, `from ... import ...`).

Within each group, import lines are sorted lexicographically. Within `from M import A, B, C`, symbol identifiers are sorted lexicographically.

### 3.4 Function Declarations (`fun_decl`)
- Modifiers MUST follow canonical order: `[access] [static] [extern|inline] [async] fn <name>(<params>) as <RetType>:`.
- If the parameter list fits within the column limit, it remains on a single line.
- If the signature exceeds the column limit:
  - Each parameter is placed on its own line indented 4 spaces.
  - A trailing comma is placed after the final parameter.
  - The closing parenthesis and return type annotation are placed on their own line matching the definition's indentation depth.

### 3.5 Type Annotations & Casts
- Type binding operator `as`: Exactly 1 space before and after (`name as Type`).
- Cast operator `to`: Exactly 1 space before and after (`expr to Type`).
- Lifetimes: `life[a] T` with no internal spaces.
- Raw pointers: `ptr[T]` with no space before `[`.
- Systems keywords: `ref expr` and `deref expr` MUST have exactly 1 space after the keyword.

### 3.6 Section Banners
Section banners MUST match the regular expression:
```
^\/\/ ── [A-Za-z0-9 _\-\/]+ ─+$
```
- Total length MUST equal 80 columns (or 75 columns where appropriate).
- Banners are preceded by 2 blank lines (unless at line 1) and followed by 1 blank line.

### 3.7 Color Literals (`color_literal`)
Hexadecimal color literals in Mantiq (`#RGB`, `#RRGGBB`, `#RRGGBBAA`) MUST be normalized to uppercase hex digits (`#1E1E2E`, `#FF5733`, `#CDD6F4`).

### 3.8 Declarative Collections & UI Trees
- Short collections fit inline: `[1, 2, 3]`, `{"a": 1, "b": 2}`.
- Nested or overflowing collections MUST break into multi-line lists with 4-space indentation, one element per line, trailing commas on every item, and the closing delimiter aligned with the initiating statement.
- The spread operator `...` MUST NOT contain spaces between the periods and the target expression: `...base_config`.

---

## 4. Exit Codes & Tooling Integration

The `nizam fmt` and `mantiq fmt` command-line interfaces MUST conform to standard Unix exit codes:
- `0`: Success (all files formatted or `--check` passed).
- `1`: Check failure (unformatted files found under `--check`, or diff exists).
- `2`: Syntax error encountered during parsing (file remains unchanged).
- `127`: Fatal I/O or filesystem error.

