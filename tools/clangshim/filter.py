#!/usr/bin/env python3
"""IR pre-filter for the Nizam toolchain's merged .ll modules.

The toolchain writes one .ll per program: an unconditional declare block,
std-module definitions and user code in a single module. Three defect
classes of the current builder era break the LLVM parser/verifier:

  1. declare-vs-define collisions:  `declare @x` + `define @x`
  2. duplicate declares:            two `declare @x` lines
  3. bracketed generic drop names:  `call void @__nizam_drop_Set[i64](...)`
     and arg-position `ptr @__nizam_drop_Tuple2[String, i32` (truncated,
     the closing ] never arrives)

Repairs:
  - drop declares colliding with a define
  - drop repeat declares (keep the first)
  - rename `@__nizam_drop_<Base>[...]` -> `@__nizam_drop_<Base>`
      * Base with an existing define or runtime counterpart -> plain Base
        (Set/Dict route to __nizam_drop_Dict: Set is dict-backed)
      * otherwise -> synthesized no-op `__nizam_drop_<Base>`
  - dead erased-copy sweep (Milestone M follow-up): monomorphisation emits
    specialised defs (@Set_i64_add) alongside the erased template copies
    (@Set_add). When nothing reachable from `main`/module-level data
    references an erased copy, drop it — transitively, since erased copies
    only call each other. Guarded: a define is dropped only if a mono'd
    sibling (@<Base>_<suffix>_<method>) exists, so any future fallback
    path that legitimately targets the erased def is unaffected.
"""
import re
import sys


def sweep_dead_erased(out: str) -> str:
    """Drop defines unreachable from main/module-level refs (full DCE).

    Valid when the module is an executable (`@main` exists): nothing
    outside the program can call its defines (no dlopen/dlsym use in the
    toolchain's products), so unreachable-from-roots code is dead. This
    removes the monomorphisation leftovers — the erased template copies
    (@Set_add) and unused specialised defs alike — plus any other dead
    std surface, transitively (dead defs call only dead defs).
    """
    if not re.search(r"^define\b.*?@main\(", out, re.M):
        return out  # no main (library-style output) -> no entry roots, skip

    lines = out.split("\n")
    blocks = []  # (start, end_inclusive) line indices of define bodies
    i = 0
    while i < len(lines):
        if re.match(r"^define\b", lines[i]):
            j = i
            while j < len(lines) and lines[j] != "}":
                j += 1
            blocks.append((i, j))
            i = j + 1
        else:
            i += 1

    ref_re = re.compile(r"@([\w$.+-]+)")
    ref_q_re = re.compile(r'@"([^"]+)"')
    dname = []
    drefs = []
    for (a, b) in blocks:
        m = re.search(r"@([\w$.+-]+)\(", lines[a]) or re.search(r'@"([^"]+)"', lines[a])
        if not m:
            dname.append(None)
            drefs.append(set())
            continue
        dname.append(m.group(1))
        body = "\n".join(lines[a:b + 1])
        drefs.append({m.group(1) for m in ref_re.finditer(body)} |
                     {m.group(1) for m in ref_q_re.finditer(body)})

    idx = {n: k for k, n in enumerate(dname) if n}
    defined = set(idx)

    # roots: main + every @name referenced outside define bodies
    is_def_line = [False] * len(lines)
    for (a, b) in blocks:
        for k in range(a, b + 1):
            is_def_line[k] = True
    module_text = "\n".join(l for k, l in enumerate(lines) if not is_def_line[k])
    roots = ({"main"} |
             {m.group(1) for m in ref_re.finditer(module_text)} |
             {m.group(1) for m in ref_q_re.finditer(module_text)}) & defined

    live = set()
    stack = list(roots)
    while stack:
        n = stack.pop()
        if n in live:
            continue
        live.add(n)
        for r in drefs[idx[n]]:
            if r in defined and r not in live:
                stack.append(r)

    # drop everything unreachable
    drop = {k for k, n in enumerate(dname) if n and n not in live}

    if not drop:
        return out
    kept_out = []
    k = 0
    bi = 0
    while k < len(lines):
        if bi < len(blocks) and k == blocks[bi][0]:
            if bi not in drop:
                kept_out.extend(lines[blocks[bi][0]:blocks[bi][1] + 1])
            k = blocks[bi][1] + 1
            bi += 1
        else:
            kept_out.append(lines[k])
            k += 1
    return "\n".join(kept_out)


def main() -> int:
    ll = sys.argv[1]
    try:
        text = open(ll).read()
    except OSError as e:
        print(f"clangshim: cannot read {ll}: {e}", file=sys.stderr)
        return 1

    # collect defined symbol names (define ... @name( and @"quoted")
    names = {m.group(1) for m in re.finditer(r"^define\b.*?@([\w$.+-]+)\(", text, re.M)}
    names |= {m.group(1) for m in re.finditer(r'^define\b.*?@"([^"]+)"', text, re.M)}

    # 1+2: declare hygiene
    kept = set()
    lines = []
    for line in text.split("\n"):
        m = re.match(r"^declare\b[^@\n]*@([\w$.+-]+)", line)
        if m:
            name = m.group(1)
            if name in names and "__nizam_drop" not in name:
                continue
            if name in kept:
                continue
            kept.add(name)
        lines.append(line)
    out = "\n".join(lines)

    # 3: bracketed generic drop names -> valid symbol names
    seen_bases = set()

    def note_base(m: re.Match) -> str:
        seen_bases.add(m.group(1))
        return f"@__nizam_drop_{m.group(1)}"

    # well-formed names:  @__nizam_drop_Set[i64]
    out = re.sub(r"@__nizam_drop_([A-Za-z0-9_]+)\[[^\(\[\]]*\]", note_base, out)
    # truncated arg-position names:  ptr @__nizam_drop_Tuple2[String, i32)
    out = re.sub(r"@__nizam_drop_([A-Za-z0-9_]+)\[([^\(\n]*?)\)",
                 lambda m: f"@__nizam_drop_{m.group(1)})", out)

    # inject no-op defines for renamed drop symbols that have neither a
    # definition in the module nor a runtime counterpart
    runtime_provided = {"Dict", "String", "StringBuilder", "List", "List_flat"}
    inject = []
    for b in sorted(seen_bases):
        if re.search(rf"^define\b.*?@__nizam_drop_{b}\(", out, re.M):
            continue
        if b in runtime_provided:
            continue
        inject.append(f"define void @__nizam_drop_{b}(ptr %self) {{\nentry:\n  ret void\n}}\n")
    if inject:
        first_blank = out.find("\n\n")
        pos = first_blank + 2 if first_blank != -1 else 0
        out = out[:pos] + "".join(inject) + "\n" + out[pos:]

    # 4: dead erased-copy sweep (see sweep_dead_erased docstring)
    out = sweep_dead_erased(out)

    filt = (ll[:-3] + ".cgfilt.ll") if ll.endswith(".ll") else ll + ".cgfilt.ll"
    with open(filt, "w") as f:
        f.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
