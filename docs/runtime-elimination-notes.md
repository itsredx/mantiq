# Runtime elimination — carry notes (updated during Milestone B)

## State
- Milestone A (collections in Nizam) LANDED: all 39+ `__mantiq_dict_*` / list /
  hash C bodies deleted from `runtime.c` and `src/runtime.c`. Hash primes
  (`__mantiq_hash_bytes`/`__mantiq_hash_string`) remain as WEAK C defs —
  they serve the C-side interning engine and scope lookup; the identical
  Nizam defs in `std/collections.nz` win whenever `std.collections` is
  imported.
- `__mantiq_dict_get` is weak-extern in runtime.c and every call site is
  guarded (`__mantiq_dict_get ? __mantiq_dict_get(...) : 0`) — scope lookup
  degrades gracefully when a program does not import std.collections.
- Allocator family (`mantiq_malloc`, `mantiq_malloc_raw`, `mantiq_free`,
  `mantiq_realloc`) is now weak in the C runtime with identical semantics
  retained (size bound 500 MB, calloc-zeroing, arena-ptr skip, size-0
  realloc behaviour). Milestone-B Nizam defs landed in `std/mem.nz`
  (module-level fns; the old builder only supports nested externs, so the
  extern decls are per-function).
- `__mantiq_dict_destroy` stays a no-op in this era: dict fat slots alias
  tables freely (views/copies) and freeing is a double-free.

- `__mantiq_dict_destroy` stays a no-op in this era: dict fat slots alias
  tables freely (views/copies) and freeing is a double-free.

## Aliasing drop instance #1 fixed: `strip_generic_base` (src/typecheck.nz)
ASan on the (fixed-source) compiler caught a double-free whose writer was
`struct_method_params` dropping its local `base_name` on all 7 return
paths, while `strip_generic_base(struct_name)` returned the INPUT alias on
the no-bracket path — freeing the receiver TYPE's name String still owned
elsewhere. The freed type-name buffer got recycled by IR-text buffers,
later surfacing as ASCII-as-pointer crashes. Fix: the no-bracket path now
returns a fresh memcpy'd String instead of the input alias (single caller).
This was instance #1 of the documented "auto-drop double-frees aliased
buffers" family; expect siblings (see nodictC below).

## Aliasing drop instance #2 fixed: `drop_type_base` (src/codegen.nz:2731)
ASan on test_types.nz caught a UAF inside `LLVMCodegen_emit_struct_drop_glue`
(memcpy from freed memory). `drop_type_base(type_name)` returned the INPUT
alias on the no-bracket path; all four call sites (two in
emit_struct_drop_glue, two in the struct-field drop emitter) `.deinit()` the
value or the input it aliases → use-after-free + double-free. Fix: the
no-bracket path now returns a fresh memcpy'd String (same pattern as
strip_generic_base instance #1).

## Aliasing drop instance #3 fixed: borrowck auto-drop of aliasing inits
`let lt_name as String = (deref sema).link_targets[lti]` (src/main.nz
Phase-7 link loop): the byval read aliases the buffer the List still owns;
the frozen-era borrowck marks the local Owned and drops it at iteration
scope exit → next iteration strcmp reads freed memory
(`free(): double free detected in tcache 2` on EVERY suite test — this was
the systematic 0/50 suite failure). Two-part fix:
- src/main.nz: the loop now does
  `let lt_name as String = String.make(((deref sema).link_targets[lti]).data to cstr)`
  — a fresh copy, so the auto-drop frees its own buffer. (The compiler's own
  code is compiled by the FROZEN builder, whose baked-in borrowck cannot be
  changed; source-level workaround required.)
- src/borrowck.nz: new `is_aliasing_init(sym)` helper — True when the
  symbol's `decl_node` init is an IndexExpr or a deref UnaryExpr. Both drop
  decision sites (pop_scope, ReturnStmt scope-flush) now skip auto-drop for
  such symbols. This benefits programs compiled BY the self-hosted compiler
  once it builds itself. Deliberately NO new BorrowChecker field (the frozen
  builder miscompiles unknown struct fields to index 0).

## Deref-of-aggregate identity fix (src/typecheck.nz + src/codegen.nz)
`(deref big)[k] = v` on a LOCAL Dict (dictsize/dictderef probes) failed with
`'%t.N' defined with type '{ ptr, i64, i64 }' but expected 'ptr'`:
- typecheck: deref of a by-value Dict/List/String/Set/Tuple returned
  TypeKind.Any → node_index_collection_is_dict missed the site → generic
  array-index path emitted struct-as-pointer IR. Fix: deref of these kinds
  returns the operand type (identity), like Struct/Class already did.
- codegen emit_unary_expr deref branch: emit_expr(operand) on a byval
  aggregate local already yields the struct value; the generic deref path
  then loaded AGAIN through it (`load { ptr, i64, i64 }, ptr %t.N` with a
  struct as pointer). Fix: deref of Dict/List/String/Set/Tuple operands
  returns the operand value directly.
After both fixes: dictderef + dictsize build AND run green; portstress all
7 sections still green.

## Stale-cache double-free (suite crash trigger — NOT a codegen bug)
The "systematic" 50-suite double-free crashes were environmental: the
shared `.mantiq_cache` contained bin/meta entries written by OLDER compiler
binaries (Oct 24, frozen-era; mixed with newer entries). The new binary
reading stale `.dep` meta files double-freed (`free(): double free detected
in tcache 2`) — reproducible with the sequence test_types → test_abi →
test_std over a dirty cache, and NOT reproducible after `rm -rf
.mantiq_cache` (clean-cache sequence: all green, 3/3 direct runs too).
CARRY ITEM: the tier-1/tier-2 cache-load path must tolerate meta files
written by different compiler versions (a real-user scenario after any
compiler upgrade) — either version the .dep format or key meta by exe
flags_sig like the bin entries already are. Until fixed, ALWAYS run the
suite (or any multi-binary workflow) with a clean `.mantiq_cache`.

