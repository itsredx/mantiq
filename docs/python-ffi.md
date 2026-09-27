# Bidirectional Python Foreign Function Interface (FFI)

## 1. Overview & Architectural Motivation

Python is the dominant language for data science, artificial intelligence, and high-level workflow orchestration, while Nizam and Mantiq provide a compiled systems language with static typing, affine memory ownership, deterministic auto-drops, LLVM intermediate representation emission, and native concurrency.

The **Bidirectional Python FFI Subsystem** provides a zero-overhead, memory-safe bridge connecting Nizam and CPython across two complementary directions:
1. **Exporting Nizam to Python (`--target python-ext`)**: Compiling Nizam modules directly into native CPython extension shared libraries (`.abi3.so`) compliant with the **PEP 384 Limited API / Stable ABI (`abi3`)**.
2. **Embedding Python in Nizam (`import[python]` & `extern[python]`)**: Loading the CPython runtime inside native Nizam binaries, enabling both dynamic scripting (`import[python]`) and compile-time checked, zero-overhead static declarations (`extern[python]`).

```
┌───────────────────────────────────────────────────────────────────────────────┐
│                    Nizam <-> Python Bidirectional FFI Model                   │
├───────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  [ Export Pipeline: Nizam -> Python ]                                         │
│   • Target Flag: --target python-ext                                          │
│   • PEP 384 Limited API (abi3) shared library generation (.abi3.so)           │
│   • Vectorcall function trampolines with zero Python.h header dependency      │
│   • Opaque %PyTypeObject synthesis (PyType_FromSpec) for structs and classes  │
│   • PEP 3118 Buffer Protocol with Shared-Ownership Heap Promotion             │
│   • Transitive compile-time @nogil analysis & GIL release                     │
│   • In-process PEP 517 build backend (nizam_build)                            │
│                                                                               │
│  [ Import Pipeline: Python -> Nizam ]                                         │
│   • Dynamic Tagged Imports: import[python] numpy as np                        │
│   • Static Typed Declarations: extern[python] "math": ...                     │
│   • Move-semantics affine PyObject handles with compiler-injected auto_drops  │
│   • Lazy static callable pointer caching (@__nizam_py_cached_*)               │
│   • Weak runtime C-API linkage in runtime.c                                   │
│                                                                               │
└───────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Memory Model & Handle Lifecycle: `PyObject` + Affine Ownership

### 2.1 The Fundamental Ownership Invariant
> **Compiler Invariant 1 (Visible Lifetime Enforcement):**  
> *The Nizam compiler statically manages the ownership, moves, and lifetimes of Python object handles within the scope visible to the Nizam program. It guarantees that Nizam will not execute use-after-move, use-after-free, or double-free operations on handles it owns.*

### 2.2 `PyObject` Handle Representation
In Nizam, foreign Python objects are represented by a built-in composite handle:
```nizam
struct PyObject:
    var raw_ptr as ptr[u8]      // Pointer to CPython PyObject
    var is_borrowed as bool     // True if handle is a borrowed reference
```

`PyObject` is registered in `src/types.nz` as a **Move-Semantics Affine Type** (non-copyable):
1. **Move Semantics:** Assigning an owned `PyObject` (`let b = a`) transfers ownership. Variable `a` transitions to the `Moved` state in `src/borrowck.nz`; subsequent access to `a` triggers compiler error `[E0401]: Use of moved variable`.
2. **Auto-Drop Injection:** When an owned `PyObject` leaves its lexical scope without being moved, the borrow checker injects an automatic destructor at block exit:
   ```llvm
   call void @mantiq_py_decref(ptr %py_handle)
   ```
3. **Borrowed References (`ref obj`):** Passes `obj.raw_ptr` without modifying reference counts and without scheduling an auto-drop.
4. **Explicit Cloning (`obj.clone()`):** Invokes `Py_XINCREF` and produces a new, independently owned `PyObject`.

---

## 3. Export Pipeline: Compiling Nizam to Python Extensions (`--target python-ext`)

### 3.1 PEP 384 Limited API (`abi3`) Generation
Compiling a Nizam module with:
```bash
nizam build my_kernel.nz --target python-ext -o dist/my_kernel.abi3.so
```
produces a self-contained shared library targeting the Python 3.8+ Stable ABI (`#define Py_LIMITED_API 0x03080000`).

