# Specification 0028: Python to Nizam Ahead-of-Time (AOT) Transpiler

## 1. Syntax Mapping & Desugaring Rules

### 1.1 Type Annotation Lowering
Python PEP 484 and PEP 526 type annotations map directly into Nizam static types:
- `int` -> `i64`
- `float` -> `f64`
- `bool` -> `bool`
- `str` -> `String`
- `bytes` -> `Bytes` / `List[u8]`
- `list[T]` -> `List[T]`
- `tuple` -> `Tuple[T]`
- `dict[K, V]` -> `Dict[K, V]`
- `set[T]` -> `Set[T]`
- `frozenset[T]` -> `FrozenSet[T]`
- `Optional[T]` / `T | None` -> `Option[T]`
- `Any` / Unannotated -> `PyObject`

### 1.2 Control Flow & Comprehension Lowering
- Conditionals (`if`, `elif`, `else`), loops (`while`, `for`), and pattern matching (`match`, `case`) translate directly into canonical Nizam syntax.
- List and dictionary comprehensions are desugared into imperative pre-allocated loops:
  ```nizam
  var out: List[T] = List[T]()
  for item in source:
      if condition:
          out.append(expr)
  ```
- f-strings are lowered to chained `+` operations with `.to_string()` conversion on numeric and primitive values.

---

## 2. Object Model & Class Lowering

### 2.1 Classes to Unboxed Structs
Python classes are transformed into Nizam `struct` declarations:
1. Class variable annotations and `self.<field>` assignments in `__init__` synthesize struct fields.
2. The `__init__` constructor becomes a static factory function (`public fn init(...) as Self`).
3. Methods are declared with explicit pointer receivers (`self as ptr[T]`).
4. Attribute reads and mutations on `self` are lowered to dereferenced pointer syntax `(deref self).field`.
5. Direct instantiations `MyClass(...)` are lowered to factory calls `MyClass.init(...)`.

### 2.2 Declarative UI Component Lifecycle (PyThra)
- `StatelessWidget` and `StatefulWidget` are lowered to immutable configuration structs.
- `State[W]` classes are lowered to heap-allocated mutable state structs.
- Calls to `self.set_state(lambda: ...)` inline the field mutation and invoke `/* nizam_ui_mark_dirty(self) */` on the element reference.

---

## 3. High-Performance Virtual DOM Reconciler

1. **Node Structures**:
   - `RenderedNode`: Unboxed struct containing `html_id`, `widget_type`, `key`, `props` (`Dict[String, String]`), `children_keys` (`List[String]`), `parent_html_id`, `parent_key`.
   - `Patch`: Struct containing `action` (`INSERT`, `REMOVE`, `REPLACE`, `UPDATE`, `MOVE`), `html_id`, and `payload`.
2. **Reconciliation Invariants**:
   - Diffing generates a flat list of `Patch` operations.
   - Keyed children undergo $O(N)$ index-mapped diffing to avoid quadratic tree-walk overhead during reorder operations.
   - Reconciler diffing functions are decorated with `@nogil` to permit parallel background execution across multi-threaded workers.

---

## 4. Multi-Target Compilation Drivers

The transpiler driver (`mantiq/python/nizam/transpiler/builder.py`) drives the self-hosted Nizam compiler across three targets:
1. `--target native`: Compiles transpiled Nizam modules into standalone native binaries linked against OS webview shells (`native_webview.c`).
2. `--target wasm32-wasi`: Compiles transpiled Nizam code to WebAssembly modules accompanied by a zero-dependency JS/HTML loader stub (`wasm_loader.py`).
3. `--target python-ext`: Compiles hotspot modules into PEP 384 Limited API (`abi3`) C-extension shared libraries.
