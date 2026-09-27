# Python 3.8+ Data Model Parity & Standard Collections Specification

## 1. Overview & Architectural Motivation

To achieve seamless transpilation from Python to Nizam and zero-friction interoperation across FFI boundaries, the Mantiq standard library (`std.string`, `std.collections`, and native runtime primitives) provides **direct method-for-method and semantic parity** with Python 3.8+ core built-in data types.

Because method names, parameter conventions, and default behaviors align directly with Python, the Python-to-Nizam transpiler maps calls to these collections as **direct pass-throughs** without complex syntax rewrites or runtime wrapper overhead.

---

## 2. String (`str` -> `std.string.String`)

The Mantiq native `String` type provides 100% method coverage for Python 3.8+ `str`. All methods match Python signatures and naming conventions.

| Python `str` Method | Mantiq Status | Implementation Location | Notes |
| :--- | :--- | :--- | :--- |
| `capitalize() -> String` | ✅ Implemented | `mantiq/std/string.nz:163` | Uppercases first character, lowercases rest |
| `casefold() -> String` | ✅ Implemented | `mantiq/std/string.nz:183` | Aggressive lowercase conversion for caseless matching |
| `center(width, fillchar=" ") -> String` | ✅ Implemented | `mantiq/std/string.nz:572` | Centers string within specified width |
| `count(sub, start=0, end=-1) -> i64` | ✅ Implemented | `mantiq/std/string.nz:430` | Counts non-overlapping substring occurrences |
| `encode() -> List[u8]` | ✅ Implemented | `mantiq/std/string.nz:1074` | Returns raw UTF-8 byte representation |
| `endswith(suffix, start=0, end=-1) -> bool` | ✅ Implemented | `mantiq/std/string.nz:481` | Validates prefix with slice range |
| `expandtabs(tabsize=8) -> String` | ✅ Implemented | `mantiq/std/string.nz:661` | Expands tab characters to spaces |
| `find(sub, start=0, end=-1) -> i64` | ✅ Implemented | `mantiq/std/string.nz:371` | Lowest index of substring, or -1 if absent |
| `format(args: List[String]) -> String` | ✅ Implemented | `mantiq/std/string.nz` | Positional replacement, `{{}}` escape handling |
| `format_map(mapping: Dict[String, String]) -> String` | ✅ Implemented | `mantiq/std/string.nz:1125` | Formats string using key-value dictionary |
| `index(sub, start=0, end=-1) -> i64` | ✅ Implemented | `mantiq/std/string.nz:424` | Lowest index of substring (returns -1 if absent) |
| `isalnum() -> bool` | ✅ Implemented | `mantiq/std/string.nz:232` | Checks if alphanumeric |
| `isalpha() -> bool` | ✅ Implemented | `mantiq/std/string.nz:244` | Checks if alphabetic |
| `isascii() -> bool` | ✅ Implemented | `mantiq/std/string.nz:256` | Checks if all characters are ASCII (<128) |
| `isdecimal() -> bool` | ✅ Implemented | `mantiq/std/string.nz:264` | Checks if decimal characters ('0'-'9') |
| `isdigit() -> bool` | ✅ Implemented | `mantiq/std/string.nz:275` | Checks digits |
| `isidentifier() -> bool` | ✅ Implemented | `mantiq/std/string.nz:281` | Checks if valid programming identifier |
| `islower() -> bool` | ✅ Implemented | `mantiq/std/string.nz:297` | Checks if all cased characters are lowercase |
| `isnumeric() -> bool` | ✅ Implemented | `mantiq/std/string.nz:278` | Checks numeric characters |
| `isprintable() -> bool` | ✅ Implemented | `mantiq/std/string.nz:361` | Checks printable characters |
| `isspace() -> bool` | ✅ Implemented | `mantiq/std/string.nz:349` | Checks whitespace |
| `istitle() -> bool` | ✅ Implemented | `mantiq/std/string.nz:325` | Checks title-cased words |
| `isupper() -> bool` | ✅ Implemented | `mantiq/std/string.nz:311` | Checks uppercase |
| `join(parts: List[String]) -> String` | ✅ Implemented | `mantiq/std/string.nz:951` | Joins string elements with separator |
| `ljust(width, fillchar=" ") -> String` | ✅ Implemented | `mantiq/std/string.nz:597` | Left-justifies string |
| `lower() -> String` | ✅ Implemented | `mantiq/std/string.nz:133` | Lowercase conversion |
| `lstrip(chars=None) -> String` | ✅ Implemented | `mantiq/std/string.nz:509` | Strips leading whitespace or character set |
| `maketrans(from_s, to_s) -> Dict[i64, i64]` | ✅ Implemented | `mantiq/std/string.nz:1109` | Generates character mapping translation table |
| `partition(sep) -> List[String]` | ✅ Implemented | `mantiq/std/string.nz` | Returns 3-element list `[prefix, sep, suffix]` |
| `removeprefix(prefix) -> String` | ✅ Implemented | `mantiq/std/string.nz:1041` | Removes prefix (Python 3.9+) |
| `removesuffix(suffix) -> String` | ✅ Implemented | `mantiq/std/string.nz:1057` | Removes suffix (Python 3.9+) |
| `replace(old, new, count=-1) -> String` | ✅ Implemented | `mantiq/std/string.nz:983` | Substring replacement with optional limit |
| `rfind(sub, start=0, end=-1) -> i64` | ✅ Implemented | `mantiq/std/string.nz:398` | Highest index of substring |
| `rindex(sub, start=0, end=-1) -> i64` | ✅ Implemented | `mantiq/std/string.nz:427` | Highest index of substring |
| `rjust(width, fillchar=" ") -> String` | ✅ Implemented | `mantiq/std/string.nz:613` | Right-justifies string |
| `rpartition(sep) -> List[String]` | ✅ Implemented | `mantiq/std/string.nz` | Returns 3-element list partitioned from right |
| `rsplit(sep=None, maxsplit=-1) -> List[String]` | ✅ Implemented | `mantiq/std/string.nz:778` | Splits string from right |
| `rstrip(chars=None) -> String` | ✅ Implemented | `mantiq/std/string.nz:541` | Strips trailing whitespace |
| `split(sep=None, maxsplit=-1) -> List[String]` | ✅ Implemented | `mantiq/std/string.nz:703` | Splits string by delimiter or whitespace |
| `splitlines(keepends=False) -> List[String]` | ✅ Implemented | `mantiq/std/string.nz:916` | Universal newline splitting (`\n`, `\r\n`, `\r`) |
| `startswith(prefix, start=0, end=-1) -> bool` | ✅ Implemented | `mantiq/std/string.nz:461` | Prefix check |
| `strip(chars=None) -> String` | ✅ Implemented | `mantiq/std/string.nz:503` | Strips leading and trailing whitespace |
| `swapcase() -> String` | ✅ Implemented | `mantiq/std/string.nz:186` | Inverts casing |
| `title() -> String` | ✅ Implemented | `mantiq/std/string.nz:203` | Title-cases words |
| `translate(table: Dict[i64, i64]) -> String` | ✅ Implemented | `mantiq/std/string.nz:1082` | Translates characters via lookup table |
| `upper() -> String` | ✅ Implemented | `mantiq/std/string.nz:148` | Uppercase conversion |
| `zfill(width) -> String` | ✅ Implemented | `mantiq/std/string.nz:630` | Left-pads string with ASCII zeros |

