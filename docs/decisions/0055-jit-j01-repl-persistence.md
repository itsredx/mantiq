# Decision 0055: JIT J0.1 — REPL Declaration Persistence via Source Accumulation

## Context

J0.0 (Decision 0054) shipped the `nizam repl` loop with fresh state per
snippet: each snippet compiled alone, so `fn double_it` defined in snippet 1
was undeclared in snippet 2. Decision 0035's REPL contract requires
declarations to persist (global scope, functions, types). The legacy Zig
REPL achieved this with a persistent `SemanticAnalyzer` (its `global_scope`
accumulates) + typechecker + globals map + macros, plus J0.2's `.so` chain
for link-time symbol resolution.

The self-hosted pipeline is a per-call chain (`engine.register_source` →
lower → sema → typecheck → codegen) with no incremental analysis entry
points, and execution is still process-per-snippet (no `dlopen` yet).

## Decision

**Source accumulation with a statement-suppression threshold.**

- `start_repl` keeps the session's committed source in `accum_buf` (8 MB).
  Each snippet compiles as `accum + snippet` in `work_buf`, so every prior
  declaration (fns, globals, structs) re-parses, re-typechecks, and
  re-emits — sema is effectively persistent without touching the analyzer.
- Prior snippets' *statements* must not re-execute. Codegen gains a module
  threshold `repl_stmt_min_row` (set per snippet via
  `set_repl_stmt_min_row`): `emit_program` routes only statements whose
  `node_span(d0).start_row >= repl_stmt_min_row` into the synthetic
  `@main`; earlier-row statements are dropped. Prior *declarations* are
  never filtered — they are the persistence mechanism.
- `repl_mode` (set once via `set_repl_mode`) makes `emit_program` emit a
  trivial `define i32 @main() { entry: ret i32 0 }` for declarations-only
  snippets — otherwise no `main` exists and the executable fails to link.
  File mode never sets these; its behavior is unchanged.
- A snippet is committed to `accum` only if its compile **succeeds**; a
  failed snippet leaves the session state untouched (the user can recover
  by re-entering it correctly).
- Cross-module function calls use `from codegen import set_repl_mode,
  set_repl_stmt_min_row` — module-qualified calls (`codegen.fn()`) are NOT
  supported by the lowerer (`codegen` there resolves to an undefined
  `%codegen` local). The gate's older builder rejected what the newer
  local candidate silently accepted; the from-import is correct for both.

## Semantics (documented limitations, resolved in J0.2)

- Top-level `let/var` are **globals** (file-mode parity): constant
  initializers work (`var x as i32 = 40`); non-constant initializers are
  dropped silently (`let y as i32 = x + 2` → `y = 0`) — same as file mode
  today. With J0.2's `dlopen` + `external global` scheme, per-snippet
  entry functions will assign initializer values at runtime (the legacy
  Zig behavior).
- Mutations to globals do not survive snippet boundaries (each snippet's
  executable re-initializes its globals). J0.2 links prior `.so`s so
  references bind to the still-loaded definitions.
- Duplicate `extern fn` declarations across snippets dedup correctly
  (Pass 1.5 + declare dedup).

## Verification

- Session test: `var x = 21` → `fn double_it` → `printf(x, double_it(x))`
  → `var y = 100; printf(y, double_it(y))` — prior statements do NOT
  re-execute, all values correct.
- Struct definitions persist with file-mode semantics (`mk(9).a`,
  by-value return + chained member access; Slice 38 syntax).
- Declarations-only snippets link and exit 0; failed snippets don't
  corrupt the session; duplicate externs dedup.
- File-mode regressions: elif matrix (0053), struct literal (0038),
  global string (0054) — all rc=0.
- Chain gate 50/50 + promotion; wasm 9/9; zero-runtime 3/3.

## Notes

- `probes/p42_known_struct_global.nz` records a **pre-existing** file-mode
  defect surfaced by REPL testing: struct-typed globals + field access
  emit `inttoptr i64 @g to ptr` and a wrong named-type layout
  (`%Cfg = type { i8 }`). Also: brace-literal `Pt{ x: a, y: b }` is not a
  supported literal form even for locals (`P(x = 1, ...)` is). Both
  predate this slice; tracked for a dedicated codegen pass.
- Latency is O(session) per snippet (recompile-everything); acceptable
  for J0 — J1a's session-module batching addresses it.
