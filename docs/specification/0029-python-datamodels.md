# Specification 0029: Python 3.8+ Data Model Parity across Standard Collections

## 1. Overview & Scope

This specification establishes strict method name, parameter signature, and behavioral equivalence between Python 3.8+ built-in data types and Mantiq standard library modules (`std.string`, `std.collections`, and native runtime primitives).

---

## 2. Core Collection Specifications

### 2.1 String (`std.string.String`)
- Conforms to Python `str` semantics.
- Provides 47 standard methods:
  - Casing: `capitalize`, `casefold`, `lower`, `upper`, `swapcase`, `title`
  - Alignment & Padding: `center`, `ljust`, `rjust`, `zfill`
  - Searching & Counting: `find`, `rfind`, `index`, `rindex`, `count`, `startswith`, `endswith`
  - Inspection: `isalnum`, `isalpha`, `isascii`, `isdecimal`, `isdigit`, `isidentifier`, `islower`, `isnumeric`, `isprintable`, `isspace`, `istitle`, `isupper`
  - Manipulation & Splitting: `join`, `lstrip`, `rstrip`, `strip`, `partition`, `rpartition`, `split`, `rsplit`, `splitlines`, `replace`, `removeprefix`, `removesuffix`, `expandtabs`
  - Formatting & Mapping: `format`, `format_map`, `maketrans`, `translate`, `encode`
- Dunder operators: `__len__`, `__contains__`, `__eq__`, `__ne__`, `__add__`, `__mul__`, `__getitem__`.

### 2.2 List (`std.collections.List[T]`)
- Resizable array backed by contiguous heap memory.
- Standard methods: `append`, `extend`, `clear`, `count`, `index`, `insert`, `remove`, `reverse`, `copy`, `pop`, `sort`.
- Sorting provides numeric ordering for integers/floats and lexicographic ordering for `String` elements.

### 2.3 Tuple (`std.collections.Tuple[T]`)
- Immutable sequence type.
- Standard methods: `count`, `index`, `length`, `get`, `__getitem__`.

### 2.4 Dictionary (`std.collections.Dict[K, V]`)
- Open-addressing hash map with power-of-two bitmask probing and automatic resize.
- Standard methods: `clear`, `copy`, `fromkeys`, `get`, `items`, `keys`, `pop`, `popitem`, `setdefault`, `update`, `values`.
- Supports dictionary view abstractions (`DictItems`) with Python 3.10+ `.mapping()` property access.

### 2.5 Set & FrozenSet (`std.collections.Set[T]`, `FrozenSet[T]`)
- Set implementations using hash table probing.
- `Set[T]` supports mutable and in-place operations: `add`, `clear`, `copy`, `discard`, `pop`, `remove`, `update`, `difference`, `difference_update`, `intersection`, `intersection_update`, `symmetric_difference`, `symmetric_difference_update`, `union`, `issubset`, `issuperset`, `isdisjoint`.
- `FrozenSet[T]` provides immutable set semantics with factory constructors `from_set` and `from_list`.

### 2.6 Bytes & ByteArray (`std.collections.Bytes`, `ByteArray`)
- `Bytes`: Immutable byte sequence with 36 text/byte manipulation methods and hex encoding/decoding (`fromhex`, `hex`).
- `ByteArray`: Mutable byte sequence supporting in-place mutation, byte insertion/deletion, and `to_bytes()` conversion.
