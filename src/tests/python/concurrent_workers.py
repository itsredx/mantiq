# ── Concurrent Worker Multi-Process Import Test ───────────────────────────
"""Simulates 8 concurrent worker processes importing the same .nz file."""

import os
import sys
import shutil
import multiprocessing as mp

def worker_import(idx: int):
    import nizam
    nizam.install()
    import concurrent_kernel
    res1 = concurrent_kernel.compute_worker_val(idx, 10)
    res2 = concurrent_kernel.sum_worker_data(idx, 2.5)
    expected_res1 = (idx * 10) + 42
    expected_res2 = (float(idx) * 2.5) + 100.5
    assert res1 == expected_res1, f"Worker {idx}: expected {expected_res1}, got {res1}"
    assert abs(res2 - expected_res2) < 1e-6, f"Worker {idx}: expected {expected_res2}, got {res2}"
    return (idx, res1, res2)

def main():
    # Clear any previous cache to force compilation under concurrent load
    cache_dir = os.path.join(os.path.dirname(__file__), "__pycache__", ".nizam_cache")
    if os.path.exists(cache_dir):
        shutil.rmtree(cache_dir, ignore_errors=True)

    workers = 8
    print(f"Launching {workers} concurrent workers attempting on-the-fly import...")
    with mp.Pool(workers) as pool:
        results = pool.map(worker_import, range(workers))

    print(f"All {workers} workers finished successfully!")
    for idx, r1, r2 in sorted(results):
        print(f"  Worker {idx} -> compute_worker_val: {r1}, sum_worker_data: {r2:.2f}")

if __name__ == "__main__":
    main()