#### Zero `Python.h` Header Dependency
The code generator (`src/codegen.nz`) emits LLVM type declarations for CPython C-API structures directly:
- `%PyMethodDef = type { ptr, ptr, i32, ptr }`
- `%PyModuleDef_Base = type { i64, ptr, i64, ptr }`
- `%PyModuleDef = type { %PyModuleDef_Base, ptr, ptr, i64, ptr, ptr, ptr, ptr, ptr }`

External functions are declared against `libpython3.so` symbols (`PyModule_Create2`, `PyArg_ParseTuple`, `PyLong_FromLongLong`, `PyFloat_FromDouble`, `PyUnicode_FromString`, etc.), eliminating local CPython development header requirements.

### 3.2 Vectorcall Function Trampoline Generation
For every public module-level function, the compiler generates a companion Vectorcall trampoline:
1. Unpacks arguments from Python `args` tuple using `PyArg_ParseTupleAndKeywords`.
2. Validates types and coerces values into native Nizam unboxed representations.
3. Invokes the native function with register-level ABI calling conventions.
4. Boxes the return value into a Python object (`Py_None` for void).
5. Registers the trampoline in `@my_kernel_methods` (`PyMethodDef` table) with `METH_VARARGS | METH_KEYWORDS`.

### 3.3 Struct & Class Export via `PyType_FromSpec`
Nizam structs and classes are exported as native Python types using `PyType_FromSpec` to isolate internal object header layouts across Python minor versions:
- `tp_new`: Allocates object wrapper containing opaque pointer payload `void* nizam_ptr`.
- `tp_init`: Unpacks constructor parameters and instantiates the native struct via `.init()`.
- `tp_dealloc`: Runs native borrow-checker auto-drops and frees associated heap buffers before calling `PyObject_Free`.
- `tp_methods`: Exposes member methods with bound `self` receivers.
- `tp_getset`: Exposes struct fields with direct getter and setter trampolines.

---

## 4. Shared-Ownership PEP 3118 Buffer Protocol

### 4.1 The "Zero-Copy Lifetime Trap"
When exposing native arrays (`List[f64]`, `Bytes`, raw buffers) to Python as a `memoryview` or NumPy `ndarray`, Python code can retain references in global data structures:
```python
global_views = []
def save(view):
    global_views.append(view) # View escapes function call!
```
If Nizam freed the backing buffer upon lexical scope exit, Python's view would point to deallocated memory, causing segmentation faults.

### 4.2 Shared-Ownership Heap Promotion (`MantiqBufferOwner`)
Nizam eliminates this vulnerability through shared-ownership heap promotion:
```
                      MantiqBufferOwner
                     ┌─────────────────┐
                     │ ref_count: i32  │
                     │ data_ptr: ptr   │
                     │ capacity: usize │
                     │ element_sz: u32 │
                     └────────┬────────┘
                              │
             ┌────────────────┴────────────────┐
             ▼                                 ▼
      Nizam Program                     Python Runtime
     ┌──────────────┐                 ┌─────────────────┐
     │  List[f64]   │                 │   Py_buffer     │
     │ (Holds ref)  │                 │  obj: PyCapsule │
     └──────────────┘                 │ (Holds ref)     │
                                      └─────────────────┘
```
1. When shared with Python via PEP 3118, the allocation metadata is promoted to a heap-allocated `MantiqBufferOwner` with `ref_count = 2`.
2. Nizam populates a `Py_buffer` descriptor (`buf`, `len`, `itemsize`, `format`, `shape`, `strides`) and assigns a `PyCapsule` adapter to `Py_buffer.obj`.
3. In `bf_releasebuffer` and the capsule destructor, Python decrements the owner reference count.
4. When Nizam drops the `List[T]`, it decrements the owner reference count.
5. Backing memory is deallocated **only when both runtimes release their references**.

---

## 5. Transitive Static GIL Safety Engine & `@nogil`

### 5.1 Theorem 1 (Transitive GIL Independence)
A native Nizam function $F$ can safely execute without holding CPython's Global Interpreter Lock if and only if:
1. No parameter in the signature of $F$ is of type `PyObject` or transitively contains a `PyObject`.
2. The return type of $F$ is not of type `PyObject` and does not transitively contain a `PyObject`.
3. The call graph $G(F)$ reachable from $F$ contains zero calls to CPython C-API functions, zero invocations of Python callbacks, and zero interactions with Python-managed heap references.

