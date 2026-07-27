# Development Progress

## Session: Phase 5 — AST Extensions, Borrow Checker & Copy/Move Type Distinction
**Date**: 2026-07-19

---

### Starting State
- Phases 1–4 complete (commit `c39a29c`)
- 7 sema tests passing
- Borrow checker not yet created
- AST missing CallExpr, ReturnStmt, WhileStmt, ForStmt, MemberExpr node types

---

### Work Completed

#### Phase 4 Fixes (carried over)
1. **Fixed `Some()` use-after-free** in bootstrap `codegen.zig` for `RawPointer` types
2. **Fixed `typecheck.nz` double-deref** at lines 234 and 330
3. **Fixed Test 4 (Closure Capture)**: Added `fn_scopes Dict[usize, ptr[Scope]]` to Sema
4. **Fixed `clone_and_substitute`**: Added cloning of `cond`, `then_branch`, `str_val` fields
5. **Removed debug prints** from `typecheck.nz` and `test_sema.nz`
6. **Literal coercion in BinaryExpr**: When one operand is default I32 literal and other is wider type, literal's `inferred_type` is coerced (typecheck.nz lines 426–441)
7. **StringLiteral inference**: Added node type 9 handling in typecheck.nz (returns `TypeKind.String`)

#### Phase 5: AST Extensions
8. **Extended NodeType constants** in `ast.nz`: Added 12=CallExpr, 13=ReturnStmt, 14=WhileStmt, 15=ForStmt, 16=MemberExpr
9. **Lowerer extensions** (`lower.nz`):
   - Added `lower_call_expr` (node type 12): callee via `left`, arguments via `params`
   - Added `lower_jump_stmt` (node type 13): return value via `body`
   - Added `lower_while_stmt` (node type 14): condition via `cond`, body via `body`
   - Added `lower_for_stmt` (node type 15): iterator via `name`, iterable via `left`, body via `body`
   - Added `lower_member_expr` (node type 16): object via `left`, property via `name`
   - Added `assignment` CST type routing to `lower_binary`
10. **Fixed `lower_var_decl`**: Now recognizes `number`, `identifier`, and other value types after `=` sign (was only handling `"expression"` wrapper)
11. **Fixed `lower_fun_decl`**: Added second pass over original `ts_node` to find `block_body` (was only looking in `nf_node` named_function children)
12. **Typecheck extensions** (`typecheck.nz`): Handles CallExpr(12), ReturnStmt(13), WhileStmt(14), ForStmt(15), MemberExpr(16)
13. **Sema extensions** (`sema.nz`): `declare_pass` and `resolve_pass` handle new node types
14. Verified all 7 original sema tests still pass after AST extensions

#### Phase 5: Borrow Checker
15. **Created `borrowck.nz`** with:
    - `ObjectState` enum: `Owned`, `Moved`, `Dropped`
    - `VarInfo` struct: `state as ObjectState`, `var_type as ptr[Type]`
    - `BorrowChecker` struct: `errors`, `current_file`, `symbol_states`, `auto_drops`, `scope_depth`
    - `walk_ast`: recursive AST walker handling Program, BlockStmt, FunDecl, VarDecl, CallExpr, ReturnStmt, BinaryExpr (assignment), WhileStmt, ForStmt, MemberExpr, IfStmt
    - `move_identifier`: checks use-after-move, then conditionally marks as moved based on type
    - `check_identifier_use`: reports use-after-move/drop errors
    - `report_error`: formatted error output with file/line/column
16. **Created `test_borrowck.nz`**: 4 tests (8–11)
17. **Test 8**: Use-after-move detection (`let z = x` after `let y = x`) → PASSED
18. **Test 9**: No false positives (`let y = x` with no further use) → PASSED
19. **Test 10**: Move then redeclare (`let x = 10` after `let y = x`) → PASSED

#### Phase 5: Copy/Move Type Distinction
20. **Added `is_copy_type`/`is_move_type` to `types.nz`**:
    - Copy types: I8–I128, ISize, U8–U128, USize, F16–F128, BFloat16, Boolean, Char, RawPointer (21 types)
    - Move types: everything else (String, List, Dict, Tuple, Closure, Class, Struct, Enum, Option, Result, etc.)
    - Recursive check: None returns false (conservative default)