* **Dunder Methods Supported:** `__len__`, `__contains__`, `__eq__`, `__ne__`, `__add__`, `__mul__`, `__getitem__`.
* **Verification Suite:** `mantiq/src/tests/test_string_methods.nz` (24 sub-tests covering all methods and default argument overloads).

---

## 3. List (`list` -> `std.collections.List[T]`)

The Mantiq native `List[T]` implements dynamic resizable array semantics with identical method signatures.

| Python `list` Method | Mantiq Status | Native Implementation | Notes |
| :--- | :--- | :--- | :--- |
| `append(x)` | ✅ Implemented | `__mantiq_list_append` | Appends element to list |
| `extend(iter)` | ✅ Implemented | `__mantiq_list_extend` | Extends list with elements from iterable |
| `clear()` | ✅ Implemented | Native runtime | Frees backing buffer and resets count to 0 |
| `count(x) -> i64` | ✅ Implemented | `__mantiq_list_count` | Counts matching elements |
| `index(x) -> i64` | ✅ Implemented | `__mantiq_list_index` | Returns first index or -1 |
| `insert(i, x)` | ✅ Implemented | `__mantiq_list_insert` | Python clamp & negative-index semantics |
| `remove(x)` | ✅ Implemented | `__mantiq_list_remove` | Removes first matching element |
| `reverse()` | ✅ Implemented | `__mantiq_list_reverse` | In-place reversal |
| `copy() -> List[T]` | ✅ Implemented | `__mantiq_list_copy` | Shallow copy |
| `pop([idx]) -> T` | ✅ Implemented | `__mantiq_list_pop` / `__mantiq_list_pop_index` | Removes and returns element (default last, supports negative indices) |
| `sort()` | ✅ Implemented | `__mantiq_list_sort` / `__mantiq_list_sort_str` | In-place numeric and lexicographic string sorting |

