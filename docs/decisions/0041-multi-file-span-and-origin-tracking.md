# ADR 0041: Multi-File Span & Origin Tracking

## Status
Accepted

## Context
When compiling multi-file programs with module imports (`import foo` or `from bar import baz`), errors occurring inside imported dependencies or during cross-module symbol resolution were previously misattributed to the root file (`src/main.nz`) or lacked valid line and column coordinates. To provide clear diagnostics, AST nodes and compiler passes must accurately record and resolve the origin file path.

## Decision
We implemented a multi-file span resolution architecture:

1. **Origin Tracking in AST Nodes**:
   - `Node.module_name` (`Option[String]`) stores the origin file path on top-level `Program` nodes, function bodies, and declarations.
   - `node_file_path(n as ptr[Node], default_file as String) as String` extracts the node's origin file path if present, falling back cleanly to the compiler pass's `current_file` context.

2. **Module Source Registration**:
   - During `Sema.load_imported_module`, when reading imported module source files from disk, the file path and content are immediately registered in `DiagnosticEngine.register_source(resolved_path, content)`.
   - The semantic analyzer switches `(deref self).current_file = resolved_path` before executing `declare_pass` and `resolve_pass` on the imported module AST, and restores the previous file path upon completion.

3. **Compiler Pass Propagation**:
   - `TypeChecker` and `BorrowChecker` inherit the `current_file` context and query `node_file_path(node, current_file)` when invoking diagnostic error reporting.

## Consequences
- Errors in imported modules display the actual imported module file path and exact source line snippet rather than misleading root file information.
- Clean fallback to `current_file` ensures nodes created programmatically (e.g. macro expansion or synthetic AST nodes) never crash with missing file metadata.