21. **Refactored borrow checker to use `VarInfo`**: `Dict[String, ObjectState]` → `Dict[String, VarInfo]`
22. **`mark_owned` now takes type**: `mark_owned(name, var_type)` stores type alongside state
23. **`move_identifier` checks type**: Looks up stored type in `symbol_states`, calls `is_copy_type`, skips move for copy types
24. **Added `inferred_type` to VarDecl in typecheck.nz**: `(deref node).inferred_type = annotated_type` (line 354)
25. **Test 11**: Copy type (i32) multiple uses → no move error → PASSED

**Final state**: 11 tests passing (7 sema + 4 borrowck)

---

### Decisions Made

| # | Decision | Rationale |
|---|---|---|
| D1 | `symbol_states` keyed by `String` (variable name), not `usize` (pointer) | Different AST nodes with same variable name have different `name.data` pointers; string comparison works correctly in Dict |
| D2 | `BorrowChecker.__init__` takes only `self` (no sema arg) | Simplifies initialization; type info comes from AST `inferred_type` fields, not sema scopes |
| D3 | `VarInfo` struct stores both state AND type | Avoids needing to re-lookup type from sema during borrow checking; type is stored once at declaration time |
| D4 | `move_identifier` checks type stored in `symbol_states`, not `node.inferred_type` | VarDecl's `inferred_type` is overwritten to Void by typechecker's return value assignment (compiler quirk); storing type at declaration time in VarInfo avoids this |
| D5 | Copy type = all primitive/pointer types; Move type = everything else (conservative) | Matches spec in decision 0026; primitives are stack-stored and cheap to bitwise copy; anything that could own heap memory is Move |
| D6 | When `VarDecl.inferred_type` is Void, fall back to init node's `inferred_type` | Works around a typechecker bug where VarDecl's `inferred_type` gets overwritten to Void; the init node (NumberLiteral, Identifier, etc.) retains its correct type |
| D7 | Borrow checker is type-unaware when type info is missing (None → treat as Move) | Conservative default: if we can't determine whether a type is Copy, treat it as Move to avoid missing real use-after-move bugs |
| D8 | `mark_moved`/`mark_dropped` preserve existing type info when transitioning state | Prevents losing type information when a variable transitions from Owned to Moved/Dropped |
| D9 | `memset` size for BorrowChecker needs to be ≥256 bytes | Dict fields are large; undersized memset causes heap corruption |
| D10 | `stdbuf -oL` required for test execution | stdout is fully buffered by default in the Nizam runtime; `stdbuf -oL` forces line buffering for test output |
| D11 | `extern fn printf` takes exactly 2 `cstr` args | Nizam's printf wrapper only supports 2 arguments; multi-arg printing requires separate calls |

---

### Known Issues

1. **VarDecl `inferred_type` Void overwrite**: The typechecker sets `(deref node).inferred_type = annotated_type` (which should be I32 for `let x = 42`), but `ret_type = make_type(TypeKind.Void)` afterward somehow overwrites it. The borrow checker works around this by falling back to the init node's type. Root cause not yet identified — possibly a Nizam compiler codegen bug where local `ret_type` variable aliases with struct field memory.

2. **Option cloning incomplete**: `clone_and_substitute` cannot clone `else_branch` and `initializers` Option fields due to missing Option unwrap mechanism.

---

### Files Modified
- `src/ast.nz` — Added node type constants 12–16
- `src/lower.nz` — Extended with 6 new lower functions + VarDecl/FunDecl fixes
- `src/typecheck.nz` — Added handlers for node types 12–16, BinaryExpr literal coercion, StringLiteral inference, VarDecl inferred_type
- `src/sema.nz` — Extended declare_pass/resolve_pass for new node types
- `src/types.nz` — Added `is_copy_type()`/`is_move_type()` functions (50 lines)
- `src/borrowck.nz` — **NEW**: BorrowChecker with ObjectState, VarInfo, ownership tracking, move detection (198 lines)
- `src/test_borrowck.nz` — **NEW**: 4 borrow checker tests (94 lines)
- `src/test_sema.nz` — Removed debug prints