### 5.2 Compile-Time Enforcement & Runtime GIL Release
```nizam
@nogil
public fn compute_heavy(data as ptr[f64], n as i64) as f64:
    // Pure native loops, SIMD operations, and heap math
```
- If a function marked `@nogil` attempts to call a Python API or access `PyObject`, the compiler emits `[E0450]: Function marked @nogil violates transitive GIL independence`.
- For verified `@nogil` functions, the C-extension trampoline emits `Py_BEGIN_ALLOW_THREADS` before the native call and `Py_END_ALLOW_THREADS` on return, releasing the GIL to achieve true multi-core scaling in Python `ThreadPoolExecutor` workloads.

---

## 6. Import Pipeline: Embedding Python in Nizam

Nizam provides two integration tiers when calling Python from Nizam:

### 6.1 Tier 1: Dynamic Tagged Imports (`import[python]`)
```nizam
import[python] numpy as np
import[python] json

fn run_analysis():
    let arr = np.zeros([100, 100])
    let out = json.dumps(arr.shape)
```
- Symbols are resolved dynamically via weak C-API linkage in `runtime.c`.
- Automatically calls `Py_Initialize` on first access.
- Operates on generic `PyObject` handles with dynamic attribute lookup.

### 6.2 Tier 2: Static Typed Declarations (`extern[python]`)
For performance-critical code requiring compile-time type verification:
```nizam
// Block syntax
extern[python] "math":
    fn sqrt(x as f64) as f64
    fn pow(base as f64, exp as f64) as f64

// Inline syntax
extern[python] "builtins" fn abs(x as i64) as i64
```

#### Zero-Overhead Lazy Callable Caching
To eliminate the ~120ns cost of `PyObject_GetAttrString` on every call, the code generator (`src/codegen.nz`) emits a lazy static callable cache:
```llvm
@__nizam_py_cached_sqrt_0 = internal global ptr null
```
On first invocation:
1. Resolves module and callable via `PyImport_ImportModule` and `PyObject_GetAttrString`.
2. Stores the callable pointer in `@__nizam_py_cached_sqrt_0`.
3. Dispatches directly via Vectorcall (`PyObject_CallObject`), reducing dispatch overhead to ~25ns.

---

## 7. Packaging & Concurrency Hardening

### 7.1 In-Process Import Hook (`import nizam`)
Allows transparent imports of `.nz` files directly in Python:
```python
import nizam
nizam.install()

import fast_matrix # Compiles and loads fast_matrix.nz
```

### 7.2 Atomic Lockfile Protocol
In multi-worker environments (`gunicorn -w 8`, `torchrun`, `multiprocessing`), concurrent imports cannot race on binary writes:
1. **Advisory Locking:** Worker acquires exclusive lock via `fcntl.flock(fd, LOCK_EX)` on `.cache/<mod>.lock`.
2. **PID Isolation:** Compiler outputs to `.cache/<mod>.<hash>.tmp.<pid>.so`.
3. **Atomic Commit:** Uses `os.replace` to atomically commit the finished shared library.
4. **Fast Path:** Subsequent workers acquire the lock, detect matching SHA-256 hash, and load the cached binary immediately.

### 7.3 PEP 517 Build Backend (`nizam_build`)
Located at `mantiq/python/nizam_build/`, enables building standard wheels and direct `pip` installation:
```toml
[build-system]
requires = ["setuptools"]
build-backend = "nizam_build.core"

[tool.nizam]
module-name = "my_accel"
sources = ["src/accel.nz"]
```

---

## 8. Verification & Test Suites

The FFI subsystem is verified across dedicated automated test runners in `mantiq/src/tests/python/`:
```bash
cd mantiq/src/tests/python
./run_phase_1_tests.sh      # Primitives, Vectorcall, and return marshaling
./run_phase_2_tests.sh      # PyType_FromSpec, struct fields, and methods
./run_phase_3_tests.sh      # Buffer protocol and zero-copy NumPy sharing
./run_phase_4_tests.sh      # Static GIL release and ThreadPoolExecutor scaling
./run_phase_5_tests.sh      # Dynamic import[python] embedded execution
./run_phase_6_tests.sh      # In-process loader and PEP 517 wheel build
./run_extern_python_tests.sh # Static typed extern[python] lazy callable caching
```
