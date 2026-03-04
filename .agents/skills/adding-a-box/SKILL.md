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
4. Add `box-dev` to the cleanup image list in `.github/workflows/build.yml`
5. In the `changes` job in `.github/workflows/build.yml`:
   - Add a filter entry to the `paths-filter` step:
     ```yaml
     dev:
       - 'dev/**'
     ```
   - Wire it into the `Compute build flags` step — read the filter output and append to the `boxes` array:
     ```bash
     dev="${{ steps.filter.outputs.dev }}"
     [[ "$force" == "true" ]] && dev=true
     [[ "$base" == "true" || "$dev" == "true" ]] && boxes+=('"dev"')
     ```
   The dynamic matrix and `fromJson` handle the rest — no other outputs or conditions to update.
6. `bin/box` auto-discovers it -- no changes needed there
7. Update `AGENTS.md` and `.cursor/skills/repo-overview/SKILL.md` to mention the new box
