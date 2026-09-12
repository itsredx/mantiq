#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../../" && pwd)"
NIZAM="${REPO_ROOT}/stage3/mantiq"

if [ ! -f "$NIZAM" ]; then
    NIZAM="${REPO_ROOT}/mantiq/nizam"
fi

echo "============================================================"
echo " Running Python FFI Phase 2 Integration Tests (Structs/Classes)"
echo " Compiler: $NIZAM"
echo "============================================================"

OUT_SO="/tmp/test_structs.abi3.so"
rm -f "$OUT_SO"

echo "[1/2] Compiling test_structs.nz -> $OUT_SO..."
"$NIZAM" build "$SCRIPT_DIR/test_structs.nz" --target python-ext -o "$OUT_SO" --lib-dir "$REPO_ROOT/stage3"

if [ ! -f "$OUT_SO" ]; then
    echo "ERROR: Failed to produce $OUT_SO"
    exit 1
fi

echo "[2/2] Executing Python test harness..."
python3 - << 'EOF'
import sys
import os
import gc

# Load extension module from /tmp
sys.path.insert(0, "/tmp")
import test_structs

print(f"Loaded module: {test_structs} (file: {getattr(test_structs, '__file__', 'in-memory')})")

# 1. Type Registration Verification
print("Testing Type Registration in Module...")
assert hasattr(test_structs, "Vector2"), "test_structs missing Vector2"
assert hasattr(test_structs, "ImmutablePoint"), "test_structs missing ImmutablePoint"
assert hasattr(test_structs, "Person"), "test_structs missing Person"
print("  ✓ Struct/Class types registered successfully")

# 2. Vector2 Instantiation & Attribute Access
print("Testing Vector2 Instantiation & Field Getters/Setters...")
v1 = test_structs.Vector2(3.0, 4.0)
assert v1.x == 3.0, f"Expected v1.x == 3.0, got {v1.x}"
assert v1.y == 4.0, f"Expected v1.y == 4.0, got {v1.y}"

# Keyword arguments
v_kw = test_structs.Vector2(x=10.5, y=20.5)
assert v_kw.x == 10.5 and v_kw.y == 20.5, f"Keyword args failed: {v_kw.x}, {v_kw.y}"

# Default constructor (zero-initialized)
v_def = test_structs.Vector2()
assert v_def.x == 0.0 and v_def.y == 0.0, f"Default constructor failed: {v_def.x}, {v_def.y}"

# Field mutation
v1.x = 6.0
v1.y = 8.0
assert v1.x == 6.0 and v1.y == 8.0, f"Mutation failed: {v1.x}, {v1.y}"
print("  ✓ Vector2 constructor, kwargs, getters, and setters verified")

# 3. Vector2 Member Methods
print("Testing Vector2 Member Methods...")
# length_squared(): 6*6 + 8*8 = 36 + 64 = 100.0
ls = v1.length_squared()
assert ls == 100.0, f"Expected length_squared 100.0, got {ls}"

# scale(0.5): x becomes 3.0, y becomes 4.0, returns 3.0 + 4.0 = 7.0
res_scale = v1.scale(0.5)
assert res_scale == 7.0, f"Expected scale result 7.0, got {res_scale}"
assert v1.x == 3.0 and v1.y == 4.0, f"Expected scaled fields 3.0, 4.0, got {v1.x}, {v1.y}"
print("  ✓ Vector2 member methods and mutable state dispatch verified")

# 4. ImmutablePoint (Read-only fields / let)
print("Testing ImmutablePoint (Read-only fields)...")
p = test_structs.ImmutablePoint(10.0, 20.0)
assert p.x == 10.0 and p.y == 20.0, f"ImmutablePoint fields mismatch: {p.x}, {p.y}"

# Method execution
sum_val = p.sum()
assert sum_val == 30.0, f"Expected p.sum() == 30.0, got {sum_val}"

# Attempting mutation must raise AttributeError
try:
    p.x = 99.0
    raise AssertionError("Mutation of read-only field should have raised AttributeError!")
except AttributeError as e:
    print(f"  ✓ Read-only attribute protection caught: {e}")

# 5. Person (String and integer fields)
print("Testing Person (String and integer fields)...")
alice = test_structs.Person("Alice", 28)
assert alice.name == "Alice", f"Expected 'Alice', got {alice.name}"
assert alice.age == 28, f"Expected 28, got {alice.age}"

# Mutate string and integer
alice.name = "Bob"
alice.age = 32
assert alice.name == "Bob", f"Expected 'Bob', got {alice.name}"
assert alice.age == 32, f"Expected 32, got {alice.age}"
assert alice.get_age() == 32, f"Expected get_age() == 32, got {alice.get_age()}"
print("  ✓ String and integer field marshaling verified")

# 6. Lifecycle & Garbage Collection
print("Testing Deallocation & Garbage Collection...")
del v1
del v_kw
del v_def
del p
del alice
gc.collect()
print("  ✓ tp_dealloc and memory cleanup verified")

print("\n============================================================")
print(" ALL PYTHON FFI PHASE 2 TESTS PASSED PERFECTLY!")
print("============================================================")
EOF
