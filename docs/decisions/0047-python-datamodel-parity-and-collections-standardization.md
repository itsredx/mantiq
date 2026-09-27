# Decision 0047: Python 3.8+ Data Model Parity & Standard Collections Standardization

## Context

When transpiling Python applications to native systems code, standard library impedance mismatches frequently force transpilers to generate complex AST rewrites, intermediate conversion shims, or polyfill wrappers. For instance, translating `s.casefold()`, `d.setdefault(k, v)`, `l.insert(i, x)`, `set.symmetric_difference(b)`, or `b.decode()` into incompatible native API names introduces translation complexity, increases code generation maintenance, and risks runtime semantic divergence.

---

## Decision

We standardize the Mantiq standard library (`std.string`, `std.collections`, and native runtime primitives in `runtime.c`) to provide **100% method naming and semantic parity** with Python 3.8+ built-in collections:

1. **`String` (`std.string.String`)**:
   - Implements all 47 Python `str` methods (`capitalize`, `casefold`, `center`, `count`, `encode`, `endswith`, `expandtabs`, `find`, `format`, `format_map`, `index`, `isalnum`, `isalpha`, `isascii`, `isdecimal`, `isdigit`, `isidentifier`, `islower`, `isnumeric`, `isprintable`, `isspace`, `istitle`, `isupper`, `join`, `ljust`, `lower`, `lstrip`, `maketrans`, `partition`, `removeprefix`, `removesuffix`, `replace`, `rfind`, `rindex`, `rjust`, `rpartition`, `rsplit`, `rstrip`, `split`, `splitlines`, `startswith`, `strip`, `swapcase`, `title`, `translate`, `upper`, `zfill`).
2. **`List[T]` (`std.collections.List[T]`)**:
   - Matches Python `list` signatures (`append`, `extend`, `clear`, `count`, `index`, `insert`, `remove`, `reverse`, `copy`, `pop`, `sort`).
   - Implements Python clamp semantics and negative index resolution for `insert` and `pop`.
3. **`Dict[K, V]` (`std.collections.Dict[K, V]`)**:
   - Open-addressing bitmask hash table with 100% method parity (`clear`, `copy`, `fromkeys`, `get`, `items`, `keys`, `pop`, `popitem`, `setdefault`, `update`, `values`).
   - Implements Python 3.10+ `.mapping()` property on `DictItems` views.
4. **`Set[T]` & `FrozenSet[T]`**:
   - Implements mathematical set operations and in-place updates matching Python `set` and `frozenset`.
5. **`Tuple[T]`**:
   - Immutable sequence with zero-overhead indexing, `count`, and `index`.
6. **`Bytes` & `ByteArray`**:
   - Immutable and mutable byte sequence implementations supporting text/binary manipulation, hex translation, and slicing.

---

## Consequences & Compliance

- **Zero-Rewrite Transpilation**: The Python-to-Nizam transpiler maps collection method calls as direct pass-throughs, simplifying compiler visitor logic.
- **Mental Model Continuity**: Developers writing Nizam directly or transpiling from Python benefit from identical method names, parameter orders, and return types.
- **Verification**: Verified via dedicated automated test suites in `mantiq/src/tests/`:
  - `test_string_methods.nz`
  - `test_list_methods.nz`
  - `test_dict_methods.nz`
  - `test_set_methods.nz`
  - `test_tuple_methods.nz`
  - `test_bytes_methods.nz`
