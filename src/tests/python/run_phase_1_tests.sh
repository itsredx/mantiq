#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../../../.." && pwd)"
MANTIQ_DIR="$ROOT_DIR/mantiq"
TEST_NZ="$MANTIQ_DIR/src/tests/python/test_primitives.nz"
OUT_SO="/tmp/test_primitives.abi3.so"

echo "=== Running Phase 1 Python FFI Test Suite ==="

# 1. Compile test_primitives.nz with --target python-ext
echo "Compiling $TEST_NZ -> $OUT_SO..."
cd "$MANTIQ_DIR"
./nizam build src/tests/python/test_primitives.nz -o "$OUT_SO" --target python-ext

if [ ! -f "$OUT_SO" ]; then
    echo "ERROR: Output $OUT_SO was not produced!"
    exit 1
fi

echo "Compilation succeeded: $OUT_SO"

# 2. Execute Python verification test
python3 - << 'EOF'
import sys
sys.path.insert(0, '/tmp')

import test_primitives

print("✓ Module imported successfully: test_primitives")
exports = [m for m in dir(test_primitives) if not m.startswith("__")]
print(f"✓ Module exports ({len(exports)}): {exports}")

# ── 1. Integer Operations ─────────────────────────────────────────────
assert test_primitives.add_i64(10, 20) == 30, "add_i64 failed"
assert test_primitives.add_i64(-50, 100) == 50, "add_i64 negative failed"
assert test_primitives.add_i64(2**40, 2**40) == 2**41, "add_i64 64-bit overflow check failed"
print("✓ add_i64 passed")

assert test_primitives.multiply_i32(6, 7) == 42, "multiply_i32 failed"
assert test_primitives.multiply_i32(-3, 10) == -30, "multiply_i32 negative failed"
print("✓ multiply_i32 passed")

# ── 2. Floating-Point Operations ──────────────────────────────────────
assert abs(test_primitives.scale_f64(3.5, 2.0) - 7.0) < 1e-9, "scale_f64 failed"
assert abs(test_primitives.scale_f64(-1.5, 4.0) - (-6.0)) < 1e-9, "scale_f64 negative failed"
print("✓ scale_f64 passed")

assert abs(test_primitives.add_f32(1.25, 2.5) - 3.75) < 1e-5, "add_f32 failed"
print("✓ add_f32 passed")

# ── 3. Boolean Logic ──────────────────────────────────────────────────
assert test_primitives.negate_bool(True) is False, "negate_bool(True) failed"
assert test_primitives.negate_bool(False) is True, "negate_bool(False) failed"
print("✓ negate_bool passed")

assert test_primitives.logical_and(True, True) is True, "logical_and(True, True) failed"
assert test_primitives.logical_and(True, False) is False, "logical_and(True, False) failed"
assert test_primitives.logical_and(False, True) is False, "logical_and(False, True) failed"
print("✓ logical_and passed")

# ── 4. Strings & CStr ─────────────────────────────────────────────────
assert test_primitives.echo_cstr("hello world") == "hello world", "echo_cstr failed"
assert test_primitives.echo_cstr("") == "", "echo_cstr empty failed"
print("✓ echo_cstr passed")

assert test_primitives.echo_string("nizam ffi rocks") == "nizam ffi rocks", "echo_string failed"
assert test_primitives.echo_string("🚀 Unicode strings work!") == "🚀 Unicode strings work!", "echo_string unicode failed"
print("✓ echo_string passed")

assert test_primitives.string_len("123456789") == 9, "string_len failed"
assert test_primitives.string_len("") == 0, "string_len empty failed"
print("✓ string_len passed")

# ── 5. Zero-Argument & Void Functions ─────────────────────────────────
assert test_primitives.get_version() == 42, "get_version failed"
print("✓ get_version passed")

assert test_primitives.do_nothing() is None, "do_nothing failed"
print("✓ do_nothing passed")

# ── 6. Visibility / Export Filtering ──────────────────────────────────
assert not hasattr(test_primitives, "_internal_secret"), "hidden function leaked into exports!"
assert not hasattr(test_primitives, "_hidden_fn"), "underscore-prefixed function leaked into exports!"
assert not hasattr(test_primitives, "main"), "main leaked into exports!"
print("✓ Visibility filtering passed (hidden and _-prefixed functions excluded)")

# ── 7. Exception / Type Safety Enforcement ────────────────────────────
try:
    test_primitives.add_i64(10, "not_an_int")
    assert False, "Should have raised TypeError"
except TypeError:
    pass

try:
    test_primitives.get_version(1, 2, 3)
    assert False, "Should have raised TypeError for extra args"
except TypeError:
    pass

print("✓ TypeError propagation passed")

print("\n========================================================")
print("🎉 ALL PHASE 1 PYTHON FFI TESTS PASSED SUCCESSFULLY! 🎉")
print("========================================================")
EOF
