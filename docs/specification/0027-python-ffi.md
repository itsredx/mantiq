# Specification 0027: Bidirectional Python Foreign Function Interface (FFI)

## 1. Syntax & Grammar Additions

### 1.1 Tagged Module Import (`import[python]`)
```nizam
import[python] <module_path> [as <alias>]
from[python] <module_path> import <symbol> [as <alias>]
```
- Tagged imports instruct the CST lower pass (`src/lower.nz`) to categorize the imported module as a dynamic foreign Python dependency.
- Imported objects evaluate to the built-in affine type `PyObject`.

### 1.2 Static Typed Extern Block (`extern[python]`)
```nizam
// Block declaration:
extern[python] "<module_name>":
    fn <function_name>(<param_name> as <type>, ...) as <return_type>

// Inline declaration:
extern[python] "<module_name>" fn <function_name>(<param_name> as <type>, ...) as <return_type>
```
- Parameters and return types must be valid Nizam primitive types (`i8`..`i64`, `u8`..`u64`, `f32`, `f64`, `bool`, `cstr`, `String`, `ptr[T]`).
- Function symbols are resolved lazily at runtime and cached statically in LLVM global slots (`@__nizam_py_cached_*`).

### 1.3 Static GIL Safety Decorator (`@nogil`)
```nizam
@nogil
fn <function_name>(<params>) as <return_type>:
    <body>
```
- Can be applied to function declarations and definitions.
- Enforces compile-time isolation from CPython runtime APIs.

---

## 2. Compilation Target: `--target python-ext`

When the compiler is invoked with `--target python-ext`:
1. **Target Triple & Output Layout**: Target triple is set to host architecture with dynamic relocation (`-fPIC`). Output binary conforms to PEP 384 Limited API naming (`<name>.abi3.so`).
2. **LLVM Module Metadata**:
   - Generates `%PyMethodDef` table exporting all public module-level functions.
   - Generates `%PyModuleDef` describing module name and methods.
   - Generates exported C symbol `@PyInit_<modulename>()` invoking `PyModule_Create2(ptr @module_def, i32 1013)`.
3. **No Local Python Header Requirement**: Emits opaque type declarations and external calls directly against `libpython3.so` symbols.

---

## 3. Object Model & Memory Lifecycle

### 3.1 Affine Type Semantics (`PyObject`)
- `PyObject` is a non-copyable affine struct containing `{ ptr raw_ptr, i1 is_borrowed }`.
- Assignment transfers ownership; use-after-move is rejected by `src/borrowck.nz` (`[E0401]`).
- Lexical exit of an owned `PyObject` automatically injects `call void @mantiq_py_decref(ptr %raw_ptr)`.
- Explicit cloning via `obj.clone()` emits `call void @mantiq_py_incref(ptr %raw_ptr)` and returns an owned handle.

### 3.2 Opaque Type Synthesis (`PyType_FromSpec`)
Structs and classes marked for export generate a `PyType_Spec` descriptor:
- `tp_new`: Allocates object wrapper containing opaque pointer payload `void* nizam_ptr`.
- `tp_init`: Unpacks constructor parameters and calls native struct `.init()`.
- `tp_dealloc`: Runs native auto-drops on `nizam_ptr` and frees heap memory before calling `PyObject_Free`.
- `tp_methods`: Maps member methods to instance calls with bound `self`.
- `tp_getset`: Maps struct fields to property getter/setter trampolines.

---

## 4. PEP 3118 Shared-Ownership Buffer Protocol

1. **Heap Promotion**: Any native linear collection (`List[T]`, `Bytes`, raw memory buffers) exposed to Python via PEP 3118 promotes its metadata to a `MantiqBufferOwner` control block with initial `ref_count = 2`.
2. **Buffer Descriptor (`Py_buffer`)**: Populated with raw buffer pointer, byte length, itemsize, format character, dimension count, shape, and strides.
3. **Deallocation Invariant**: Memory is freed if and only if both Nizam and CPython release their respective reference counts.

---

## 5. Transitive Static GIL Safety Analysis

A function marked `@nogil` is verified by the semantic analyzer (`src/sema.nz`):
1. **Parameter & Return Constraints**: Signature must contain zero instances of `PyObject`.
2. **Call Graph Invariant**: Transitively reachable call graph must contain zero invocations of CPython C-API functions, Python callbacks, or managed object allocations.
3. **Runtime Release**: The code generator wraps verified native calls in `Py_BEGIN_ALLOW_THREADS` and `Py_END_ALLOW_THREADS`.
