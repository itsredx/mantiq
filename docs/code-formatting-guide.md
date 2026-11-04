# Nizam & Mantiq Code Style & Aesthetic Formatting Guide

// ── Document Overview ───────────────────────────────────────────────────────
// Target Audience: Nizam & Mantiq Developers, Tooling Authors, Core Contributors
// Purpose: Canonical Style Guide and Code Formatter (`fmt`) Reference
// Languages: Nizam (.nz) & Mantiq (.mq)
// Status: Canonical Standard

---

## 1. The Aesthetic Philosophy of Nizam & Mantiq

Programming languages are not merely instructions for computers; they are medium of human thought and collaborative engineering. Both **Nizam** and **Mantiq** place visual elegance, aesthetic balance, and cognitive ergonomics at the center of language design.

### 1.1 The Dual-Language Aesthetic Continuum
- **Nizam (`.nz`)**: Designed for systems programming, zero-cost abstractions, predictable memory ownership, SIMD/parallel loops, and quantum hardware. Its aesthetic is **disciplined, transparent, and razor-sharp**. Memory layouts, raw pointers (`ptr[T]`), and Non-Lexical Lifetimes (`life[a]`) are made visible without syntax noise.
- **Mantiq (`.mq`)**: Designed for toolkits, user interfaces, dynamic application layers, and rapid iteration. Its aesthetic is **declarative, expressive, and fluid**. First-class color literals (`#1E1E2E`), declarative UI trees, spread operators (`...`), and actor channels cascade naturally down the screen.

### 1.2 The Golden Rules of Formatting
1. **Zero Style Bikeshedding**: There is only one canonical representation for any AST. Formatting is fully automated via `nizam fmt` / `mantiq fmt`.
2. **Strict 4-Space Indentation**: Tabs are strictly prohibited. Every nested block indents exactly 4 spaces.
3. **Structured Architectural Zoning**: Files are organized into distinct logical zones using standardized Unicode box-drawing banners (`// ── Section ───────────────────────`).
4. **Predictable Vertical Rhythm**: Blank lines are meaningful. Exactly two blank lines separate top-level definitions; exactly one blank line separates class methods.
5. **Horizontal Restraint**: Lines aim for an **88-column** soft target and strictly honor a **100-column** hard maximum.

---

## 2. Section Banners: The Architectural Skeleton

In both `.nz` and `.mq` files, code sections are visually partitioned using standardized Unicode banners. This provides instant visual indexing when scrolling through medium-to-large translation units.

### 2.1 The Banner Standard
```nz
// ── Section Name ────────────────────────────────────────────────────────
```

### 2.2 Rules for Banners
- **Prefix**: Starts with `// ── ` (`//` followed by space, two Unicode light horizontal bars `\u2500\u2500`, and a space).
- **Title**: Written in Title Case (e.g., `Imports`, `Memory Management`, `Public API`, `Tests`).
- **Trailing Fill**: A single space after the title, followed by repeated horizontal bars (`─`) extending to **column 75** (or **column 80**).
- **Vertical Spacing**:
  - Always preceded by **2 blank lines** (unless starting at line 1 of the file).
  - Always followed by **1 blank line** before the first declaration in that section.

---

## 3. Whitespace, Indentation & Line Wrapping

### 3.1 Indentation
- Every indentation level is exactly **4 spaces**.
- Tabs (`\t`) are never permitted in source files.
- Empty lines must contain **no trailing whitespace**.
- Files end with exactly **one trailing newline** (`\n`).

### 3.2 Line Length Boundaries
- **Soft Target: 88 Columns**: Group expressions and argument lists should prefer breaking across multiple lines when approaching 88 columns for optimal reading comfort.
- **Hard Limit: 100 Columns**: Code lines must not exceed 100 columns unless forced by an indivisible atomic literal (e.g., a long string literal or URL).

### 3.3 Multi-Line Breaking Heuristics
When a signature, call, or collection exceeds the column limit:
1. Break immediately after the opening delimiter (`(`, `[`, `{`).
2. Indent all elements by **4 spaces** on separate lines.
3. Place a **trailing comma** after the last element.
4. Place the closing delimiter (`)`, `]`, `}`) on its own line matching the indentation of the initiating line.

