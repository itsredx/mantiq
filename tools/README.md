# Toolchain bootstrap and validation chains

Binary roles (living copies in `~/.local/share/nizam-tools/`):

| Binary | Role |
|---|---|
| `nizam-new` | **Canonical self-hosted compiler** (gen-3 lineage, 50/50-validated). |
| `nizam-self-promoted` | Snapshot of the last 50/50 self-hosted build; the chain's builder. |
| `nizam-new-fixed7` | Chain build output; promoted to `nizam-new` only at 50/50. |
| `nizam-new-next` | OLD frozen builder (27-min builds) — bootstrap fallback only. |
| `nizam-new-preSelfHost.bak` / `nizam-new-prev.bak` | Rollback points. |

## Chains

- **`chain_stable.sh`** — going-forward flow: `nizam-self-promoted` builds
  `src/main.nz` (~3 min) -> `nizam-new-fixed7` -> nm sweep -> `test_std`
  gate -> full 50-test suite (2-way parallel: worker 2 gets an isolated
  cwd-relative cache, wiped every run; journal-resumable) -> promote
  to `nizam-new` at 50/50. Run after any compiler-source change.
- **`selfhost_bootstrap.sh`** — recovery flow: canonical compiler builds
  itself into `nizam-self` (supervised, 3 attempts, RSS circuit-breaker at
  1.45 GB for low-RAM hosts). Use when the toolchain is broken or to prove
  the fixed point after Milestone-N-style changes.
- **`selfhost_chain.sh`** — the original gen-2 validation flow
  (`nizam-self` -> `nizam-self2` -> suite -> `nizam-self-promoted`).
- **`rtunlink_chain.sh`** — historical Milestone-D flow (old builder);
  kept for archaeology.

All chains require `tools/clangshim/` first on PATH (declare hygiene,
drop-glue name repair, dead-code sweep — see `clangshim/filter.py`) and
`CPATH=$HOME/.local/lib/mantiq/include` for `tree_sitter/api.h`.

State/logs land in `~/.local/share/nizam-tools/` (`rtunlink.log`,
`rt_nolink.state` journal, `selfhost_build.log`, `selfhost_rss.log`).
The suite journal makes interrupted runs resumable; the cache is cleared
on every suite run so tooling changes cannot fake a pass.