* **Dunder Methods Supported:** `__len__`, `__getitem__`, `__setitem__`, `__delitem__`, `__iter__`, `__contains__`.
* **Verification Suite:** `mantiq/src/tests/test_list_methods.nz` (12 sub-tests covering all operations).

---

## 4. Tuple (`tuple` -> `std.collections.Tuple[T]`)

Immutable sequence types implemented in `std.collections`:

| Python `tuple` Method | Mantiq Status | Native Implementation | Notes |
| :--- | :--- | :--- | :--- |
| `count(x) -> i64` | ✅ Implemented | `Tuple.count` | Counts occurrences of element |
| `index(x) -> i64` | ✅ Implemented | `Tuple.index` | Returns first index or -1 |
| `length() -> i64` | ✅ Implemented | `Tuple.length` | Element count (`len(t)`) |
| `get(i) -> T` | ✅ Implemented | Direct element access | Zero-overhead indexing |
| `__getitem__(i) -> T` | ✅ Implemented | Direct subscript `t[i]` | Compiler-supported indexing |

* **Verification Suite:** `mantiq/src/tests/test_tuple_methods.nz`.

---

## 5. Dictionary (`dict` -> `std.collections.Dict[K, V]`)

High-performance hash map with open-addressing bitmask probing:

| Python `dict` Method | Mantiq Status | Native Implementation | Notes |
| :--- | :--- | :--- | :--- |
| `clear()` | ✅ Implemented | `__mantiq_dict_clear` | Clears all entries |
| `copy() -> Dict[K, V]` | ✅ Implemented | `__mantiq_dict_copy` | Shallow clone with capacity preservation |
| `fromkeys(seq, [v])` | ✅ Implemented | `__mantiq_dict_fromkeys` | Creates dictionary from key sequence with default |
| `get(k, [default]) -> V` | ✅ Implemented | `__mantiq_dict_get` | Key lookup with optional default fallback |
| `items() -> DictItems[K, V]` | ✅ Implemented | `DictItems` View Struct | Provides `.length()`, `.keys()`, `.values()`, `.mapping()`, `.to_list()` |
| `keys() -> List[K]` | ✅ Implemented | `__mantiq_dict_keys` | Returns list of all keys |
| `pop(k, [default]) -> V` | ✅ Implemented | `__mantiq_dict_pop` | Removes and returns value or default |
| `popitem()` | ✅ Implemented | `__mantiq_dict_popitem` | In-place removal of last inserted entry |
| `setdefault(k, [default]) -> V` | ✅ Implemented | `__mantiq_dict_setdefault` | Inserts default if missing, returns value |
| `update(other)` | ✅ Implemented | `__mantiq_dict_merge` | Merges entries from another dictionary |
| `values() -> List[V]` | ✅ Implemented | `__mantiq_dict_values` | Returns list of all values |

* **Dictionary Views:** Python 3.10+ `.mapping` property and view methods supported on `dict.keys()`, `dict.values()`, and `dict.items()`.
* **Verification Suite:** `mantiq/src/tests/test_dict_methods.nz`.

---

## 6. Set & FrozenSet (`set`, `frozenset` -> `std.collections.Set[T]`, `FrozenSet[T]`)