### Git Commits
- `c39a29c` — `feat: Phase 4 - Type System & Monomorphization`
- `8ca8e39` — `test` (debug iteration)
- `a1d8d58` — `feat: borrow checker with copy/move type distinction`

---

## Session: Phase 6 — Destination-Driven Literal Inference
**Date**: 2026-07-19

### Work Completed

#### Parser / Lowering Fixes
1. **Fixed Type Annotation Parser Flattening in Lowerer**:
   - Refactored `lower_type_annotation` in `src/lower.nz` to iterate directly over visible children of `type_annotation` starting at index 1, accommodating tree-sitter's flattened tree layout for hidden/anonymous type descriptor rules. This ensures variable and parameter type annotations are successfully resolved (e.g. `f64`).
   - Updated parameter parsing inside `lower_fun_decl` in `src/lower.nz` to match both `"param_decl"` and `"typed_var"` kinds to comply with the tree-sitter grammar rules.

#### Type Checker & Literal Inference Integration
2. **Type Checker & Literal Inference Integration**:
   - Integrated parameter type annotation extraction for function declarations, and return value validation for return statements in `src/typecheck.nz`.
   - Implemented destination-driven type propagation for `NumberLiteral` expressions under variable initializations, assignment statements, return statements, and function call parameters.
3. **Skip Nizam Strict Mode Import Check for Primitives and Generic Parameters**:
   - Modified `check_nizam_import` in `src/typecheck.nz` to bypass explicit import verification for built-in primitive types (e.g. `i32`, `f64`, `bool`, `ptr`, `void`) and generic type parameters (assumed to be single uppercase letters like `T`).

#### Verification
4. **Verification**:
   - Extended the `src/test_sema.nz` verification test suite with Scenario 12 to validate correct literal inference rules for variable initialization (`let y as f64 = 0.0`), assignment (`y = 24`), and call parameters (`f(42)`). All tests pass successfully.

### Files Modified
- `src/lower.nz` — Refactored `lower_type_annotation` and `lower_fun_decl`
- `src/typecheck.nz` — Updated `check_nizam_import` and parameter types/ReturnStmt/assignments type propagation
- `src/test_sema.nz` — Added Scenario 12 literal type inference verification

### Git Commits
- `d32c7eb` — `feat: implement destination-driven literal type inference and fix parser type annotation flattening`
- `a05ac3e` — `fix: skip nizam strict mode import checks for primitives and generic parameters`

---

## Session: Phase 5 (Remainder) — Borrow Checker Lexical Auto-Drops & Context Managers
**Date**: 2026-07-20

### Work Completed