## test_borrowck SIGSEGV: BorrowRecord reassignment aliasing (instance #5, diagnosed)
`BorrowChecker_update_borrows_liveness` (src/borrowck.nz:343) segfaults
hashing `b.borrower_name` when compiling test_borrowck.nz (gdb: PC inside
an inlined __mantiq_hash_string loop dereferencing a garbage data pointer).
Mechanism (aliasing family, instance #5): `updated_list` records are built
from byval list reads (`(deref ab_ref)[idx]`) with the struct ctor SHALLOW-
copying the String fields; `(deref self).active_borrows = updated_list`
then drops the old list — BorrowRecord drop glue frees the String buffers —
leaving the new list's records dangling. The next borrow-creation call
hashes a freed/clobbered buffer → SEGV. Long-term fix: deep-copy Strings
in the loop (`String.make(b.borrower_name.data to cstr)`) or disable
reassignment drop for active_borrows. STATUS: pending ASan confirmation.

## Verified behaviour triples (post-deletion)
| program | std imported | link | runtime source |
|---|---|---|---|
| no-dict program | none | OK | C weak hash/alloc only |
| dict program, no import | none | FAIL, only `__mantiq_dict_*` undefined (honest) | - |
| dict program | std.collections | OK | Nizam port |

## New (mangled) crash in test_dict_methods post-deletion
`main → __nizam_drop_List → __nizam_drop_String → free(): invalid pointer`

Root cause chain (all C-parity, pre-existing builder bugs — NOT port
regressions):
1. codegen `emit_dict_literal` for annotated-but-empty `{}` literals emits
   `@__mantiq_dict_create(4, 4, 0)` (i32 defaults) — the "literal lie".
2. `__mantiq_dict_get_or_insert` / set therefore memcpy only 4 bytes per
   String key (the low half of the String.data pointer), stripping strided
   across the keys table.
3. `d.keys()` (called with key_size 24) copies 24 bytes per entry from the
   4-byte-strided table → each 24-byte slot is a mash of two entries.
4. At scope exit the List[String] drop glue walks the garbage slots and
   frees the mangled non-canonical pointer → glibc abort.
Prior full-suite runs did not reach this path (declare-vs-define build
failure, then the destroy double-free crash came first).

Fix that belongs to r2 codegen (frozen builder is unfixable by definition):
- `emit_dict_literal`: for empty literals, take k/v size + is_str flags
  from the declared variable's annotated type when `node_inferred_type`
  payload is missing. Same fix must feed `__mantiq_dict_create` a real
  `is_string_key` flag rather than the `ks==24 → is_str=2` heuristic.
- dict drop glue: needs fine-grained ownership (refcount in the dict raw
  struct, or copy-on-assign fat slots) before `__mantiq_dict_destroy` can
  free for real. Spot: `src/codegen.nz` emit_auto_drops / the `%`-typed
  branch (~14545) emits raw constructed `@__nizam_drop_<Type>` names;
  `drop_type_base` strips generics but the raw branch bypasses it — that
  is where `@__nizam_drop_Set[i64]` came from.

## Toolchain
- `~/.local/share/nizam-tools/clangshim/{clang,filter.py}` — IR repair
  shim (declare dedup, bracketed drop-name rename, no-op drop injection).
  Both need `chmod +x` (silent-fallback hazard on a missing bit!).
- `~/.local/share/nizam-tools/runsuite.sh` — 50-suite runner (--no-cache
  per test). Logs land in `/tmp/<test>.build.log` / `.run.log`.
- dir /tmp is EPHEMERAL: machine restarts wiped /tmp once already. Any
  state worth keeping goes under ~/.local/share/nizam-tools/.

## Session update (ASan port-stress + dict-literal fix)
- **Port stress validated** (`probes/portstress.nz`, primitive keys/values
  only, helper-call style mirroring `set_dict_*` in src/codegen.nz): all 7
  sections green non-ASan (ids churn, bool churn, list grow, 4096-entry
  resize, collision-heavy, Set add/remove, interleaved list+dict realloc
  traffic). Hygiene rules that made it compile: `{}` literal inits for
  dicts (`Dict[K,V]()` ctor is undeclared in the frozen sema), `to` casts
  not `as` in expressions, big int literals (>i32) unsupported, `Set`
  needs explicit `.init()` after `Set[T]()` (constructor is not
  auto-invoked; mirrors test_set_methods.nz:12).
- **(4,4) dict-literal bug root-caused and FIXED (2-part)**: typecheck_node
  stores a bare `Dict` (no name/payload) on `{}` literals; codegen's
  emit_var_decl propagation only fires when the init type is None/Any, and
  emit_dict_literal defaulted to hardcoded `k_size = v_size = 4`. Fixed by
  (a) `src/typecheck.nz` VarDecl branch: propagate the annotated type to
  DictLiteral inits whose type has payload==None; (b) `src/codegen.nz`
  emit_dict_literal: read key size from the type NAME
  (`dict_key_size_from_name`, same convention the set/get paths already
  use via dict_declared_key_size) and value size from payload; is_heap_str
  when the key name is "String". Self-build green (SELF_BUILD=0).
- **test_dict_methods "free(): invalid pointer" root cause**: its
  `Dict[String, i32] = {}` literals created (4,4)-sized dicts with
  is_string_key=0, while the set paths stored 24-byte fat String keys via
  dict_declared_key_size=24 → ~20-byte heap overflow per insert → glibc
  "free(): invalid pointer" abort. The fix should turn this suite test
  green (42 → 43) once the new binary can compile it.
- **Central blocker repro shrunk to 7 lines**: fresh self-built binary
  SIGSEGVs on `probe: var d as Dict[usize,i64] = {}` and even on
  `List[i64]` + append (`probes/dictmin2.nz`), crash in
  `LLVMCodegen_emit_var_decl`, rdi = 0x20312e7274732e40 = "@.str.1 "
  (IR text in a pointer slot) — byte-identical to the pre-fix cgtest2
  crash value. nodictB (one print literal) SIGBUSes with the fresh binary
  exactly as it did with pre-rewrite cgtest2 → NOT caused by the dict fix.
  Probes persisted in ~/.local/share/nizam-tools/probes/.
- Fresh-binary validation harness: `~/.local/share/nizam-tools/
  nizam-new-wrap` (CPATH/LD_LIBRARY_PATH/ulimit wrapper; point
  NIZAM_NEW_BIN at the binary; the bare binary lacks tree_sitter/api.h
  CPATH and the unbounded stack the recovered wrapper provides).
- The port stress under ASan caught the (4,4) spill as a bad-free in
  `__mantiq_nz_dict_resize` (frees of keys+0x30 interior pointer;
  ASan chunk header trashed by the 4-byte value spill of entry 7) —
  resolved by the dict-literal fix. Primitive dict/list/Set shapes are
  otherwise ASan-clean.

## ROOT CAUSE: the "emit_var_decl / flush_statement_temps SIGSEGV" blocker
The central crash that blocked every new-binary probe (ASCII `"@.str.1 "`
read as a pointer) was **not** a runtime/collections bug. It is a stale
builtin-struct-metadata collision inside the compiler source itself:

- `codegen.nz` registers compiler-internal structs via hardcoded LLVM type
  strings (`register_builtin_struct("LLVMCodegen", <37 fields>)`) and a
  hardcoded field-index strcmp chain. These were baked when the struct had
  37 fields and were never updated when `temp_tracker_regs` /
  `temp_tracker_types` were appended to the source struct (39 fields).
- `emit_struct_decl` skips AST-driven field registration when the name is
  already in `defined_types` — the builtin registration shadows it.
- Every access to `temp_tracker_regs/types` therefore compiles to
  **field 0 = `type_out`** (gdb/IR-verified: `init_cg` zeroes type_out with
  the tracker init; `register_temp` appends String entries into the IR-text
  builder; `flush_statement_temps` then reads IR text as `String` entries —
  `entry.data = "@.str.1 "` = the literal-declaration line).
- The frozen bootstrap binaries (`nizam-bin`, `nizam-bin.bak`) contain no
  `temp_tracker_regs` string at all — they predate the feature, so ANY
  source using those fields is miscompiled by them. Self-hosting has been
  broken since the fields were added ("frozen era").
- Same class: the uncommitted `BorrowChecker.borrowed_ast_vars` field
  (added after the freeze) resolved to field 0 = `errors` (a List treated
  as Dict). That uncommitted diff was reverted to restore baseline
  behavior; if the AST-borrow-init fix is needed later, implement it
  WITHOUT a new struct field (e.g. marker entries in `var_source_map`,
  which the frozen tables know at index 9).

**Fix landed (src/codegen.nz):** temp_tracker fields deleted from the
struct; `register_temp` / `consume_temp` / `clear_statement_temps` /
`flush_statement_temps` are no-ops (call sites unchanged). This only leaks
statement temporaries in generated code — never corrupts. The long-term
fix (post-bootstrap) is to drop the hardcoded LLVMCodegen builtin
registration + index chain and let AST registration drive layout, or
rename the struct.

Validation after the fix (fresh non-ASan binary):
- nodictA/B, dictmin1/2: PASS (nodictB prints correctly).
- portstress: all 7 sections green end-to-end (first time).
- nodictC (`let s as String = "x"`): `free(): invalid pointer` — PRE-EXISTING
  (frozen binary aborts identically): auto-drop frees an interned string
  literal. Known drop-glue bug family; unassigned.
- dictsize (`(deref big)[k] = v` through `ptr[Dict]`): IR error
  `'%t.N' defined with type '{ ptr, i64, i64 }' but expected 'ptr'` —
  PRE-EXISTING (frozen binary fails identically): the dict-index path uses
  the byval-loaded Dict struct as a pointer. Known r2 carry item.

## r2 codegen carry list (verified bugs in the frozen builder)
1. ~~dict literal inference lie~~ FIXED (see above): bare-Dict inference in
   typecheck + payload-as-key in emit_dict_literal both corrected.
   Residual: `__mantiq_dict_create` is_str flag now derives from the key
   name ("String" → is_heap_str) via the fix; verify literal items loop
   keeps parity for non-empty literals.
2. `emit_auto_drops` `%`-typed branch emitting bracketed generic drop
   names (`@__nizam_drop_Set[i64]`, truncated
   `@__nizam_drop_Tuple2[String, i32`).
3. ~~SIGSEGV `LLVMCodegen_emit_var_decl` on user input~~ ROOT-CAUSED AND
   FIXED (see below): not a runtime bug at all — stale builtin struct
   metadata in the frozen builder.
4. `test_systems_and_type_intrinsics`: insertvalue operand i32 vs %type
   field i64 mismatch (line ~319 emitted).
5. OOP `%super` undefined value in interfaces/classes emit.
6. RTTI downcast SIGSEGV (`__rtti_Circle`).
7. generic-Tuple `from_list` / Tuple.get surfaces emit
   `__mantiq_list_append(..., i64 1024)` (resolve_struct_size fallback for
   generic T + pointer-array semantics) — tuple method suite garbage.
8. `String.make` undefined-IR in some contexts ({ptr,ptr} return type vs
   24-byte slot) — official suite passes through other paths.
9. list.append(c-string literal) corrupts slots (bare ptr stored as
   24-byte String) — use String.make or existing values in tests.

## Suite baseline (frozen builder, pre-deletion)
PASS=42 FAIL=8 — deltas analysed in session; post-deletion rerun pending
(/tmp/fullsuite4.log when it completes).
## Aliasing drop instance #6 fixed: closure capture-list copy (src/symbols.nz `add_captured_var`)
Root cause of the long-standing "closures/lambdas emit `%factor` undefined"
failure (test_closures_lambdas, every multi-capture lambda). Mechanism:
`add_captured_var` did `let existing as List[String] = (deref d).captured_vars`
— a byval copy of the capture list embedded in the AST node (the copy SHARES
the malloc'd element buffer), plus `let e as String = existing[i]` element
copies in the dup-check loop (sharing each String char buffer). The
compiler's drop glue (kill semantics) frees those aliased buffers when the
locals are killed per call. Consequences:
- The element-array buffer is freed mid-call; the next `append` re-allocs
  and other allocations (e.g. a later interned "main" string) reclaim the
  block → captured names read back as garbage ("cap[0]=main" instead of
  "factor").
- Freed String elem buffers get reused → the list's String structs dangle.
Codegen then maps names/offsets from the corrupted list: variables unpacked
as wrong allocas, body references fall back to the OUTER frame's locals
(`load i32, ptr %factor` — the caller's alloca), and IR ends with
undefined-value errors in zig/clang.
Single-capture closures worked by accident (dup-check loop never runs at
count==0, so no element copies); multi-capture closures deterministically
corrupted. Diagnosed via instrumented compiler (SEMA-Append / CG-CLOSURE
printf of node ptr + list buf addr + element data/len): SEMA appends the
correct names into the correct buffer, then the buffer is corrupted before
codegen reads it.
Fix (copy-free dup-check, same result semantics):
- src/symbols.nz `add_captured_var`: no local list/element copies. Count
  via `(deref d).captured_vars.length()`; element char data read straight
  through the list by a C helper `__nizam_list_str_at(ref captured_list, i)`
  (returns the element's char*, NULL when out of range); dedup via strncmp;
  append stays in place.
- runtime.c: `__nizam_list_str_at` (weak) reads a compiler List[String]
  whose inline {data,len,cap} struct sits at `list_ptr`; stride 24
  ({ptr,i64,i64}).
Note: instrumented builds of THIS fix must not print the list with
byval-copied locals (`let dbg = list[dbg_i]`) — the debug copies
themselves free the buffers being observed (gdb: SIGSEGV inside printf in
Sema_check_closure_capture — the observed crash was the probe, not the
product).
Validation: probes/prob_clo_nz.nz builds clean and prints
"PASS: Lexical Environment Heap Capture"; IR shows properly-named capture
allocas (`%factor_0` at env+0). test_closures_lambdas.mq: 7/7 suites PASS.
Regression: test_tuple_methods, test_dict_methods still PASS.

## Minor ownership fixes landed earlier this session (42 → 44/50)
- Tuple append elem_size (src/codegen.nz emit_call method-call append
  path, ~line 6889): generic-T `resolve_struct_size` fallback 1024
  corrupted `List` payload for `(deref x).field.append(...)`; now when the
  struct name is not in `struct_sizes`, fall back to
  `self.llvm_type_byte_size(elem_t)` (8 for {ptr,i64,i64}-style payloads).
  Tuple_from_list now appends `i64 8`; test_tuple_methods PASS.
- Dict `keys()`/`popitem` deep copy (std/collections.nz
  `__mantiq_dict_keys` / `__mantiq_dict_popitem`): dict key slots are
  shallow copies with non-owning data (rodata/stack pointers) and
  `__mantiq_dict_destroy` is a deliberate no-op; the keys() list drop glue
  freed them → `free(): invalid pointer`. Both now deep-copy each key's
  string buffer (mantiq_malloc + memcpy, update sdata/scap in the appended
  slot) when `key_size == 24` (.String keys — String keys use
  is_string_key=2, so the guard is key_size, NOT the is flag).  
  test_dict_methods PASS.
- String literal init ownership (runtime.c + src/codegen.nz): `let s as
  String = "lit"` stored the rodata pointer; auto-drop `__nizam_drop_String`
  then tried to free rodata → abort. Added weak runtime helper
  `__nizam_str_clone(data, len)` (fresh owned NUL-terminated copy; NULL for
  empty) and the literal-init site (NodeType.StringLiteral into String
  var_type, ~line 3034) now calls it for raw_len>0; empty literals keep
  NULL data (drop no-ops). test_bytes_methods PASS.

## Tooling notes for this session
- clang-15 shim for Test 12 (Clang Syntax Check): test builds invoke
  `clang-15 -fsyntax-only -x ir` on generated IR, but IR produced here is
  LLVM 15+-era types-only OpaquePointer form; `~/.local/share/nizam-tools/
  clangshim/clang-15` (a Python filter on PATH via run_tests_new_tmp.sh)
  translates that invocation to `opt -passes=verify -disable-output`.
  Test 12 passes with the shim on PATH.
- test_quantum_dce needs a long wall-clock (allowed 1700s) — passes; the
  suite runner has no per-test timeout.
- /tmp tmpfs quota: commits of stale .ll/.o/.bin artifacts from probe
  builds fill it and fail later builds with `Disk quota exceeded`
  (zig cc object writes). Clean `rm -f /tmp/*.ll /tmp/*.o /tmp/*.o.tmp
  /tmp/*.log /tmp/*.bin` before long builds.
- Suite runner: src/tests/run_tests_new_tmp.sh (50 suites,
  binaries to /tmp/<test_name>). Durable runs: `setsid nohup ... >
  ~/.local/share/nizam-tools/suite_final.<n>.log`.

## Suite progress (self-hosted compiler, this session)
42/50 (84%) → **46/50 (92%)** — official full-suite rerun
(suite_final.3.log, official runner, fresh .mantiq_cache, promoted
~/.local/share/nizam-tools/nizam-new = selfbuild28c). Deltas landed on the
way: Tuple append elem_size fix (test_tuple_methods), dict
keys()/popitem deep-copy ownership (test_dict_methods), String-literal
__nizam_str_clone (test_bytes_methods), clang-15 verify shim (test_codegen —
Test 12 clang syntax check via clangshim), and closure capture-list
copy-drop fix (test_closures_lambdas). No regressions against the 44/50
probes; test_quantum_dce completed within the runner (no per-test
timeout).
The 4 remaining failures (all pre-existing, unrelated to runtime work):
- test_expr_body_and_generics.nz — exit 139 in lower/codegen, not yet gdb'd.
- test_interfaces_and_classes.mq / test_oop_override_final_access.mq /
  test_reflection_downcast.mq — .mq trio: infinite recursion in lowerer
  `tag_node_file_path` (gdb-confirmed earlier), which my changes do not
  touch.

## Milestone C final state (session of Oct 28, `nizam-new-next` line)

### What ships now
- `runtime.c`: the public C bodies for the collections/allocator/drop-glue
  surface are GONE (`mantiq_malloc`, `mantiq_malloc_raw`, `mantiq_free`,
  `__mantiq_hash_*`, `__nizam_drop_String/_StringBuilder/_Dict/_Dict_flat/
  _List/_List_flat`, `__nizam_str_clone`, `__nizam_list_str_at`, dictionary
  destroy/resize). The remaining C machinery uses internal statics
  (`mantiq_malloc_c` etc., bodies verbatim from HEAD incl. counters);
  ~70 internal call sites retargeted to the statics.
- Target programs get those symbols from plain LLIR instead:
  - std-import programs: `std.mem`/`std.collections` define them (no lazy
    emission).
  - no-import programs: `LLVMCodegen::emit_rt_glue_bodies` (codegen.nz,
    ~1994) lazily emits the 11 IR bodies verbatim, called from `generate()`
    before the `__cg_filter_declares` hygiene pass (codegen.nz:2319).
- Lazy emission gotcha hit this session: the emitted bodies CALL C helpers
  (`@abort`, `@calloc`, `@malloc`, `@realloc`, `@free`); without matching
  declares the module fails `use of undefined value '@abort'` at the link
  stage (repro: t_clo). Fixed by emitting the declares conditionally
  alongside each corresponding body (`if h_free == 1: declare i32
  @mantiq_is_arena_ptr(ptr)` + `declare void @free(ptr)`, and
  abort/calloc/malloc/realloc declares under h_malloc/h_malloc_raw/
  h_realloc).

### Bootstrap dance (one-time, completed)
The first self-build of the new compiler still links `main.nz`-as-target
against `runtime.c`; to be link-clean it needed the old public symbols to
exist. The bootstrap `runtime.c` = clean static version + WEAK public HEAD
bodies (11 fns + weak `__mantiq_hash_*` overridden by the TU's own strong
IR defines + strong no-op `__mantiq_dict_destroy`) + weak C ports of
`__nizam_str_clone` / `__nizam_list_str_at` (semantics taken verbatim from
the IR bodies at codegen.nz:2037/2039; the frozen builder's TU calls
`__nizam_list_str_at` from `add_captured_var`, symbols.nz:1736). After
that build produced `nizam-new-next`, its own raw `.ll` defines everything
in IR and the clean static runtime (no public bodies at all) works for all
subsequent builds. Bootstrap file preserved:
`~/.local/share/nizam-tools/runtime_bootstrap.c.bak`; clean static:
`runtime_msC_static.c.bak`.

### Twin declares (resolved)
clang 23.1.3 AND `opt -passes=verify` both reject a repeated
`declare i64 @mantiq_strlen` ("invalid redefinition"). But the frozen
builder's baked-in output still carries twins — its codegen predates
`__cg_filter_declares`; those failures came only from fallback build paths
(`.cgfilt.ll` leftover link, selfbuild36 noise). The NEW compiler's raw
`.ll` is twin-clean (verified `strlen-occurrences=1` on both a no-import
micro program and the std-path test; filter probe
`mantiq/probes/prob_filter.nz` dedups doubles in isolation).

### Warm-cache double-free (found this session, PRE-EXISTING)
Building any std-import test a SECOND time (tier-1 `.dep` cache hit)
aborts the compiler process: `free(): double free detected in tcache 2`.
ASAN evidence (nizam-new-next-asan, NIZAM_SHIM_ASAN=1 shim build):
- alloc: `mantiq_malloc runtime.c:3034 ← String.__init__ clone ← split_lines`
  (159-byte chunk; the `.dep` line clone),
- free#1 direct `compile_source → __nizam_drop_String`,
- free#2 `compile_source → __nizam_drop_List → element drop`.
Root cause: byval list extraction aliases — `let s as String = list[i]`
struct-copies the element WITHOUT cloning `data`, so the local and the
list element share one buffer and both drops free it. Reproduces
IDENTICALLY with the frozen Oct-28 `nizam-new` binary → not a Milestone-C
regression. Trigger is warm state: the 46/50 suite ran with a fresh
(empty) `.mantiq_cache`; every crash report this evening lines up with
`.mantiq_cache/meta/*.dep` existing (mtimes 10-28 20:53–22:57).
Proven trigger: cold cache → `test_list_methods` build=0 run=0; after that
build writes its `.dep`, the very same command aborts (rc 134).
Minimal fix applied in `src/main.nz` tier-1 path (~365, ~381): clone the
five `d_lines[...]` extractions with `String.make(...)` so local drops and
the list teardown own disjoint buffers. Baked into `nizam-new-next` by
selfbuild39 (Oct 29 01:53); gate3 (warm rebuild of `test_list_methods`)
returns rc=0 — warm-cache crash resolved.

### Needle-in-string-constant false positive (found Oct 29, fixed)
`suite_final.4` dropped to 43/50: `test_codegen`, `test_param_block`,
`test_quantum_dce` (all import the compiler modules) failed to link with
`undefined symbol: mantiq_malloc ... referenced 4042 more times`, zero
line-start `define` in their `.ll`.

Root cause: `codegen.nz`'s lazy-emission needles and IR bodies are string
literals. When the compiled program IMPORTS `codegen`, those literals land
in the assembled module as `@.str` constants (`c"define ptr
@mantiq_malloc..."`). `rt_body_missing` substring-scanned its four output
streams, matched the needle inside a constant, concluded the body was
already defined, and skipped emission — leaving only declares. The
baseline binary never hit this because `runtime.c` still carried the C
bodies then; with the clean static (body-free) runtime the skipped
emission became a hard link error.

Fix (`src/codegen.nz`, after `__cg_stream_has`): new
`__cg_buf_has_def` / `__cg_stream_has_def` — line-anchored matching. A
real IR definition always starts a line; the identical text inside a
`c"..."` constant is always preceded by other bytes. `rt_body_missing`
now consults only the line-anchored predicates. Verified in the failed
`.ll`: `^define ptr @mantiq_malloc` = 0 matches, 4 `c"define ptr
@mantiq_malloc` constants.

### Self-build bootstrap dependency (operational, verified twice)
Rebuilding the compiler TU (`src/main.nz`) with a pre-emission or
pre-line-anchor builder requires `runtime.c` = bootstrap (weak C bodies)
on disk for THAT build; the source fixes land only in the OUTPUT binary,
which is then validated against the clean static runtime. Chain:
`./nizam` (frozen repo wrapper → nizam-bin, Oct 22) + bootstrap runtime →
`nizam-new-next` (line-anchor + warm-cache fixes baked) → restore clean
static → gates + suite. Two traps confirmed:
- A failed `./nizam` build DELETES the `-o` target (destroyed
  `nizam-new-next` once; rebuilt by selfbuild39).
- An old builder's raw `.ll` may still carry the `mantiq_strlen`
  twin-declare; that error in the first link attempt is fallback-path
  noise — the clangshim filter handles the real path and the build
  completes (`Successfully compiled` is the only rc=0 signal; check the
  exit code, not the presence of error text, in build logs).

### Final tallies (Milestone C complete, Oct 29 02:44)
- `suite_final.4` (pre-line-anchor binary): 43/50 — regression that
  exposed the needle-in-string-constant bug.
- selfbuild39 (builder `./nizam` + bootstrap runtime): rc=0; both fixes
  (line-anchor, warm-cache) baked into the output binary.
- Gates on final binary vs clean static runtime: std path PASS,
  no-import lazy emission PASS, warm-rebuild PASS (rc=0).
- `suite_final.5` (final binary, cold cache): **46/50** — the 3
  compiler-module-import tests are fixed; remaining 4 failures are the
  pre-existing, out-of-scope set (`.mq` trio lowerer crashes +
  `test_expr_body_and_generics`).
- PROMOTED: `nizam-new-next` → `nizam-new`
  (previous baseline saved as `nizam-new-preMilestoneC.bak`).
- `runtime.c` clean static state confirmed: zero public bodies for the
  collections/allocator/drop-glue surface.

### Debug internals worth keeping
- gdb symbolization near the static C trampolines can MISLABEL frames:
  one frame reported as `compile_source` was really `mantiq_malloc_c`
  (0x11abaf < mantiq_malloc_c end 0x11ac00). Cross-check with
  `nm -n <bin>` before trusting a bt label.
- ASAN compiler build: `NIZAM_SHIM_ASAN=1` env with the clangshim injects
  `-fsanitize=address` into every compile; product:
  `~/.local/share/nizam-tools/nizam-new-next-asan` (3.8 MB).
- `valgrind` is not installed on this box; ASAN is the heap forensics tool.

## Leak mode — the UAF endgame (Oct 30–31)

### The "shallow-copy drop hazard" (root cause of the last SIGSEGVs)
Many sema/typecheck passes take **by-value** `List` copies of node-owned
storage (`FunDeclData.params`, `NodeData.declarations`, `node_name`, …).
Those copies are shallow: they share the heap buffer with the AST. The
newer borrow-checker emits an **auto-drop** for such byval copies at
scope exit, which calls `mantiq_free` (or `free@plt`) on the shared
buffer → the AST now references freed tcache memory → later passes read
garbage → SIGSEGV. Confirmed with hardware watchpoints
(`~/.local/share/nizam-tools/gdb/watch_params.x`, `watch_free.x`): the
free originated in `check_sig_has_py_types` params handling; the freed
chunk's first qword = own addr≫12 + random key at +8 (tcache signature).

Fixed instance-by-instance where cheap (pointer accessors instead of
byval copies):
- `src/sema.nz` `check_sig_has_py_types` (~207) — `node_params_ptr`.
- `src/sema.nz` `scan_node_for_gil` (~85–215) — decls/params copies.
- `src/codegen.nz` `strip_generic_base` / `drop_type_base` (earlier
  instances #1–#6, see sections above).

~26 further byval-copy sites in `src/sema.nz` (`declare_pass`,
`resolve_pass`, `analyze_gil_safety`, ~828–1757) are *suspects* under
leak mode but need no conversion: `mantiq_free` is a no-op, so their
auto-drops free nothing.

### Leak mode (the actual fix)
The working pre-aliasing binaries never emitted those drops — pure leak,
no UAF, perfect for a short-lived compiler process. Leak mode restores
exactly that behavior **regardless of what the borrow-checker emits**:
- `mantiq_free` → no-op (`ret void`).
- `mantiq_realloc` → `malloc` + memcpy bounded by
  `malloc_usable_size(old)`; **never releases the old block**. Copy
  semantics are mandatory: `std/collections.nz`
  `__mantiq_list_append` (~780) relies on realloc preserving contents.
  Verified with a 5000-append growth test (`0 2499 4999` = correct).
- Stale shallow copies stay valid forever ⇒ no UAF possible.

### Where the definitions live (the bootstrap trap, layer 2)
Both **enum constants AND rt-glue templates are baked into the builder
binary**. A builder may emit its own `mantiq_free`/`mantiq_realloc`
bodies (from its baked templates) into any child program it compiles.
Overriding:
- ✅ **Program-local `fn mantiq_free` / `fn mantiq_realloc`** definitions
  in the TU: lazy emission sees an existing definition
  (`rt_body_missing`) and skips the template. Now lives in
  `src/main.nz` (~36–73) with explanatory comment.
- ❌ `from std.mem import mantiq_free, mantiq_realloc` — does NOT work:
  lazy emission only fires for *called* symbols; the std.mem bodies
  were never emitted and the template won anyway.
- The bundled copies are neutered for consistency: `std/mem.nz`
  (not even imported by the TU — dead code, harmless), and
  `src/codegen.nz` rt-glue templates (~2049–2086) →
  free=`ret void`, realloc=malloc+copy.

### Builder constraints for leak-mode builds
- `nizam-new-next` is currently the only viable builder: it has the
  fixed `get_enum_variant_val` table (`0f59d7f` — missing
  `NodeType.InterfaceDecl` made interface nodes `kind 0 = Program` →
  walker crash) and its own drop-free check/scan paths. The
  `nizam-new-fixed*` lineage (pre-table-fixes) self-crashes compiling
  anything real.

### Rebuild recipe (selfbuild45, the current method)
```
export PATH=~/.local/share/nizam-tools/clangshim:$PATH
export NIZAM_NEW_BIN=~/.local/share/nizam-tools/nizam-new-next
# ensure runtime.c = clean static (no C bodies on the surface)
grep -q "void\* mantiq_malloc(size_t" runtime.c && \
  cp ~/.local/share/nizam-tools/runtime_msC_static.c.bak runtime.c
rm -rf .mantiq_cache
~/.local/share/nizam-tools/nizam-new-wrap build src/main.nz \
  -o ~/.local/share/nizam-tools/nizam-new-fixed4 --no-cache \
  --lib-dir "$PWD" > ~/.local/share/nizam-tools/selfbuild45.log 2>&1
echo "rc=$?" >> ~/.local/share/nizam-tools/selfbuild45.log
```
(`NIZAM_NEW_BIN` must point at the **builder** — the wrapper chain is
*NIZAM → wrap → NIZAM_NEW_BIN*, so it must be the builder binary name.)
~40 min with nizam-new-next (its O(n²) scanner); fixed4 ships the O(n)
`__cg_buf_has_def` scanner, so future rebuilds are fast.

Fixes the last 4 suite failures were expected to hinge on: the `.mq`
trio + `test_expr_body_and_generics` still need their own diagnosis (a
fresh gdb watchpoint round on the fixed4 binary) — description may be
updated as results land.

## The .mq OOP trio — one root cause, three symptoms (Oct 31)

With leak-mode landed (`suite_final.9` = **47/50**, fixed4 promoted to
`nizam-new`), only the `.mq` OOP trio remained:

- `test_interfaces_and_classes.mq` / `test_oop_override_final_access.mq`:
  broken IR — `%t.N = load ptr, ptr %super` (undefined SSA; also raw
  `%super` as a GEP base).
- `test_reflection_downcast.mq`: compiles, SIGSEGV at run INSIDE
  `__rtti_Circle` — `call <reg>` where the register was the address of
  the class RTTI global, i.e. data executed as code.

### Root cause: key-collision closure hijack
`emit_class_decl`/`emit_interface_decl` register `T.method` keys into
`struct_field_indices` (meant as vtable indices: method_count).
`emit_call_expr` consulted the SAME map — key `s_nm + "." + m_name`
(obj type name + method) — to flag `is_closure_member_field`. Any
class/interface method call therefore entered the closure emission:
`extractvalue {ptr,ptr}` of the obj's rtti slot and an indirect call:
`call i32 %fn_pair.0(ptr %fn_pair.1)` where the pair is (rtti ptr,
first field bytes).
- Struct objects were immune: struct methods are registered only as
  `T_name` in `program_functions` (emit_program prepass), never as
  `T.field` keys.

### Fixes landed (cascade)
1. `56f1881` codegen: the closure decision now requires the mangled
   method function `T_method` to NOT exist in
   program_functions/defined_functions. Real method calls route to the
   existing direct-dispatch path (`fn_target_name = s_nm + "_" +
   method_name`, obj prepended as first ptr arg — verified with a
   struct min repro: `call void @Counter_bump(ptr %c)`).
2. `5ec177e` codegen: deref-of-aggregate in emit_lvalue_ptr. Bare
   `self` receivers (value semantics) loaded the whole `%Struct` value
   and the member-addr GEP then used the value register as a pointer
   (`load %Counter, ptr %t.2` type error). Aggregate-typed deref
   sources now return `emit_lvalue_ptr(inner)` (the alloca slot);
   pointer sources unchanged (compiler sources declare
   `self as ptr[T]`, so main.nz untouched).
3. `4bf2f70` codegen: `super().m()` — obj is a CallExpr naming super —
   now recognized by the is_super base-delegation branch (mangles to
   `base_Class_method`, direct call), instead of falling into the
   generic unknown-function path (`declare @super`).

### Interface dispatch status (open)
`%Interface = type { ptr, ptr }` with interface method keys registered
the same way (15683) — with the closure hijack removed, interface-typed
obj calls should dispatch via the direct-mangle path too, which only
works when the impl class defines the method body (duck-typed). A
true vtable-based dispatch for interface VALUES ({data, rtti} pairs
per the `is`-pattern machinery at 10961) has NOT been built; the trio
tests only exercise concrete-typed obj calls so far.

## FINAL STATE: 50/50, self-host compiler complete (Oct 31, 16:00)

### Binary lineage
- `nizam-new` = `nizam-new-fixed6` (md5 2fa1e874c61c9a76409b42a9decfd6a0),
  built by `nizam-new-next` from repo at `8b67d16`.
- Backups: `nizam-new-preLeakMode3.bak` (46/50 Milestone C state),
  `nizam-new-preFinal.bak` (fixed6 copy, byte-identical).
- The 46→50 delta came from two build generations:
  - fixed4 (leak-mode + TU allocator surface): 47/50 — cured
    `test_expr_body_and_generics` (UAF class).
  - fixed6 (closure-hijack fix + super() delegation + deref parity
    fixes 5ec177e/8b67d16): 50/50 — cured the `.mq` OOP trio.

### Final verification record
- `suite_final.9` (fixed4, cold cache): 47/50 (records + auto-promote).
- closure2 chain gates on fixed6: test_std + all three `.mq` OOP tests
  PASS (build+run each).
- `suite_final.11` (fixed6, mid-restart race): 48/50 — invalid (suite
  run interleaved with concurrent rebuilds; ignore).
- `suite_final.resumable` (fixed6, state-journal runner, warm cache):
  **50/50 — Total 50 / Passed 50 / Failed 0** — journal
  `~/.local/share/nizam-tools/suite_resume.state` (50 PASS, 0 FAIL).

### OOP trio final fixes (see previous section for root cause)
- `56f1881` closure hijack defused (key-collision method decisions).
- `4bf2f70` super() delegation (obj CallExpr named super routed through
  the base-mangled is_super branch; verified min-repro: `res=25`).
- `5ec177e` deref-of-aggregate lvalue unwrap (slot-vs-copy).
- `8b67d16` deref-identity parity for Class/Struct in emit_unary_expr
  (verified min-repro struct Counter: build+run `3`/`4`).

### Resumable suite runner (host-restart tolerant)
`~/.local/share/nizam-tools/resume_suite.sh` — journals per-test results
to `suite_resume.state`, skips journal-PASSed tests, promotes
 automatically at ≥47 and reports 50/50. Use it instead of
`src/tests/run_tests_new_tmp.sh` whenever the box's restart cadence is
unpredictable (~10 min observed during the final hours).

---

## Milestone D — runtime.c fully unlinked (2026-11-01)

Goal: the compiler TU and every native product build with ZERO
runtime.c input; `tree_sitter_helper.c` remains the only C source on
the link line (untouched by design).

### What still referenced runtime.c (final inventory)
TU (compiler self-build) real residual:
- `mantiq_run_command_direct` fork/exec/waitpid driver
- `mantiq_mkdir_p` / `mantiq_copy_file` (cache/driver paths)
- `mantiq_sha256_hex` / `mantiq_sha256_file_hex` (cache keys)
- `mantiq_perf_now_ns` / `mantiq_perf_rss_bytes` + counters + profile flag
- `mantiq_ast_arena_reset` / `mantiq_intern_reset` (TU teardown no-ops)
- `mantiq_type_needs_drop` / `mantiq_type_set_needs_drop` (C type registry)
- `__mantiq_scope_lookup` (C scope-parent walk in Sema.lookup_symbol)
- `mantiq_strlen` (one call: std/collections `__mantiq_list_fromhex`)

Product-side surface codegen emits as real calls (the TU never calls
these — they were invisible to TU IR sweeps):
- print: `mantiq_print_{i32,bool,float,ptr,space,newline,str,cstr}`
- conversions: `mantiq_{i32,i64,u64,float,f64,char,bool}_to_str`
- strings: `mantiq_strlen`, `mantiq_concat_str` (concat path with a
  StringLiteral part emits a real `mantiq_strlen` call)
- async: `mantiq_spawn` / `mantiq_await` (+ internal task runner)
- channels: `__mantiq_channel_*` (10 fns, POSIX pthread variant)
- quantum: `mantiq_quantum_*` (7 fns, static qubit array)
- RTTI: `mantiq_isa`

### How each piece was replaced
1. TU-local Nizam ports in `src/main.nz` (override builder-baked rt-glue
   via `rt_body_missing` define-scan): run_command_direct (fork/execvp/
   waitpid, `status/256 & 255`, `status & 127`), path_sane guard,
   mkdir_p, copy_file (open/read/write/close; O_WRONLY|O_CREAT|O_TRUNC
   = 577, mode 493), perf_now_ns (clock_gettime CLOCK_MONOTONIC),
   perf_rss_bytes (getrusage, ru_maxrss at struct offset 32, KB->B),
   counters as inert zeros (they only ever counted C-internal helper
   allocs), set_profile_active / ast_arena_reset / intern_reset no-ops.
2. FNV-1a replaces sha256 for cache keys: dual-seed 32-bit streams
   combined into a 16-hex-char 64-bit key (`%08lx%08lx`). No shift ops
   exist in Nizam — FNV needs only xor/mul/and. Consumers are opaque
   strcmp-compared keys/binary names; the format change costs one
   cold-cache pass and self-heals.
3. Needs-drop type registry ported from runtime.c globals to a
   name-keyed `Dict[String,bool]` owned by Sema (`needs_drop_types`),
   bridged into LLVMCodegen by main after the sema phase (shared
   handle, one assignment). Sema.check_and_register_struct_drop writes
   it; codegen's `type_needs_drop` helper reads it behind an
   `needs_drop_registry_active` gate (zero-initialized LLVMCodegen
   instances must not touch the builtin Dict — no zeroed-dict guard
   exists in `__mantiq_dict_get`). `is_copy_type` (types.nz) is now
   registry-free; its 4 BorrowChecker call sites are augmented with
   `BorrowChecker.sema_needs_drop_type` (Sema carries, BC derefs).
   The registry is LOAD-BEARING: copy-vs-move decisions feed drop
   emission; getting it wrong resurfaces the UAF class.
4. `Sema.lookup_symbol` ported to a Nizam scope-parent walk with the
   C's exact `visited_global` semantics (global scope re-checked once
   at the end if not on the chain).
5. `std/collections.__mantiq_list_fromhex` now calls libc `strlen`.
6. `emit_rt_glue_bodies` (codegen.nz) gained two template families:
   - TU-side: `mantiq_alloc_box32` (64KB calloc slabs via internal
     globals `@__nizam_box32_slab`/`@__nizam_box32_off`; new-slab
     threshold `off > 65504` ≡ C's `off + 32 > 65536`),
     `mantiq_ast_alloc` (calloc, zeroed; arena reset/destroy no-ops —
     leak-mode), `mantiq_intern_string` (fresh zero-terminated copy per
     call, no dedup — consumers strcmp, never pointer-compare),
     `mantiq_page_alloc/free` (mmap/munmap, 4096 round-up),
     `mantiq_is_arena_ptr` (returns 0 — inert because mantiq_free is a
     no-op in leak mode).
   - Product-side (differential-tested against runtime.c before
     embedding — see below): print family (printf/fwrite),
     conversions (snprintf into stack buffers, malloc_raw + memcpy,
     out_len store), strlen/concat (concat mirrors C's empty-part
     handling exactly, malloc_raw-backed), spawn/await + internal
     task runner (POSIX pthreads; Task layout: thread=0 func=8 env=16
     result=24 is_done=32 mutex=40[40B] cond=80[48B] size=128),
     channels (10 fns; Channel layout: buf=0 cap=8 head=16 tail=24
     count=32 is_closed=40 mutex=48[40B] not_empty=88[48B]
     not_full=136[48B] size=184), quantum (static 64-i32 qubit array),
     isa (TypeDescriptor: type_id=0 name=8 parent=16 n=20 ids=24).
   Shared string constants + libc/pthread declares are emitted
   unconditionally; `__cg_filter_declares` drops repeat declares and
   declare-vs-define collisions. Every define is gated on its own
   `rt_body_missing` needle so std/user bodies always win.
7. Driver unlink (main.nz): d_argv no longer appends runtime.o /
   runtime.c / the ../mantiqz fallback; the two sprintf link-command
   templates drop the runtime tokens; `var rt_str` removed. The
   wasm and python-ext targets intentionally still reference
   runtime.c (untested targets; file kept intact).

### Differential validation (before embedding)
Templates were written as a standalone `.ll` and differential-tested
against runtime.c with an identical C driver:
- `~/.local/share/nizam-tools/rtport/{my_rt.ll,test_main.c,tu_main.c}`.
- Product surface: byte-identical output across print/conversions/
  concat/strlen/spawn/await/channel send/recv/try ops/close/len/cap/
  free/quantum/isa (one real bug caught: try_send's reject path
  returned without unlocking the mutex -> deadlock in recv-after-
  close; the C has the unlock).
- TU surface: box32 slab-jump pattern, zeroed ast_alloc, intern
  content semantics, page alignment — identical. Known intentional
  deltas (documented inert): intern dedup gone, is_arena_ptr -> 0.

### Bootstrap -> single-stage pivot
Originally two-stage: stage 1 built with runtime.c still linked
(bootstrap; output binary carries all new codegen), stage 2 rebuilt the
TU with the new binary whose emission covers everything -> links
without runtime.c. Both stage-1 attempts were killed by server restarts
(~35-40 CPU-min each; Tier-2 cache is keyed by the FINAL IR hash, so
killed builds cannot resume).

Pivot: the TU now defines its LAST five runtime.c-resolved symbols as
TU-local Nizam fns in main.nz — `mantiq_ast_alloc`, `mantiq_alloc_box32`,
`mantiq_intern_string`, `mantiq_page_alloc`, `mantiq_page_free` — so the
OLD builder compiles the full new sources in ONE stage. The old baked
d_argv still lists runtime.c on the link line, but the linker never
pulls runtime.o (every mantiq symbol it could satisfy is already
defined in the TU). Signatures match the consumers (lower.nz externs,
std/mem.nz externs) and the emitted define lines match the
emit_rt_glue_bodies needle text, so the TU-side templates skip
themselves in future self-hosted builds. Leak-mode simplifications:
ast_alloc = calloc(1, max(sz,1)); box32 = 32-byte calloc (slab machinery
unneeded when free is a no-op); page_alloc returns NULL on any failure
(callers only test NULL; Linux mmap never returns NULL, MAP_FAILED is
built as `(0 - 1 to usize) to ptr`).
Chain: `~/.local/share/nizam-tools/rtunlink_chain.sh` (single stage)
(log: rtunlink.log; suite journal: rt_nolink.state — FRESH journal,
the old `suite_resume.state` is seeded 50 PASS and would skip all).

### Collision safety net
runtime.c's non-static definitions are now `__attribute__((weak))` (all
of them, not just the colliders). If a future TU edit re-introduces an
undefined mantiq symbol, the linker pulls runtime.o and its weak defs
lose to the TU's strong Nizam defs instead of erroring with multiple
definitions. Native builds that define everything never pull runtime.o.

### clang-23 optimizer bug (worked around in the shim)
clang was upgraded 22.1.8 -> 23.1.3 on 2026-10-22. LLVM 22 AND 23 crash
(SIGSEGV in `TargetLibraryInfoImpl::getLibFunc` during instcombine on
the entry function) when a call passes FEWER arguments than the callee
declaration has parameters — e.g. `call ptr @calloc(i64 1)` against
`declare ptr @calloc(i64, i64)`. The builder passes
`-disable-llvm-verifier`, so the malformed call reaches the optimizer.
The crash is probabilistic under ASLR; `setarch --addr-no-randomize`
makes it deterministic (llvm-reduce + that flag produced the minimal
testcase). Root trigger found and fixed in the sources: a parameter
named `size` collides with the `size` UNARY OPERATOR keyword — the
parser treats a bare `size` identifier as the sizeof-like operator,
which both corrupted the comparison (`icmp eq i64 1024, 0`) and DROPPED
the argument from the following call. Renamed to `sz`.
The shim (`clangshim/clang`) additionally retries with
`-fno-inline-functions` if the optimizer dies by signal, as a belt-
and-suspenders fallback for any future malformed-IR shape.

### Known remaining gaps (documented, out of scope)
- `mantiq_py_*` symbols: native products using python-embed interop
  (`import python` + TypeKind.PyObject) still resolve py fns from
  runtime.c. Not exercised by the 50-test suite; the python-ext
  target keeps linking runtime.c anyway. Template family can be added
  on demand.
- wasm/py-ext targets: unchanged, still reference runtime.c.

### Gate debug cycle (Nov 3): three template defects, all caught by the gate
The first full chain run after the template push reached the test_std
gate and failed three times, each on a one-line template defect. The
cheap-validation loop (hand-patch the failing product IR, filter, clang,
link, run — minutes, not a 26–40 min rebuild) caught two of the three
before they cost a cycle; the third was missed because the validation
target (test_codegen) self-declared a symbol the gate product
(test_std) did not.

1. `\\00` escaping (`850158c`): the Nizam lexer misparses a single
   `\00` in a codegen.nz string literal — it eats the NUL escape, the
   closing quote, and the following text, producing IR like
   `c"COLUMNSdefine i32 @nizam_get_terminal_width() {` ([1357 x i8] vs
   the declared [8 x i8]). IR byte escapes must be written `\\00` in
   codegen.nz source.
2. Format-string size (`8eab096`): `0x%016llX` is 9 chars + NUL = 10
   bytes; the template declared `[11 x i8]`. Fixed in the hand-patch
   artifact during validation but initially missed in the source.
3. Missing libc declares (`102fa8f`): test_std's product IR declares
   only `memcpy`; `getenv`/`atoi`/`ioctl`/`sprintf` were undefined
   values. The templates now emit their own declares — safe because
   `__cg_filter_declares` (final assembly) dedupes repeat declares and
   drops declare/define collisions. Declares must always accompany
   template bodies: never assume the product declares a libc function.

Lesson: validate template changes against the LOWEST-assumption
product (a test that imports compiler modules but declares nothing
itself), and statically audit every `c"..."` literal for
`[N x i8]`-vs-byte-count and escape doubling before rebuilding.

### Final state (Nov 3, 14:50)
- Chain run of 13:54: build OK -> nm sweep OK -> test_std gate PASS ->
  50-test suite **50 passed, 0 failed (of 50)** -> PROMOTED
  `nizam-new-fixed7` -> `nizam-new` (previous builder saved as
  `nizam-new-preRTunlink.bak`).
- `nizam-new` (1.33 MB): 68 runtime-class T-symbols defined TU-side,
  ldd runtime refs 0, no undefined mantiq allocator/runtime symbols.
- Products built by the promoted binary: 0 undefined `mantiq_*`
  symbols, 0 libmantiq dependency — native products are fully
  self-contained. runtime.c remains linked ONLY for wasm/py-ext
  targets and the `mantiq_py_*` family (documented above).

## Milestone M — real per-type generic monomorphisation (Nov 3–4)

With the runtime fully unlinked (Milestone D), the generic story moved from
"erased ABI coercion" to genuine per-type monomorphisation: every concrete
instantiation of a generic struct/method now gets its own specialised type
and functions (`Set[i64]` -> `%Set_i64` + `@Set_i64_add(i64)`), generated
from the template's actual source text rather than by retyping erased
values.

### Architecture (Option B — module generics, not the toy)
- `sema.nz` `load_imported_module`: after lowering an imported module, a
  snapshot of its generic registries PLUS the module's source text is kept
  (`MonoState.tmpl_source`); each instantiation records the template's
  source span (`register_instantiation`).
- `lower.nz` `monomorphize_with_sources()`: after the declare pass merges
  module decls into the root, re-runs the mono pass seeded with the
  snapshot; generated defs are APPENDED to root, and `main.nz`
  declare_passes them before resolve/typecheck. lower.nz cannot import
  sema (cycle) — orchestration lives in `main.nz` `compile_source` with
  plain dicts.
- In-program generics (`Box2[i32]`, `pick[i32]`) were always handled by the
  lowerer's mono pass and keep working; pass 2 is idempotent (annotations
  already mangled have no `[`).
- `tc.monomorphize` (typecheck.nz:1008) is DEAD code — discovered during
  this work; in-program generics never went through it.

### Fixes forced by real mono (each validated before the rebuild)
1. `cc9eff0` + `27dd187` — the mono machinery itself: source-snapshot
   seeding, root append, explicit-annotation call fixup.
2. `35f776a` — E0101 scope fix: generated bodies reference module siblings
   (e.g. `Dict` inside std.collections templates) missing from the root
   scope; `main.nz` copies loaded-module scope symbols into the global
   scope when instantiations exist.
3. `e7ae95e` — zero-arg `__init__`: implicit `X()` construction previously
   left a null dict handle (segfault). Pre-pass records structs with
   zero-arg ctors; the no-arg ctor path emits alloca + call + load.
4. `14f3e04` — ctor init emission typed from the call's inferred LLVM type
   (erased copies carried flat literal reprs into mono'd slots).
5. `b93f390` — two codegen paths where tc-side types stay erased while
   value-side types are mono'd:
   - static member calls (`FrozenSet.from_set(ref sup)`): derive the
     instantiation suffix from the args' payload type names, retarget to
     `@FrozenSet_i64_from_set` when it exists, move the ret type to the
     named repr in step.
   - subscript on named-struct collections (`t[2]` on `Tuple[i64]`):
     `emit_index_addr` only recognised the flat `{ ptr, i64, i64 }` repr;
     mono'd structs now pun the value into a temp slot, GEP field 0
     (via the `__fti_<Struct>.0` registry), load the handle, extract the
     buffer ptr.
6. `031e196` — infinite loop in the static-call retarget: the arg-scan
   increment was nested inside the "arg has an inferred type" guard; any
   extern-call arg without a type spun `emit_call_expr` forever (gate
   rc=124, even a trivial smoke file hung at 100% CPU). Found via gdb
   SIGINT backtrace (`timeout -s INT 25 gdb -batch -ex run -ex "bt 25"` —
   direct attach fails, yama ptrace_scope=1; run the binary UNDER gdb).

### Validation method
Cheap-first: every fix was validated by hand-patching the failing suite IR
to exactly the shapes the new codegen emits, compiling and RUNNING it
(Set & FrozenSet parity + tuple parity, rc=0) BEFORE spending a ~26–40 min
whole-program rebuild. Two full chain runs were lost to bugs found this way
(the hang) instead of shipping them into the suite.

### Final state (Nov 4, 12:41)
- Chain run: build OK -> sweep OK -> gate test_std PASS -> suite
  **50 passed, 0 failed (of 50)** -> PROMOTED `nizam-new-fixed7` ->
  `nizam-new` (suite resumed from the durable journal
  `rt_nolink.state` after a server restart killed the first run mid-suite;
  10 journaled PASSes skipped, 40 run fresh).
- Acceptance PoCs against the PROMOTED binary:
  - `set_min.nz` — minimal `Set[i32]` with NO `Dict` import (scope-fix
    acceptance): has2=1, cnt=3, rc=0.
  - `set_i32.nz` — the original segfault repro: has42=1, has99=0, cnt=2,
    remove works, rc=0. Products: 0 runtime refs, 0 undefined mantiq
    symbols (still fully self-contained).
- IR sweep: `%Set_i32 = type` emitted alongside 25 specialised
  `@Set_i32_*` defines; `@Set_i32_add` takes a real `i32` parameter.

### Documented limitations (accepted, next-session candidates)
- Dead erased copies still emitted: the erased `@Set_add`-family defs and
  `%Set` type remain in products (16 erased-call refs in the set_i32 IR);
  matches the Wrap behaviour. Cleanup candidate.
- Diagnostics mis-map for generated snippets: mono re-lowering uses the
  main file's path, so spans/errors from generated bodies point at the
  main file with snippet-relative positions.
- `check_source` (main.nz:1063) intentionally never runs mono — it is a
  typecheck-only path.
- Sub-pointer-width element subscripts (`Tuple[i32]`-style) still use the
  erased ptr stride — pre-existing, unrelated to mono.
- `Dict.has` still has no zeroed-dict guard (pre-existing gotcha).

### Milestone M follow-up: dead-code sweep in the clang shim (Nov 4, 20:35)

Real monomorphisation left every product carrying dead weight: the erased
template copies (`@Set_add` beside `@Set_i32_add`) plus all unused std
surface. Reachability analysis of the set_i32 IR showed the erased copies
form a closed subgraph — only dead defs call dead defs; `main` reaches
only mono'd defs.

- Implementation: `sweep_dead_erased()` in `tools/clangshim/filter.py`
  (also live in `~/.local/share/nizam-tools/clangshim/filter.py`). Parses
  define blocks, BFS reachability from roots (`main` + every `@name`
  referenced outside define bodies), drops unreachable defines.
  Guards: skipped entirely when the module has no `@main` (library-style
  outputs — py-ext/wasm — keep everything); no dlopen/dlsym use anywhere
  in the toolchain's products, so full DCE on executables is sound.
- Bring-up bugs caught offline: an index-vs-name set check (silent
  no-op), and a false-sibling match (`Set_i32_intersection_update`
  looked like a mono'd sibling of `Set_i32_update` while a dead-but-kept
  caller still referenced it) — which proved the sweep must be FULL DCE,
  not sibling-guarded: dead mono'd defs call each other too.
- Fake-validation trap: the first suite rerun after the change finished
  in 3 s — the product cache served binaries without invoking clang, so
  the filter never executed. Cleared `.mantiq_cache` and reran.
- Validation (real builds through the shim): offline — set_i32 IR 341→24
  defines (89% smaller IR), identical output rc=0; test_set_methods
  358→54; test_tuple_methods 344→25, all pass. Systemic — full 50-test
  suite with cache cleared: **50 passed, 0 failed (of 50)**, promoted.
- Product size: set_i32 binary 121,896 → 21,520 bytes (**82% smaller**);
  suite products now ~120–160 KB.

Caveat: the sweep lives in the shim (build-time tooling), not the
compiler — the next compiler self-build also passes through it. Porting
the sweep into codegen.nz's final assembly remains open, as does the
rest of the limitation list (generated-snippet span mapping,
sub-ptr-width subscripts).

## Milestone N — full self-hosting (Nov 5, 00:42)

The self-hosted compiler now builds itself, end to end, validated across
generations:

- **nizam-new** (gen-1, built by the old 27-min builder) compiles
  `src/main.nz` -> **nizam-self** in **~2.5 min** (rc=0).
- **nizam-self** compiles the same source -> **nizam-self2**: nm sweep OK,
  test_std gate PASS, **50-test suite 50 passed, 0 failed (of 50)**,
  promoted to `nizam-self-promoted`.
- **Fixed point**: nizam-self2 -> **nizam-self3** rc=0 in 3m14s
  (user CPU only 42s). nizam-self2: 0 undefined mantiq symbols, 0 ldd
  runtime refs — fully self-contained.
- **Promoted nizam-self2 -> nizam-new** (previous saved as
  `nizam-new-preSelfHost.bak`). `chain_stable.sh` is the going-forward
  chain: builder = `nizam-self-promoted`, output -> nizam-new-fixed7 ->
  gate -> suite -> promote to nizam-new; ~5-8x faster end-to-end than the
  old-builder chain.

### What blocked self-hosting, and the fixes
1. **Borrowck memory explosion (`80b3a03`)**: `symbol_states` accumulated
   every variable declared anywhere in the program (pop_scope only marked
   entries Dropped), while `snapshot_symbol_states` copied the whole map
   3x per IfStmt and snapshots were never freed — O(symbols x if-stmts)
   allocation. Compiling the compiler's own source: 280MB -> 1.1GB in 40s,
   SIGKILL. Fix: pop_scope removes the popped scope's entries; the map
   stays function-scoped. Peak during the self-host build: **380MB**.
   (Diagnosed via gdb SIGINT backtrace: the ramp sampled inside
   BorrowChecker_snapshot_symbol_states <- walk_ast.)
2. **tree_sitter/api.h missing in the bootstrap env** — the bootstrap
   script lacked the CPATH export the chain script has.
3. **Undefined compiler_lib_dir/set_compiler_lib_dir at ld (`e24abd2`)**:
   the compiler TU declares them extern; runtime.c defines them, but
   native product link lines dropped runtime.c in Milestone D. The old
   builder's baked link line masked the gap until a self-hosted build
   exposed it. Fix: weak-marked in runtime.c (same pattern as
   mantiq_intern_string), strong TU-side defs copied verbatim into
   tree_sitter_helper.c (on every native product link line); the shim DCE
   sweep drops them from products that never reference them.

### State of the toolchain after Milestone N
- Canonical compiler `nizam-new`: gen-3 lineage (self-hosted since gen-2),
  1.23 MB, self-contained, DCE'd.
- Old builder `nizam-new-next` retained only as a bootstrap fallback.
- Future compiler-source change cycles: edit -> chain_stable.sh -> ~3 min
  build + ~15 min suite, promotion at 50/50.
