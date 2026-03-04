---
name: shell-style
description: Shell script style conventions for this repo. Use when writing or editing .sh files or the bin/box script.
---

# Shell Script Style

- Shebang: `#!/usr/bin/env bash`
- Always `set -euo pipefail`
- Quote all variable expansions: `"$var"`, not `$var`
- Use `printf` over `echo` for anything with escape sequences or formatting
- Use `local` for function-scoped variables
- Keep functions focused and short
- No comments explaining obvious code; comments only for non-obvious intent
