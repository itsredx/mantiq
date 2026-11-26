# Decision 0052: Pinned Wasm Runner (`nizam_wasi.js`)

## Context

There were three separate node-WASI invocation sites, each with its own flag
set, none pinned to a single source of truth:

| Site | Flags | Runner |
|---|---|---|
| `dev-sync.sh --wasm` stage4 bootstrap | `--no-incremental-marking --stack-size=16384 --max-old-space-size=384` | `mantiq/nizam_wasi.js` |
| `compiler-service/nizam_wasi.js` shebang (production) | `--no-incremental-marking --stack-size=65536 --max-old-space-size=4096` | itself |
| `run --target wasm32` in `src/main.nz` | `--experimental-wasi-unstable-preview1`, no stack/heap flags | inline `node -e '...'` one-liner |

The two `nizam_wasi.js` copies were already kept byte-identical by dev-sync
(`file|WASI Node Runner|mantiq/nizam_wasi.js|compiler-service/nizam_wasi.js`).
The unpinned half was the compiler's inline runner: a minimal duplicate of the
flag set that had already drifted. It worked only because the wasm test
programs happened not to open files or import `env.host_system` — a wasm
program with deep recursion (the reason `--stack-size` exists) or a
`host_system` import would fail there with a confusing instantiation/stack
error instead of running.

## Decision

`run --target wasm32` in `src/main.nz` now routes through the pinned
`nizam_wasi.js` launcher with the **stage4-bootstrap flag set**:

```
node --no-incremental-marking --stack-size=16384 --max-old-space-size=384 <nizam_wasi.js> <out.wasm>
```

This delegates ALL runner semantics to one file: node-22 WASI path-argument
absolutization, preopens (`/tmp`, `.`, `/`), the `env.host_system` bridge
(unsigned pointer normalization + `execSync`), and `NIZAM_WASM` path
override. Runner discovery is cwd-relative (`nizam_wasi.js`, then
`../mantiq/nizam_wasi.js`) — the documented invocation convention is "run
from the mantiq tree root" (same convention as `run_wasm_tests.sh`).

**Fallback preserved**: if no vendored runner is found, the compiler keeps
the old inline `node --experimental-wasi-unstable-preview1 -e '...'`
one-liner, so standalone builds (no mantiq checkout adjacent) still execute
wasm output. The one-liner is now explicitly a degraded fallback, not a
second implementation to maintain.

The flag matrix is frozen as the contract: stage4 bootstrap flag set for
`run --target wasm32` (test programs need deep-recursion headroom, not the
full 64K stack / 4 GB heap of the production shebang); shebang flags only
apply when `nizam_wasi.js` is exec'd directly. `--experimental-wasi-
unstable-preview1` is dropped from the pinned path (node 22 enables WASI
preview1 with an ExperimentalWarning; the stage4 bootstrap never needed the
flag).

## Verification

- `run src/tests/wasm/test_wasm_hello.nz --target wasm32` executes through
  `nizam_wasi.js` (node warnings + `Hello from WebAssembly WASI!`).
- wasm suites 9/9 through the new path.
- RT-unlink chain gate 50/50 + promotion; zero-runtime 3/3 (Gate A 25080 B).