#### AST & Parser Extensions for WithStmt
1. **Added `WithStmt = 21`** to [ast.nz](file:///home/red-x/projects/desktop/mantiq/src/ast.nz) and [lower.nz](file:///home/red-x/projects/desktop/mantiq/src/lower.nz).
2. **Fixed `lower_with_stmt` in `lower.nz`**: Skipped anonymous keyword tokens (`kw_with`, `with`, `as`) during traversal so that the resource expression and variable bindings are parsed correctly.

#### Semantic Analysis & Typechecking for WithStmt
3. **Sema Support**: Updated `sema.nz` to process `WithStmt` in `declare_pass` and `resolve_pass`. It creates a child scope, registers the context manager variable, and sets `is_context_manager = True` on the context manager variable's symbol.
4. **Typechecker Support**: Updated [typecheck.nz](file:///home/red-x/projects/desktop/mantiq/src/typecheck.nz) to validate `WithStmt`.
5. **Nizam Strict Mode Skipping**: Added `String`, `List`, `Dict`, and `cstr` to primitive skipped types to avoid false import error flags.
6. **Sema Built-ins & std.mem**: Added all common built-ins (`None`, `Some`, `Empty`, `Ok`, `Err`, `make`, `drop`, `range`, `print`) to the global scope initialization. Special-cased imports of `std.mem` to dynamically register memory builtin symbols, matching the host compiler's behavior.

#### Borrow Checker Auto-Drops & Context Managers
7. **lexical scope auto-drops**: Implemented scope tracking and population of `auto_drops` (destructors injection) for owned move-type variables on scope exits in [borrowck.nz](file:///home/red-x/projects/desktop/mantiq/src/borrowck.nz).
8. **Context manager cleanups**: Prioritized context manager variable cleanups inside `with` statement blocks.
9. **Memory allocator workarounds**: Replaced generic list `make` allocations with standard C `malloc` allocations in local helpers to avoid host compiler generic codegen dereference segmentation faults.

#### Verification
10. **Extended tests in `test_borrowck.nz`**:
    - Added Test Scenario 13 verifying the correctness of `auto_drops` injection.
    - Added Test Scenario 14 verifying correct context manager block scope drop injection and flag settings.
    - Resolved panic from block scopes with single statements by checking AST node types.
    - All tests pass cleanly.

### Files Modified
- `src/ast.nz` — Added node type constant 21
- `src/lower.nz` — Implemented `lower_with_stmt`, `lower_string`, and skipped keywords in `lower_with_stmt`
- `src/typecheck.nz` — Added skipped types list for strict mode and `WithStmt` typechecking
- `src/sema.nz` — Extended declare_pass/resolve_pass for `WithStmt`, added Option/Result/memory builtins, special-cased `std.mem`
- `src/borrowck.nz` — Implemented scope tracking, auto-drops injection, context managers, and used `malloc`
- `src/test_borrowck.nz` — Added Scenario 13 and 14 verification, fixed AST lookup panics

### Git Commits
- `c029df4` — `feat: implement lexical auto-drops injection and context manager cleanup cycle for Phase 5`

---

## Session: Phase 6 — LLVM IR Code Generation (Partial)
**Date**: 2026-07-20

### Work Completed

#### Code Generator (`codegen.nz`)
1. **Created `codegen.nz`** (~551 lines) with `LLVMCodegen` struct containing:
    - 4 `StringBuilder` buffers: `type_out`, `outlined_out`, `metadata_out`, `main_out`
    - `temp_counter`, `label_counter` for fresh register/label names
    - `type_to_llvm`: maps all `TypeKind` variants to LLVM IR types (i8–i128, u8–u128, f16–f128, Boolean, String→`{ ptr, i64, i64 }`, List/Dict→`{ ptr, i64, i64 }`, Option→`{ i8, ptr }`, etc.)
    - `fresh_temp()`, `fresh_label()` counters
    - `generate(root)`: entry point, emits program declarations, returns main_out
2. **AST dispatch** via `emit_node`: handles all node types — Program(1), FunDecl(3), VarDecl(4), IfStmt(5), BinaryExpr(6), Identifier(7), NumberLiteral(8), StringLiteral(9), CallExpr(12), ReturnStmt(13), WhileStmt(14), BlockStmt(19)
3. **Expression emission** via `emit_expr`: returns SSA register name strings; handles NumberLiteral→literal constant, Identifier→load, BinaryExpr→arithmetic/comparison, CallExpr→call instruction, StringLiteral→getelementptr into constant
4. **Binary expression emission** via `emit_binary_expr` (expression context) and `emit_binary_stmt` (assignment context): maps operators +,-,*,/,% to add/sub/mul/sdiv/srem; <,>,<=,>=,==,!= to icmp variants
5. **Control flow**: `emit_if` emits cond→br→then/else/end blocks with OptionLayout else-branch check; `emit_while` emits cond/body/end loop with back-edge br
6. **Function emission** via `emit_fun_decl`: emit `define` with param types, call `emit_node` on body, append `ret void` if no explicit return

#### Null Safety & Robustness
7. **Null checks throughout**: every function checks node/op.data/callee/args for None before dereferencing; returns default "0" or "void" on None
8. **OptionLayout pattern** for else-branch: `option_has_value(ref_to_option)` / `option_unwrap_ptr(ref_to_option)` to safely check Option fields without triggering bootstrap compiler's invalid `bitcast` codegen
9. **`sprintf` for number formatting**: uses `"%g"` for f64 and `"%d"` for i32 to format number literals into LLVM IR
10. **`op.data to cstr` casts**: operator tokens have `ptr[u8]` data field, not `cstr`; explicit cast required for `strcmp` calls

#### Test Suite (`test_codegen.nz`)
11. **Created `test_codegen.nz`** with helper `run_one(source, file, check)` and 9 diagnostic tests:
    - Test 1: VarDecl + Number (alloca+store check) → PASSED
    - Test 2: FunDecl noop (define+ret void check) → PASSED
    - Test 3: FunDecl with return (ret check) → PASSED
    - Test 4: StringLiteral (constant+getelementptr check) → PASSED
    - Test 5: CallExpr (call check) → PASSED
    - Test 6: Assignment (store check) → PASSED
    - Test 7: Multi-statement (alloca check) → PASSED
    - Test 8: WhileStmt (br check) → PASSED
    - Test 9: Two Vars (alloca check) → PASSED

#### Known Limitations
12. **Binary expression type error**: `let x as i32 = 10\nlet y as i32 = x + 5\n` triggers `type mismatch in binary expression` in typechecker stderr, but codegen still produces output. Workaround: tests avoid binary expressions with typed variables
13. **No executable output yet**: IR is only inspected for structural correctness (alloca, store, call, br, define keywords); no `llc`/`clang` compilation pipeline
14. **While/if tests use trivial conditions**: complex conditions trigger binary expression type errors; deferred to future fix

### Files Modified
- `src/codegen.nz` — **NEW**: LLVM IR code generator (551 lines)
- `src/test_codegen.nz` — **NEW**: 9 codegen diagnostic tests

### Git Commits
- pending

#### Phase 6 Fixes
15. **Fixed `pass_stmt` handling in lowerer** (`lower.nz`): Added `pass_stmt` handler that produces a NumberLiteral(0) placeholder, preventing the default fallback from creating an `"UNSUPPORTED"` Identifier that would trigger "undeclared variable" errors in sema
16. **Expanded test suite** (`test_codegen.nz`): Added 3 new tests:
    - Test 10: IR Module Header validation (checks for `target triple` string)
    - Test 11: IR External Declarations (checks for `declare` keyword)
    - Test 12: Clang Syntax Check — writes minimal IR to `/tmp/nz_test12.ll` and validates it with `clang-15 -fsyntax-only`
17. **Removed redundant `pass` builtin registration** from sema.nz — not needed once the lowerer handles `pass_stmt` properly
18. **Fixed `write_file` function**: Takes explicit `data_len` parameter instead of relying on `strlen`, which crashes on non-null-terminated String data

### Git Commits
- `04940fe` — `feat: implement LLVM IR code generation with diagnostic test suite`
- `80a021a` — `fix: handle pass_stmt in lowerer and add clang IR validation tests`

---

## Session: Phase 6 — Tasks 6.4 & 6.5 (Closure Outlining & Scope Auto-Drops)
**Date**: 2026-07-26

### Work Completed
1. **Task 6.5: Scope Cleanups (`auto_drops`)**:
   - Implemented `emit_auto_drops` with null-check branching (`icmp ne ptr %ptr_reg, null` → `br i1 %cond_reg, label %exec, label %skip`).
   - Integrated `emit_auto_drops` into `emit_return`, `emit_block`, and `emit_with`.
   - Added **Test 13 (Scope Auto-Drops IR Generation)** to `src/tests/test_codegen.nz`.
2. **Double-Free / Segfault Resolution in SSA Register Functions**:
   - Refactored `fresh_temp`, `fresh_label`, `emit_expr`, `emit_binary_expr`, `emit_call_expr`, `emit_unary_expr`, `emit_cast_expr`, `emit_list_literal`, `emit_index_expr` in `src/codegen.nz` to return Copy primitive `ptr[u8]`.
   - Bypassed bootstrap compiler borrow-checker string drop generation for register/label variables.
3. **Task 6.4: Closure Outlining & Environment Packing**:
   - Added `closure_counter` and `fresh_closure_name()` to `LLVMCodegen`.
   - Implemented `emit_closure_expr(node)`:
     - Outlines closure body into `self.outlined_out` as `@__closure_N(ptr %env, ...)`.
     - Allocates fat pointer `{ ptr @__closure_N, ptr %env }` in `self.main_out`.
   - Added **Test 14 (Closure Outlining IR Generation)** to `src/tests/test_codegen.nz`.
4. Verified all 14 tests in `test_codegen.nz` pass cleanly with zero errors or segfaults.

