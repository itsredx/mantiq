# Decision 0051: Struct-Literal Field Validation (E0315 / E0308)

## Context

Struct construction uses plain call syntax — `P(x = 1, y = 2)` (named) and
`P(1, 2)` (positional) — with the ctor emitter splicing each argument into the
aggregate via `insertvalue`. Two failure classes escaped semantic analysis and
surfaced as raw LLVM errors instead of proper diagnostics:

- **Unknown named field** (`P(x = 1, w = 2)`) or **out-of-range positional
  slot** (`P(1, 2, 3)` on a 2-field struct): codegen emitted
  `insertvalue ... , N` with N past the field count →
  `invalid indices for insertvalue` from clang, with no file/span context.
- **Field/value type disagreement** (scalar field given an aggregate value, or
  vice versa): codegen emitted the value register with the wrong LLVM type →
  `%t.N defined with type '%Q = type { i32 }' but expected 'ptr'`.

Both were diagnosed late (LLVM assembly stage), produced confusing messages,
and bypassed the E-code diagnostic contract.

## Decision

Add validation in the TypeChecker's struct-ctor branch
(`callee_t.kind == TypeKind.Struct` in the CallExpr path of `src/typecheck.nz`):

1. **Unknown named field → E0315** (`field \`w\` not found in struct \`P\``).
2. **Out-of-range positional slot → E0315** (`struct \`P\` has no field at
   position N (it has M)`).
3. **Clear field/value type disagreement → E0308** (`field \`y\` of struct
   \`P\` expects X, got Y`), via a new `is_numeric_type_kind` helper.

Gating conditions, each empirically necessary:

- **`sd_validate38`**: validation runs only when the symbol's `decl_node` is a
  real `NodeType.StructDecl`. Builtin collections (Dict/List/String) register
  symbols with the *import node* as decl_node, so a naive field scan counts 0
  fields and false-positives on `Dict()` / `String(s)` with E0315.
- **`sd_is_generic22`**: skip the E0308 compat check when the ctor call
  carries explicit type annotations (`Tuple2[K, V](v0 = ...)`) — the
  template's field types are type parameters (`A`/`B`), not concrete types, so
  any comparison reports nonsense ("expects A, got K").
- **Unknown/Any value types degrade silently** — inference gaps must not
  produce false mismatches.

## Non-Decision: Missing-Field Check (E0317) Dropped

An earlier iteration errored on partially-specified literals
(`sd_provided < sd_f_count` → E0317). This broke two **established idioms**:

- `Lowerer(source_code = source, mode = ..., file_path = ...)` — fully-named
  partial ctor in `test_lower.nz`; the remaining fields are zero-initialized
  by design.
- `String(s)` — positional partial ctor in `std/string.nz`.

Partial constructors (named OR positional) with implicit zero-init of the
remaining fields are intentional language semantics, so the E0317
missing-field check was **dropped**. `err_missing_struct_field()` remains in
`error.nz` (unused, reserved) in case a future decision requires full
coverage via an explicit opt-in.

## Diagnostics Infrastructure Notes

- TypeChecker has no own report method; all errors go through
  `(deref (deref self).sema).report_error_node(code, msg, node)` (4-arg form
  taking the node).
- `error.nz` plain `err_*()` functions are NOT visible to `typecheck.nz`
  (separate compilation unit resolution in strict mode); error codes are
  hardcoded as `"E0315" to cstr` etc. at the call sites.
- `StringBuilder.append` takes `cstr` only — passing an `i64` segfaults the
  compiler, and calling a nonexistent `String.to_string()` types the receiver
  Unknown so codegen skips the alloca temp and emits invalid IR. Number
  formatting uses the `sprintf`-into-`make[u8]`-buffer pattern with explicit
  `free`, and pre-built `String` values are passed directly.

## Verification

- Legal named / positional / unannotated / nested struct-typed-field literals
  keep working (`P(x = 1, y = Q(a = 7))` → `q=8,9`).
- `unknown` → E0315, `extra` (positional overflow) → E0315, `mismatch`
  (aggregate into scalar field) → E0308.
- Full RT-unlink chain gate 50/50 (test_std's `Tuple2[K, V]` generic ctor and
  `String(s)` idiom preserved) + promotion.
- wasm suites 9/9; zero-runtime 3/3 (Gate A native 25080 B).
