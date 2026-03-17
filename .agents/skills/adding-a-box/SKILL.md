---
name: adding-a-box
description: Step-by-step checklist for adding (or removing) a distrobox definition. Use when creating a new box, adding a new environment, or duplicating an existing box.
---

# Adding a New Box

Complete checklist for adding a new box (e.g., `dev`). Every step is required unless noted otherwise.

## 1. Create box directory

- `dev/Containerfile`:
  ```dockerfile
  ARG BASE_IMAGE=ghcr.io/gablank/box-base:latest
  FROM ${BASE_IMAGE}
  ARG BUILD_DATE=unknown
  ARG BUILD_SHA=unknown
  # Add box-specific packages here (if any)
  COPY dev/local-bin/ /usr/local/bin/
  RUN chmod +x /usr/local/bin/* 2>/dev/null || true
  RUN printf 'build_date=%s\nbuild_sha=%s\nimage=box-dev\n' \
          "$BUILD_DATE" "$BUILD_SHA" > /etc/box-build-info
  ```
  Skip the `COPY dev/local-bin/` lines if the box has no local-bin scripts.

- `dev/box.toml`: follow existing patterns from `priv/box.toml` or `work/box.toml`. This is the source of truth; `distrobox.ini` is generated from it.

- `dev/local-bin/.gitkeep` (only if the box needs box-specific scripts)

## 2. Update CI workflow

In `.github/workflows/build.yml`:

- **Path filter** — add to the `dorny/paths-filter` `filters:` block:
  ```yaml
  dev:
    - 'dev/**'
  ```

- **Variable + force-true** — in the `Compute build flags` step, add:
  ```bash
  dev="${{ steps.filter.outputs.dev }}"
  ```
  and append `&& dev=true` to the force line.

- **Matrix wiring** — add to the `boxes` array:
  ```bash
  [[ "$base" == "true" || "$dev" == "true" ]] && boxes+=('"dev"')
  ```

- **Cleanup image list** — add `'box-dev'` to the `images` array in the cleanup job.

The dynamic matrix (`fromJson`) and `build-boxes` job handle the rest — no other CI changes needed.

## 3. Update documentation

- **`README.md`**: add row to the boxes table, add image URL to the image build section, add directory to the repo structure tree.

- **`AGENTS.md`**: add directory to the repo structure tree, update image build flow description, update containerfile conventions list.

- **`.agents/skills/repo-overview/SKILL.md`**: add to architecture list, key directories table, and image flow description.

## 4. No changes needed

These are auto-discovered or generic — no updates required:
- `bin/box` — auto-discovers boxes via `*/box.toml`
- `scripts/` — shared by all boxes
- `compile-box-toml.py` — generic compiler
- `CLAUDE.md` — no box-specific references
- `setup.sh` — uses generic examples

## Removing a Box

Reverse the steps above: delete the box directory, remove from CI (all four places), and remove from documentation (all three files).
