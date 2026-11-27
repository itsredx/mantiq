# Decision 0054: JIT J0 — REPL Command and Synthetic Main

## Context

`docs/jit-design.md` phased the JIT work: **J0** ports the legacy Zig dlopen
REPL (`mantiqz/mantiq-compiler/src/jit.zig`, Decisions 0020/0035) onto the
self-hosted compiler. J0.0 is the interactive loop itself: read snippet lines
until a blank line, compile the snippet in-process, execute natively, print
the exit status; Ctrl-D exits. J0.1 adds persistent semantic state across
snippets; J0.2 adds cross-snippet `.so` linkage.

The first end-to-end J0.0 run exposed a deeper defect that also breaks plain
`run` on statement-bearing files: **top-level statements emitted raw LLVM
instructions at module level** — `%t.1 = getelementptr ...` outside any
`define`, no `@main` — rejected by clang (`expected 'type' after name`).
The self-hosted codegen had lost the legacy Zig script-style entry
(`codegen.zig:1052–1144`).

## Decision

### 1. `nizam repl [nizam|mantiq]` (J0.0)

`start_repl(default_mode, prof_flag)` in `main.nz` (~line 1639):

- Reads snippet lines byte-wise (`read(0, ...)`) until a blank line or EOF;
  Ctrl-D exits. `snip_no` and `getpid()` key the output paths
  (`/tmp/nizam_repl_<pid>_<n>`).
- Per snippet: `compile_source(snip, "<repl>", out, mode, target, perf,
  is_debug=False, use_cache=False, "/tmp", no_libc=False)` — the virtual
  `<repl>` path only feeds diagnostics; the cache is bypassed (it is keyed
  by file sha + `/proc/self/exe` sha).
- Success → execute via `mantiq_run_command_direct` with a synthetic argv,
  print `[exit N]`. Fresh pipeline state per snippet (J0.1 persistence is
  future work per Decision 0035's table).
- Dispatch in `main()`: `repl [nizam|mantiq]`, defaulting to the binary's
  default mode.

### 2. Synthetic `@main` for top-level statements

`emit_program` (codegen.nz, Pass 2) now:

- Pre-scans root decls: any non-declaration kind (CallExpr, BinaryExpr,
  IfStmt, WhileStmt, ForStmt, etc. — the statement kinds `emit_node`
  dispatches) is collected; presence of a non-extern `fn main` FunDecl is
  noted.
- Pass 2 emits only declaration kinds (FunDecl, ImportDecl + the existing
  excluded set); collected statements are skipped there.
- After all functions, if statements exist **and no user `fn main`**, emit
  `define i32 @main() {\nentry:\n` + the statements in source order +
  `ret i32 0` + `}`, with `current_return_type = "i32"` and fresh
  `var_slots`/`var_counts`/`var_types` — mirroring `emit_fun_decl`'s
  function-state setup. Emitted *after* all functions so calls resolve
  against real definitions (externs are already declared by Pass 1.5).
- Top-level `return` is skipped in the synthetic main (meaningless in
  script mode; would strand the trailing `ret`).
- When a user `fn main` exists, behavior is unchanged (statements were
  already broken there; no corpus file exercises that combination).

### 3. Global string initializers

The same defect class existed for top-level string variables:
`emit_expr(StringLiteral)` registers the `@.str.N` constant (type_out) but
unconditionally appends a `getelementptr` to main_out — illegal at module
level, so `var s as cstr = "hi"` at top level never compiled. The VarDecl
global path now recovers the `@.str.N` symbol from the appended region,
truncates main_out back, and — for pointer-typed globals (cstr → `ptr`) —
initializes the global to the constant's address (`@s = internal global
ptr @.str.1`, a legal LLVM global initializer). Aggregate-typed globals
(String → `{ ptr, i64, i64 }`) keep `zeroinitializer`.

## Verification

- REPL: `printf` statement, arithmetic on a top-level `var`, user-defined
  `fn` + call, `if/else`, `while` — all `[exit 0]` with correct output.
- File-based `run` of statement-bearing files repaired (was rc=1 with
  invalid IR).
- Global string var probe (`probes/p41_gvar_str.nz`) prints the value;
  REPL variant likewise.
- No regression: elif matrix (Slice 40), struct-literal probe (Slice 38).
- Chain gate 50/50 + promotion; wasm suites 9/9; zero-runtime 3/3.

## Notes

- J0.0 is deliberately fresh-state per snippet. J0.1 (persistent
  sema/typechecker/arena) and J0.2 (cross-snippet `.so` chaining via
  `zig cc -shared -fPIC` + `dlopen`/`dlsym`, synthetic entry
  `repl_snippet_N`) follow `docs/jit-design.md`.
- Statement results are visible only through side effects (printf) in
  J0.0 — expression-value echo requires J0.1/J0.2 machinery.
- REPL prompts/snippet output interleave correctly because prompts are
  flushed with `fflush(None)` before each read.