### 6.1 `Set[T]` (Mutable Set)
| Python `set` Method | Mantiq Status | Native Implementation | Notes |
| :--- | :--- | :--- | :--- |
| `add(elem)` | ✅ Implemented | `Set.add` | Inserts element |
| `clear()` | ✅ Implemented | `Set.clear` | Removes all elements |
| `copy() -> Set[T]` | ✅ Implemented | `Set.copy` | Shallow clone |
| `difference(other) -> Set[T]` | ✅ Implemented | `Set.difference` | Returns elements in self but not other (`a - b`) |
| `difference_update(other)` | ✅ Implemented | `Set.difference_update` | In-place difference (`a -= b`) |
| `discard(elem)` | ✅ Implemented | `Set.discard` | Removes element without error if absent |
| `intersection(other) -> Set[T]` | ✅ Implemented | `Set.intersection` | Elements common to both (`a & b`) |
| `intersection_update(other)` | ✅ Implemented | `Set.intersection_update` | In-place intersection (`a &= b`) |
| `isdisjoint(other) -> bool` | ✅ Implemented | `Set.isdisjoint` | True if no common elements |
| `issubset(other) -> bool` | ✅ Implemented | `Set.issubset` | True if subset (`a <= b`) |
| `issuperset(other) -> bool` | ✅ Implemented | `Set.issuperset` | True if superset (`a >= b`) |
| `pop() -> T` | ✅ Implemented | `Set.pop` | Removes and returns arbitrary element |
| `remove(elem) -> bool` | ✅ Implemented | `Set.remove` | Removes element |
| `symmetric_difference(other)` | ✅ Implemented | `Set.symmetric_difference` | Elements in either but not both (`a ^ b`) |
| `symmetric_difference_update` | ✅ Implemented | `Set.symmetric_difference_update` | In-place symmetric difference (`a ^= b`) |
| `union(other) -> Set[T]` | ✅ Implemented | `Set.union` | Combined elements (`a \| b`) |
| `update(other)` | ✅ Implemented | `Set.update` | In-place union (`a \|= b`) |

### 6.2 `FrozenSet[T]` (Immutable Set)
Implements all non-mutating set operations: `copy`, `difference`, `intersection`, `isdisjoint`, `issubset`, `issuperset`, `symmetric_difference`, `union`.
- Constructors: `FrozenSet.from_set(s)` and `FrozenSet.from_list(items)`.
* **Verification Suite:** `mantiq/src/tests/test_set_methods.nz`.

---

## 7. Bytes & ByteArray (`bytes`, `bytearray` -> `std.collections.Bytes`, `ByteArray`)

### 7.1 `Bytes` (Immutable Byte Sequence)
36 methods implemented mirroring Python `bytes`:
`capitalize`, `center`, `count`, `decode`, `endswith`, `expandtabs`, `find`, `fromhex`, `hex`, `index`, `isalnum`, `isalpha`, `isascii`, `isspace`, `islower`, `isupper`, `join`, `ljust`, `lower`, `lstrip`, `maketrans`, `partition`, `removeprefix`, `removesuffix`, `replace`, `rfind`, `rindex`, `rjust`, `rpartition`, `rsplit`, `rstrip`, `split`, `splitlines`, `startswith`, `strip`, `swapcase`, `title`, `translate`, `upper`, `zfill`.

### 7.2 `ByteArray` (Mutable Byte Sequence)
Implements all `Bytes` operations plus in-place mutation:
`append`, `clear`, `copy`, `count`, `decode`, `endswith`, `extend`, `find`, `fromhex`, `hex`, `index`, `insert`, `pop`, `pop_index`, `remove`, `reverse`, `split`, `replace`, `startswith`, `strip`, `lstrip`, `rstrip`, `lower`, `upper`, `swapcase`, `capitalize`, `title`, `center`, `expandtabs`, `join`, `partition`, `rpartition`, `rsplit`, `splitlines`, `translate`, `to_bytes`.

* **Verification Suite:** `mantiq/src/tests/test_bytes_methods.nz`.

---

## 8. Summary of Test Coverage

All data models and their parity behaviors are continuously verified under the Mantiq test suite:
- `mantiq/src/tests/test_string_methods.nz`
- `mantiq/src/tests/test_list_methods.nz`
- `mantiq/src/tests/test_dict_methods.nz`
- `mantiq/src/tests/test_set_methods.nz`
- `mantiq/src/tests/test_tuple_methods.nz`
- `mantiq/src/tests/test_bytes_methods.nz`