#### Function Signatures
```nz
// Multi-line parameter wrapping:
public fn transfer_aligned_buffer(
    allocator as ref MemoryAllocator,
    source_ptr as ptr[u8],
    dest_ptr as ptr[u8],
    byte_count as usize,
    alignment_boundary as usize,
) as Result[usize, MemoryError]:
    pass
```

#### Declarative Collections & UI Trees
```mq
let palette = [
    #1E1E2E,
    #313244,
    #CDD6F4,
    #89B4FA,
    #F38BA8,
]

let card = Container(
    padding = 16,
    background = #1E1E2E,
    elevation = 2,
    child = Text("Analytics Overview", color = #CDD6F4),
)
```

---

## 4. Horizontal Spacing & Operator Aesthetics

Balanced whitespace around operators prevents cognitive crowding:

### 4.1 Spacing Rules
- **Binary Operators**: Exactly 1 space before and after:
  - Arithmetic: `+`, `-`, `*`, `/`, `%`
  - Comparison: `==`, `!=`, `<`, `<=`, `>`, `>=`, `is`
  - Logical: `and`, `or`
  - Bitwise: `&`, `|`, `^`, `<<`, `>>`
  - Assignment: `=`, `+=`, `-=`, `*=`, `/=`, etc.
- **Type Bindings & Casts**:
  - `let x as i32 = 10` (1 space before and after `as`)
  - `let val = (x to f64) * 2.0` (1 space before and after `to`)
- **Systems Keywords (`ref`, `deref`)**:
  - `let p as ptr[i32] = ref val` (1 space after `ref`)
  - `let num = deref p` (1 space after `deref`)
- **Punctuation**:
  - Colons `: `: No space before; newline after (or 1 space if introducing an inline expression).
  - Commas `, `: No space before; 1 space after.
  - Semicolons `;`: No space before; 1 space after (if multi-statement on single line).
  - Parentheses/Brackets: No spaces inside: `(a, b)`, `[1, 2, 3]`, `List[T]`.

---

## 5. Vertical Rhythm & Blank Line Hierarchy

Predictable vertical blank spacing gives code a natural reading pace:

```
┌────────────────────────────────────────────────────────┐
│ Top-Level Declarations (Functions, Structs, Classes)    │
│                     [2 Blank Lines]                    │
├────────────────────────────────────────────────────────┤
│ Section Banners (// ── Name ──...)                     │
│                     [1 Blank Line]                     │
├────────────────────────────────────────────────────────┤
│ Method Definitions inside Struct / Class               │
│                     [1 Blank Line]                     │
├────────────────────────────────────────────────────────┤
│ Logical Statement Paragraphs inside Function Body      │
│                     [1 Blank Line]                     │
├────────────────────────────────────────────────────────┤
│ Adjacent Fields / Variable Declarations                │
│                     [0 Blank Lines]                    │
└────────────────────────────────────────────────────────┘
```

---

## 6. Nizam-Specific Aesthetic Standards (`.nz`)

### 6.1 Ownership, Lifetimes, and Raw Pointers
Nizam makes memory and ownership explicit without visual clutter:
- Lifetimes: `life[a] T` or `life a T` attached to types.
- Pointer syntax: `ptr[T]` with no space before `[`.
- Dereference reads: `(deref struct_ptr).field` or `deref p`.

```nz
struct WindowBuffer[T]:
    data as ptr[T]
    len as usize
    borrowed_lifetime as life[a] T

fn read_sample[T](buffer as ref WindowBuffer[T], index as usize) as Option[T]:
    if index >= (deref buffer).len:
        return Option[T].None
    return Option[T].Some(deref ((deref buffer).data + index))
```

### 6.2 Systems Loops and SIMD Decorators
- Attached decorators `@vec` and `@par` join directly to `for`:
```nz
for@vec i as usize in 0 to usize..sample_count:
    deref (dest + i) = deref (src1 + i) + deref (src2 + i)

for@par tile in image.tiles():
    tile.apply_filter()
```

### 6.3 Quantum Built-in Formatting
- Quantum registers format with dimension parameters `qreg[N]`:
- Standard gates (`H`, `CNOT`, `measure`) format cleanly as function calls with reference parameters:
```nz
fn initialize_qubits() as (bool, bool):
    var q as qreg[2]
    H(ref q[0])
    CNOT(ref q[0], ref q[1])
    return (measure(ref q[0]), measure(ref q[1]))
```

---

