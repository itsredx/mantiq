# Decision 0050: Qualified Module Access & Top-Level Access Modifiers

## Context

Nizam's import system supported three forms — `import X` (module symbol only),
`from X import Y` (named symbols), and `import X [path]/[vendor]` (all symbols
when zero named symbols follow) — but not Python-style qualified use:

```nizam
import std.math
let r as f64 = std.math.sqrt(16.0)   // E0101 "undeclared variable" on `std`
```

The module symbol registered as `"std.math"` (the full dotted target), but
expression resolution descended into the dotted MemberExpr chain and tried to
resolve `std` alone — never declared. Two-level local modules
(`import mymod` + `mymod.helper(5)`) failed identically. Separately, top-level
`public fn` / `private fn` never parsed: `access_modifier` only decorated
struct/class members, so the grammar produced an ERROR node and module files
using access modifiers failed with E0101 on the modifier token itself.

## Decision

Qualified access is resolved at the sema layer; codegen needs no changes
because module declarations are already merged into the program root and
emitted under plain names.

### 1. Qualified chain resolution (`src/sema.nz` — `resolve_qualified_chain`)

Before `declare_pass`, a new pass hook rewrites dotted module chains in place:

- A dotted `MemberExpr` chain is flattened right-to-left into segments.
- The longest dotted prefix is matched against a registered
  `SymbolKind.Module` symbol (`std.math`, or an `import X as Y` alias) whose
  scope must exist in `loaded_modules`.
- The trailing segment must exist in the module scope and be **public**
  (`access_modifier != "private"`); a private symbol reports `E0104`
  ("symbol `x` in module `m` is private").
- The WHOLE chain is rewritten to a plain `Identifier` holding the trailing
  symbol's name. Downstream (typecheck, borrowck, codegen) then treats it
  exactly like a `from <mod> import <sym>` use — the call emits under the
  plain function name.
- Nothing is registered in the importing scope: unqualified use of the same
  name still reports E0101/E0316. Nizam strict mode is preserved by design.
- Multi-level trailing access (`module.Type.member`) fails loudly with E0104
  rather than a confusing E0101 (Phase B: struct-embedded access).
- Unannotated qualified calls type as `TypeKind.Unknown` (acceptable — the
  codebase idiom annotates return types).

### 2. Module aliases (no new Sema field)

`import X as Y` registers the SAME module scope under the alias key in
`loaded_modules` plus an alias `SymbolKind.Module` in the current scope — in
both the cached and full-load paths. `Y.sym(...)` then resolves without a
second module load.

### 3. Top-level access modifiers (grammar + lowerer)

- `grammar.js`: `fun_modifier` now includes `$.access_modifier`, with a
  `[$.fun_modifier, $.var_decl]` conflict declaration for the
  `access_modifier 'static'` ambiguity (next token `fn` vs `let` disambiguates
  — GLR handles it).
- `src/lower.nz` (`lower_fun_decl`): the `fun_modifier` branch now maps
  `public`/`private`/`protected` onto the FunDecl's `access_modifier`.
  Critical detail: in the generated parse tree the modifier token is a child
  of `fun_modifier` (NOT a direct `access_modifier` child as for var/struct
  rules), and `private` is not one of `final`/`extern`/`async` — without this
  branch the modifier fell through silently and every module fn defaulted to
  "public".
- Default `access_modifier` stays `"public"` for plain `fn`: plain functions
  remain reachable via `from std.math import min` (std/math's helpers are
  plain). `private fn` = module-private → E0104 via qualified access.

## Consequences & Verification

- `mymod.helper(5)` after `import mymod` runs (q=15); `mymod.secret()` on a
  `private fn` reports E0104; `import mymod as mm` + `mm.helper(5)` works via
  the alias; bare `helper(5)` after a plain import still reports E0101
  (strict mode intact); `std.math.sqrt(16.0)` runs (q=4.0); method/field
  access on locals (`s.len`) unaffected.
- Parser: `public fn`, `private fn`, and `async public fn` at top level
  parse with `access_modifier` nodes, no ERROR.
- Full gates with the new compiler: 6 borrowck suites green
  (`test_nll_borrowck`, `test_borrowck`, `test_lifetimes_and_pointers`,
  `test_origin_subset_facts`, `test_cfg_loops_nll`,
  `test_cfg_branch_disjoint`), wasm 9/9, zero-runtime 3/3, chain gate 50/50
  + promotion.
- Known latent parser bug (documented, not fixed here): a comment placed
  between `if`/`elif` branches mis-parses and cascades E0101/E0102 across the
  file — comments must live inside branch bodies (recovered during this
  slice's build debugging).

## Future Work

- Phase B: multi-level trailing access (`module.Type.member`) once
  struct-embedded access modifiers exist.
- Fix the comment-between-branches parser defect.
- Editor tree-sitter wasm parsers (vscode/nvim) still embed the pre-0050
  grammar (additive change — rebuild with `tree-sitter build --wasm` when
  convenient).
