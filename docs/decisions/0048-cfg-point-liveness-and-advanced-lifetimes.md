# Decision 0048: CFG Point-Based Liveness Engine, Path-Sensitive NLL & Advanced Lifetimes

## Context

Nizam's initial borrow checker (`src/borrowck.nz`) enforced affine move semantics, use-after-move / use-after-drop errors, and basic Non-Lexical Lifetimes (NLL). However, the initial NLL implementation evaluated loan liveness by comparing source code row numbers (`row > last_use_row`).

This heuristic exhibited three foundational architectural gaps:
1. **Row-Based NLL Fragility**:
   - In loops (`while`, `for`), backward control-flow jumps violate monotonic line progression. A loan terminated at line 40 could be re-accessed on iteration 2 at line 25, risking false negatives (missed memory hazards) or false positives.
   - In branch disjunctions (`if/else`, `match`), loans created and dropped inside one branch were erroneously treated as outliving operations occurring later in file line order in alternate branches.
2. **Inter-procedural Lifetime Black-Box**:
   - Generic lifetime binders (`fn choose[life a](x as life[a] String, y as life[a] String) as life[a] String`) were parsed in AST metadata but not verified at call sites, allowing returned references to outlive short-lived arguments.
3. **Struct-Embedded Lifetime Limitations**:
   - Composite types could not safely wrap references with lifetime bounds (`struct StringView[life a]`), and distinct struct fields could not be mutably borrowed simultaneously without whole-struct collision.

---

## Decision

We replace linear line-number borrow checking with a **path-sensitive CFG point-based liveness and origin-tracking engine** in `src/cfg.nz` and `src/borrowck.nz`, structured into a four-phase architectural progression:

### 1. CFG Point-Based Representation & Dataflow Engine
- Program coordinates are identified by discrete CFG points:
  ```nizam
  struct Point:
      public var bb_id as i64
      public var stmt_idx as i64
  ```
- Basic blocks flatten terminator representation (`terminator_kind`, `terminator_target_bb`, `terminator_then_bb`, `terminator_else_bb`, `terminator_expr`) with explicit pointer setters (`set_terminator_return`, `set_terminator_branch`, `set_terminator_branch_if`), eliminating LLVM IR struct-return and enum dispatch mismatches.
- Nested loop tracking uses scalar fields `current_loop_break_bb` and `current_loop_continue_bb` saved on the call stack across nested loops, avoiding dynamic list pop operations.
- Backward variable liveness analysis (`var_live_at(Var, Point)`) computes exact variable liveness across basic block predecessors and loop back-edges.
- Loans are terminated at point $P$ if the borrower variable is dead downstream:
  $$\text{Kill}[P] = \{ L \mid \text{borrower}(L) \notin \text{LiveVars}(P) \}$$

### 2. Inter-Procedural Lifetime Parameterization & Elision
- Function signatures track `lifetime_params` and parameter/return lifetime annotations.
- At call sites, argument loan origins map to parameter lifetimes:
  $$\text{Origin}('a) = \bigcup_{arg \in \text{Params}('a)} \text{Origin}(arg)$$
- Return values inherit $\text{Origin}('a)$. If any argument loan in $\text{Origin}('a)$ is dropped while the return value remains live, error **`[E0408]`** (`borrowed value does not live long enough`) is emitted.
- Deterministic 3-rule lifetime elision infers parameters for single-input and `self` method calls.

### 3. Struct-Embedded Lifetimes & Field Projections
- Struct definitions support generic lifetimes: `struct StringView[life a]: buffer as life[a] String`.
- Composite instances inherit the origins of their reference fields. If the struct outlives the referenced allocation, error **`[E0409]`** is emitted.
- Field projections (`Base.Field`) allow simultaneous disjoint mutable borrows of distinct struct fields without whole-object conflicts.
- Reference variance rules (covariance for immutable references, invariance for mutable reference payload types) govern subtyping.

### 4. Standardized Diagnostic Catalog
All borrow and lifetime violations report structured diagnostics with primary and secondary span labels:
- `[E0401]`: `UseAfterMove`
- `[E0402]`: `UseAfterDrop`
- `[E0403]`: `MoveWhileBorrowed`
- `[E0404]`: `MutateWhileBorrowed`
- `[E0405]`: `ConcurrentMutableBorrow`
- `[E0406]`: `AliasingViolation`
- `[E0407]`: `DanglingStackReference`
- `[E0408]`: `BorrowedValueDoesNotLiveLongEnough`
- `[E0409]`: `StructOutlivesBorrowedData`
- `[E0410]`: `LifetimeElisionAmbiguity`

---

## Phased Implementation Roadmap

1. **Phase 1: CFG Point-Based Liveness Engine (Weeks 1–2) — [COMPLETED]**
   - AST-to-CFG lowering in `src/cfg.nz`.
   - Backward variable liveness analysis (`var_live_at`, `is_borrower_live`).
   - Borrow checker integration in `src/borrowck.nz` and `src/main.nz`.
   - Codegen dictionary value size alignment fixes in `src/codegen.nz`.
   - Verified via `test_cfg_loops_nll.nz` (4/4 passed) and `test_cfg_branch_disjoint.nz` (4/4 passed).
2. **Phase 2: Inter-Procedural Lifetime Parameterization & Elision (Weeks 3–4)**
   - AST binders, call-site origin substitution, outlives verification (`E0408`).
3. **Phase 3: Struct-Embedded Lifetimes & Field Projections (Weeks 5–6)**
   - `struct Name[life a]`, field-level disjoint loan tracking (`E0409`).
4. **Phase 4: Polonius Fact Engine & Drop Elaboration Integration (Weeks 7–8)**
   - Datalog fact formulation and dynamic drop flag insertion in codegen.

---

## Consequences & Verification

- **Elimination of False Positives**: Branch-disjoint loan scopes and loop early releases are handled with complete precision.
- **Elimination of False Negatives**: Backward loop edges correctly propagate loan liveness, preventing use-after-free across loop iterations.
- **Multi-Target Workspace Parity**: Verified with zero drift across `mantiq/` and `compiler-service/` via `./dev-sync.sh --check`.
- **Test Suites**:
  - `src/tests/test_borrowck.nz` (Legacy move, drop, copy-type, auto-drops)
  - `src/tests/test_nll_borrowck.nz` (NLL early release, aliasing XOR mutability)
  - `src/tests/test_cfg_loops_nll.nz` (Loops, backward edges, break/continue)
  - `src/tests/test_cfg_branch_disjoint.nz` (Branch-disjoint loan scopes)
