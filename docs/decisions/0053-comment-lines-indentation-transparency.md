# Decision 0053: Comment Lines Are Transparent to Indentation Decisions

## Context

A `//` (or `/* */`) comment placed **between `if`/`elif`/`else` branches** —
at the same indentation as the branch keywords — mis-parsed: the external
scanner fired DEDENT one line early (the comment line's indentation is lower
than the enclosing block's), after which the next line's leading newline was
emitted as a NEWLINE token that `if_stmt`'s `repeat(seq('elif', ...))` cannot
accept. One misplaced comment cascaded E0101/E0102 errors across the rest of
the file. Comments worked only *inside* branch bodies.

The defect lived in `tree-sitter-mantiq/src/scanner.c`, not the grammar —
`comment` is an `extra`, but the scanner's structural decisions (INDENT /
DEDENT / NEWLINE) were made from whatever line the scanner happened to be
positioned on, including comment-only lines.

## Decision

In the scanner's DEDENT check: when the would-be dedent trigger is a comment
at line start, **skip comment/blank lines (consuming them into the scanner,
which is equivalent to the parser skipping extras) and re-measure from the
next content line** before deciding. The dedent then reflects the line the
parser will actually land on; if the re-measured line is no longer a dedent,
the normal INDENT/NEWLINE logic takes over.

Line-comment runs to EOF defer the dedent to the EOF handler. A lone `/` at
line start (expression continuation, not a comment) rewinds with `return
false`. Trailing comments after code and comments as an entire branch body
(deeper indentation) never enter this path — their original behavior was
correct and is preserved.

Comment-as-branch-body was verified to parse correctly *before* this change
(0 errors), so the fix is deliberately minimal: only the between-branches /
lower-indent DEDENT path changes.

## Verification

- Probe matrix (`/tmp/elif_cmt.nz`, `/tmp/elif_matrix.nz`): comments before a
  fn, at top of body, inside branches, between if/elif/elif/else branches, a
  trailing body comment, and a block comment before a statement — all parse
  clean and run correctly end-to-end (`done 0`).
- Full-corpus parse sweep: every `src/*.nz`, `std/*.nz`, all native/wasm test
  files (`src/tests/**`) — 0 ERROR nodes anywhere.
- Full RT-unlink chain gate 50/50 + promotion; wasm suites 9/9; zero-runtime
  3/3 (Gate A native 25080 B).
- Editor tree-sitter wasm rebuilt from the fixed grammar/scanner and
  redeployed (`~/.local/lib/mantiq/tree-sitter-mantiq.wasm`, Oct 7 → current).

## Notes

- This matters acutely for the planned REPL/JIT (see `docs/jit-design.md`):
  interactive sessions funnel comment-laden snippets through this scanner.
- The tree-sitter CLI caches compiled parsers; a stale cache masked a
  diagnostic iteration during the fix (cleared `~/.cache/tree-sitter`).
- The wasm32 tree-sitter archive recipe's inline paths were stale; the
  working invocation is `zig cc -Oz -target wasm32-wasi -I $TS/include
  -I $TS/src -I tree-sitter-mantiq/src` with `$TS =
  ~/.cargo/registry/src/index.crates.io-*/tree-sitter-0.26.7` (the `-I
  $TS/src` provides `unicode/umachine.h` for tree-sitter 0.26.7's lib.c).
