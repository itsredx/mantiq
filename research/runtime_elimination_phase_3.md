# Phase 3: Pure-Nizam Generic Collections (`std.collections`)

This phase eliminates the type-erased C collection shims (`__mantiq_list_*` and `__mantiq_dict_*`) from [runtime.c](file:///home/red-x/projects/desktop/mantiq_nizam/mantiq/runtime.c). It promotes the pure-Nizam implementations of `List[T]` and `Dict[K, V]` in [std/collections.nz](file:///home/red-x/projects/desktop/mantiq_nizam/mantiq/std/collections.nz) to primary first-class containers, enables monomorphization and method inlining in the LLVM backend, and integrates container lifecycles with the compiler's drop elaboration engine.

---

## 1. Objectives

- Implement high-performance, generic `List[T]` and `Dict[K, V]` entirely in pure Nizam without calling `runtime.c`.
- Enable full monomorphization in `typecheck.nz` and `codegen.nz`, generating specialized machine code for each type instantiation (`List[i32]`, `List[String]`).
- Enable deep inlining of hot collection operations (`append`, `get`, `length`, `contains`) by LLVM.
- Implement automatic element destruction: when a collection is dropped, each contained element is destroyed according to its affine drop rules before the backing storage is freed.
- Deprecate and remove all `__mantiq_list_*` and `__mantiq_dict_*` helper functions from `runtime.c`.

---

## 2. Problem Formulation

Currently, collection operations in Nizam generate calls to external C functions in `runtime.c`:

```llvm
; Current Codegen: Appending an element to a List
call ptr @__mantiq_list_append(ptr %list, ptr %elem, i64 8)

; Current Codegen: Looking up a key in a Dict
%val = call ptr @__mantiq_dict_get(ptr %dict, ptr %key, i32 8)
```

Inside [mantiq/runtime.c](file:///home/red-x/projects/desktop/mantiq_nizam/mantiq/runtime.c#L1265-L1320), collections are implemented with raw `void*` pointer arithmetic:

```c
void __mantiq_list_append(void* list_addr, void* elem_addr, int64_t elem_size) {
    struct List { void* data; size_t len; size_t cap; }* l = (struct List*)list_addr;
    if (l->len >= l->cap) {
        size_t new_cap = l->cap == 0 ? 8 : l->cap * 2;
        l->data = mantiq_realloc(l->data, (int64_t)(new_cap * elem_size));
        l->cap = new_cap;
    }
    memcpy((char*)l->data + l->len * elem_size, elem_addr, (size_t)elem_size);
    l->len++;
}
```

### Critical Flaws of the C Runtime Implementation:
1. **Optimization Barrier**: Because `__mantiq_list_append` is an external C symbol, LLVM cannot inline the fast path (`len < cap`). Every single item append forces a function call, saving/restoring caller-saved registers, spilling memory, and destroying loop vectorization.
2. **Element Drop Leaks**: The C runtime has no concept of Nizam types. When `__mantiq_list_pop` or `__mantiq_list_remove` is called on a `List[String]` or `List[CustomStruct]`, the element's inner heap allocations are **never dropped**, leading to silent memory leaks.
3. **Dataflow & Borrow Blindness**: Nizam's Polonius borrow checker cannot track whether references to elements in a `List[T]` are invalidated when `__mantiq_list_append` reallocates the backing buffer.

---

## 3. Key Tasks & Current Status

### [ ] Task 3.1: Monomorphized `List[T]` in Pure Nizam (`std/collections.nz`) — **Status: Not Done**
`std/collections.nz:13` declares `struct List[T]`, but its operations lower to C. `codegen.nz` has 59 `__nizam_list_*` calls and those functions live in `runtime.c` (`__nizam_list_concat`, `_contains`, `_copy`, `_count`, `_equals`, `_decode`, ...). It remains a Nizam-declared generic with a C implementation — renamed and wrapped, but not eliminated.

```nizam
# ── Generic Monomorphized List ───────────────────────────────────────
struct List[T]:
    public var data as ptr[T]
    public var length as i64
    public var capacity as i64
    public var allocator as ptr[Allocator]

    public fn init(allocator as ptr[Allocator] = None) as List[T]:
        return List[T](
            data = None to ptr[T],
            length = 0 to i64,
            capacity = 0 to i64,
            allocator = if allocator != None to ptr[Allocator]: allocator else: get_default_allocator()
        )

    public fn append(self as ptr[List[T]], item as T):
        if (deref self).length >= (deref self).capacity:
            self.grow_capacity()
        let slot as ptr[T] = (deref self).data + (deref self).length
        (deref slot) = item
        (deref self).length = (deref self).length + 1 to i64

    private fn grow_capacity(self as ptr[List[T]]):
        let new_cap as i64 = if (deref self).capacity == 0 to i64: 8 to i64 else: (deref self).capacity * 2 to i64
        let item_sz as usize = sizeof[T]()
        let new_data as ptr[T] = ((deref self).allocator).resize(
            (deref self).data to ptr[u8],
            ((deref self).capacity to usize) * item_sz,
            (new_cap to usize) * item_sz
        ) to ptr[T]
        (deref self).data = new_data
        (deref self).capacity = new_cap
```

### [ ] Task 3.2: High-Performance Hash Map `Dict[K, V]` in Pure Nizam (`std/collections.nz`) — **Status: Not Done**
`struct Dict[K,V]` (line 44) and `struct DictBucket[K,V]` (line 38) exist in `std/collections.nz`, but lowering still calls `__mantiq_dict_*` (49 call sites in `codegen.nz`, routing into `runtime.c`). Dict is the furthest behind and carries the Bug C hash/capacity defect (`runtime.c:1093`).

```nizam
# ── Open-Addressing Dict ─────────────────────────────────────────────
struct DictBucket[K, V]:
    public var key as K
    public var val as V
    public var hash as u32
    public var state as u8 // 0: Empty, 1: Occupied, 2: Tombstone

struct Dict[K, V]:
    public var buckets as ptr[DictBucket[K, V]]
    public var count as i64
    public var capacity as i64
    public var allocator as ptr[Allocator]
    ...
```

### [ ] Task 3.3: Container Drop Elaboration (`src/borrowck.nz`, `src/codegen.nz`) — **Status: Partial**
`__nizam_drop_` shims exist in `runtime.c` (5 refs), but drop implementation remains C-side. `std/collections.nz` still calls `mantiq_malloc` directly (~lines 752, 766, 1516, 1530).

```llvm
; Synthesized Destructor for List[String]
define void @__nizam_drop_List_String(ptr %list) {
entry:
  %len = load i64, ptr %list_len_ptr
  ; Loop over elements and call @__nizam_drop_String
  ...
  ; Finally free backing array
  call void @std_mem_free(ptr %data, i64 %cap_bytes)
  ret void
}
```

### [ ] Task 3.4: Codegen Monomorphization Integration (`src/codegen.nz`) — **Status: Not Done (Primary Blocker)**
`TypeChecker.monomorphize` (`typecheck.nz:980`) and `clone_and_substitute` (`:909`) exist but have zero callers. Codegen has no monomorphization integration. This is the P1 blocker gating all Phase 3 tasks. It requires:
1. Recursion into `TypeAnnotation.generics`.
2. Handling `else_branch` nodes.
3. Multi-type-parameter support (`Dict[K, V]`).
4. Mangling alignment (currently mangles as `add_i64` where codegen expects `Set_add`).

### [ ] Task 3.5: Deprecate C Collections in `runtime.c` — **Status: Partial**
The legacy `__mantiq_list_*` family is fully purged (0 refs). However, `__nizam_list_*` (renamed C runtime functions) plus `__mantiq_dict_*` remain — totaling roughly 108 C collection call sites in `codegen.nz`.

---

## 3.6 Current Frontier & Root Cause Analysis

### Practical Architectural Blocker
Across all Phase 3 collection work, `emit_struct_methods` in `codegen.nz` blacklists `List`, `Dict`, `DictBucket`, `Set`, `FrozenSet`, `Tuple*`, and `DictItems`, preventing any of those methods from being emitted into LLVM IR. Consequently:
- `test_std.nz` fails on undefined `@Set_add`.
- `test_set_methods.nz` fails on `@FrozenSet_from_set`.
- `test_dict_methods.nz` fails on `@DictItems_to_list`.

Task 3.4 (Monomorphization Integration) gates all downstream generic collection capabilities.

### Working Tree Compilation Status
The working tree currently has an uncommitted diff in `codegen.nz` containing a tree-sitter syntax parse error at `emit_call_expr` (line ~5206) and a preceding `TypeMismatch`. `HEAD` builds cleanly.

### Unexpected File & Directory Creation Defect
When running `./nizam build` from `mantiq/`, temporary `String` instances in `src/main.nz` (`cache_dir`, `bin_dir`, `dep_file_path`, `out_file`) had their backing memory prematurely dropped by dynamic stack drop flags/ABI return handling. As a result:
- `mantiq_mkdir_p(cache_dir)` created empty directories named with raw heap pointer addresses (`./C\udcca\x03`, `./\udcea\x1fc+`, etc.).
- `fopen(dep_file_path.data, "wb")` and `mantiq_copy_file` created `.dep` files and cached binaries with garbage pointer names directly in the working directory.
- `zig cc ... -o <out_file>` received dangling string pointers, creating `-L.` and `-Wl,-rpath,.` binary artifacts.
Resolving `String` drop semantics in `main.nz` prevents these artifacts from appearing.

---

## 4. Deliverables & Verification

- **Deliverable 1**: Complete pure-Nizam implementations of `List[T]` and `Dict[K, V]` in [mantiq/std/collections.nz](file:///home/red-x/projects/desktop/mantiq_nizam/mantiq/std/collections.nz).
- **Deliverable 2**: Compiler updates in `src/typecheck.nz` and `src/codegen.nz` emitting monomorphized container code.
- **Deliverable 3**: Verification test suite `mantiq/src/tests/test_pure_collections.nz` testing:
  - `List[i32]` append, pop, sort, reverse, extend.
  - `List[String]` verifying that removing or clearing items drops each inner `String` without memory leaks.
  - `Dict[String, i64]` insertions, re-hashing across growth boundaries, collisions, and deletions.
- **Verification Command**:
  ```bash
  ./mantiq/nizam build src/tests/test_pure_collections.nz -o /tmp/test_collections && /tmp/test_collections
  ```

---

## 5. Success Criteria

1. `objdump -t <binary> | grep __mantiq_list` returns **0 matches**.
2. Benchmark showing that appending 10,000,000 integers to `List[i32]` in pure Nizam is at least **2.5x faster** than calling the C runtime through the opaque FFI boundary.
3. Valgrind reports 0 bytes in 0 blocks leaked for nested containers (e.g., `List[List[String]]`).