## 7. Mantiq-Specific Aesthetic Standards (`.mq`)

### 7.1 Object-Oriented Hierarchy & Decorators
- Access modifiers (`public`, `private`, `protected`) precede `var` and `fn`.
- Decorators (`@override`, `@final`) sit on their own line directly above the method:
```mq
interface Shape:
    fn area(self) as f64
    fn perimeter(self) as f64

class Circle(Shape):
    public var radius as f64

    public fn new(radius as f64) as Circle:
        return Circle(radius = radius)

    @override
    public fn area(self) as f64:
        return 3.1415926535 * (deref self).radius * (deref self).radius

    @override
    public fn perimeter(self) as f64:
        return 2.0 * 3.1415926535 * (deref self).radius
```

### 7.2 Color Literals
Mantiq elevates colors to first-class syntax. The formatter standardizes color literals:
- Upper-case hexadecimal characters: `#RGB`, `#RRGGBB`, `#RRGGBBAA`.
- Examples: `#000`, `#FFF`, `#1E1E2E`, `#FF5733`, `#89B4FA80`.
- Inline ternary color selection:
```mq
let status_color = #A6E3A1 if is_online else #F38BA8
```

### 7.3 Spread Operators and UI Nesting
- The spread operator `...` has no space between the dots and the expression: `...base_styles`.
- Nested declarative collections indent 4 spaces per depth:
```mq
let settings = {
    "theme": "mocha",
    "font_size": 14,
    ...user_overrides,
}
```

### 7.4 Lambdas and Closures
- Single-line: `(x as i32) => x * x`
- Multi-line block lambda:
```mq
let on_click = (btn as Button) =>:
    btn.set_loading(true)
    submit_form()
```

---

## 8. Imports and Module Organization

Imports are grouped into three sorted tiers separated by 1 blank line:
```nz
// ── Imports ─────────────────────────────────────────────────────────────
// Tier 1: Standard Library
import std.collections
from std.collections import Dict, List, Set
from std.string import String, StringBuilder

// Tier 2: Vendor / External FFI
import vendor.libpng
link "libuv.so"

// Tier 3: Local Project Modules
import codegen
import error
from symbols import Node, NodeType, Scope, Span, Symbol
```

---

## 9. Before & After Showcase

### 9.1 Nizam Unformatted vs. Canonical
````carousel
```nz
// BEFORE FORMATTING: Inconsistent spacing, crowded tokens, no banners
import std.collections
from std.string import String
struct Point{x as f64,y as f64}
fn distance(p1 as Point,p2 as Point)as f64{
var dx=p2.x-p1.x;var dy=p2.y-p1.y
return sqrt(dx*dx+dy*dy)
}
```
<!-- slide -->
```nz
// AFTER FORMATTING: Canonical Nizam Spacing & Structure
// ── Imports ─────────────────────────────────────────────────────────────
import std.collections
from std.math import sqrt
from std.string import String

// ── Geometry Primitives ─────────────────────────────────────────────────
struct Point:
    x as f64
    y as f64

public fn distance(p1 as Point, p2 as Point) as f64:
    let dx as f64 = p2.x - p1.x
    let dy as f64 = p2.y - p1.y

    return sqrt(dx * dx + dy * dy)
```
````

### 9.2 Mantiq Unformatted vs. Canonical
````carousel
```mq
// BEFORE FORMATTING: Poor UI indentation, lowercase hex colors, cramped args
let my_view=Scaffold(app_bar=AppBar(title="App",background=#ff5733),body=Column(children=[Text("Hi",color=#000),Button(label="Go",on_click=()=>run())]))
```
<!-- slide -->
```mq
// AFTER FORMATTING: Cascading Visual Clarity
let my_view = Scaffold(
    app_bar = AppBar(
        title = "App",
        background = #FF5733,
    ),
    body = Column(
        children = [
            Text("Hi", color = #000),
            Button(
                label = "Go",
                on_click = () => run(),
            ),
        ],
    ),
)
```
````

---

## 10. CLI Tooling & Automation

The formatter is bundled directly into the `nizam` and `mantiq` CLI binaries:

```bash
# Format source files in-place
nizam fmt -w src/
mantiq fmt -w examples/

# CI verification (exit code 1 if unformatted)
nizam fmt --check src/

# View unified formatting diffs
nizam fmt --diff src/main.nz
```

