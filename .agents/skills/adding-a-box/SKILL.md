---
name: adding-a-box
description: Step-by-step guide for adding a new distrobox definition. Use when creating a new box, adding a new environment, or duplicating an existing box.
---

# Adding a New Box

To add a new box (e.g., `dev`):

1. Create `dev/Containerfile`:
   ```dockerfile
   ARG BASE_IMAGE=ghcr.io/gablank/box-base:latest
   FROM ${BASE_IMAGE}
   ARG BUILD_DATE=unknown
   ARG BUILD_SHA=unknown
   # Add box-specific packages here
   COPY dev/local-bin/ /usr/local/bin/
   RUN chmod +x /usr/local/bin/* 2>/dev/null || true
   RUN printf 'build_date=%s\nbuild_sha=%s\nimage=box-dev\n' \
           "$BUILD_DATE" "$BUILD_SHA" > /etc/box-build-info
   ```
2. Create `dev/distrobox.ini` (follow existing pattern from priv/ or work/)
3. Create `dev/local-bin/.gitkeep`
4. Add `dev` to the matrix in `.github/workflows/build.yml` and to the cleanup image list
5. Add a filter entry to the `changes` job's `paths-filter` in `.github/workflows/build.yml`:
   ```yaml
   dev:
     - 'dev/**'
   ```
   Then wire it into the `Compute build flags` step:
   ```bash
   dev="${{ steps.filter.outputs.dev }}"
   [[ "$force" == "true" ]] && dev=true
   build_dev=false
   [[ "$base" == "true" || "$dev" == "true" ]] && build_dev=true
   echo "build_dev=$build_dev" >> "$GITHUB_OUTPUT"
   ```
   And add `build_dev` to the job `outputs:` block and to the `build-boxes` matrix `if:` condition.
6. `bin/box` auto-discovers it -- no changes needed there
7. Update `AGENTS.md` and `.cursor/skills/repo-overview/SKILL.md` to mention the new box
