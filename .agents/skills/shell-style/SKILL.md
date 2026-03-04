---
name: shell-style
description: Shell script style conventions for this repo. Use when writing or editing .sh files or the bin/box script.
---

# Shell Script Style

- Shebang: `#!/usr/bin/env bash`
- Always `set -euo pipefail`
- Quote all variable expansions: `"$var"`, not `$var`
- Use `printf` over `echo` for anything with escape sequences or formatting
- Use `$'\033[...'` syntax for ANSI color variables — single-quoted `'\033[...'` stores a literal backslash string that `cat`/heredocs output verbatim; only `$'...'` makes bash interpret the escape at assignment time
- Use `local` for function-scoped variables
- Keep functions focused and short
- No comments explaining obvious code; comments only for non-obvious intent
