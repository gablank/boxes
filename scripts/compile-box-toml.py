#!/usr/bin/env python3
"""Compile box.toml → distrobox.ini.

Usage: compile-box-toml.py <box-directory>

Reads <box-directory>/box.toml, writes <box-directory>/distrobox.ini.
Requires Python 3.11+ (uses stdlib tomllib).
"""

import sys
import pathlib

try:
    import tomllib
except ModuleNotFoundError:
    print(
        "Error: Python 3.11+ is required (tomllib not found).\n"
        f"Current version: {sys.version}",
        file=sys.stderr,
    )
    sys.exit(1)


def compile_toml(box_dir: pathlib.Path) -> str:
    toml_path = box_dir / "box.toml"
    with open(toml_path, "rb") as f:
        cfg = tomllib.load(f)

    distrobox = dict(cfg.get("distrobox", {}))
    mount_dirs = cfg.get("mount-dir", [])
    mount_files = cfg.get("mount-file", [])

    name = distrobox.get("name", box_dir.name)

    # Local images (tag starts with "local-") exist only on the host —
    # override pull to false so distrobox doesn't try to fetch from the registry.
    image = distrobox.get("image", "")
    tag = image.rsplit(":", 1)[-1] if ":" in image else ""
    if tag.startswith("local-"):
        distrobox["pull"] = False

    additional_flags = distrobox.pop("additional_flags", "")

    # Append mount-file entries to additional_flags as --volume
    for mf in mount_files:
        vol = f"{mf['host']}:{mf['container']}"
        if "options" in mf:
            vol += f":{mf['options']}"
        additional_flags += f" --volume {vol}"
    additional_flags = additional_flags.strip()

    lines = [f"[{name}]"]
    for key, value in distrobox.items():
        if isinstance(value, bool):
            value = str(value).lower()
        lines.append(f"{key}={value}")

    # Emit mount-dir entries as volume= lines
    for md in mount_dirs:
        vol = f"{md['host']}:{md['container']}"
        if "options" in md:
            vol += f":{md['options']}"
        lines.append(f"volume={vol}")

    if additional_flags:
        lines.append(f"additional_flags={additional_flags}")

    return "\n".join(lines) + "\n"


def main() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <box-directory>", file=sys.stderr)
        sys.exit(1)

    box_dir = pathlib.Path(sys.argv[1])
    toml_path = box_dir / "box.toml"
    if not toml_path.exists():
        print(f"Error: {toml_path} not found", file=sys.stderr)
        sys.exit(1)

    ini_content = compile_toml(box_dir)
    ini_path = box_dir / "distrobox.ini"
    ini_path.write_text(ini_content)


if __name__ == "__main__":
    main()
