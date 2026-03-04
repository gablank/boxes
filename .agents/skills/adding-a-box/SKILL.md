---
name: adding-a-box
description: Step-by-step guide for adding a new distrobox definition. Use when creating a new box, adding a new environment, or duplicating an existing box.
---

# Adding a New Box

To add a new box (e.g., `dev`):

1. Create `dev/Containerfile`:
   ```dockerfile
   FROM ghcr.io/gablank/box-base:latest
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
5. `bin/box` auto-discovers it -- no changes needed there
6. Update `AGENTS.md` and `.cursor/skills/repo-overview/SKILL.md` to mention the new box
