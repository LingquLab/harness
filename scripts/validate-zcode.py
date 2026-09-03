#!/usr/bin/env python3
"""Validate the source-tree contract expected by a ZCode marketplace."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PLUGINS_ROOT = ROOT / "plugins"
NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")
CATEGORIES = {
    "developer-tools",
    "productivity",
    "utilities",
    "finance",
    "guides",
    "template",
    "other",
}


def load_object(path: Path, errors: list[str]) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{path.relative_to(ROOT)}: {exc}")
        return {}
    if not isinstance(value, dict):
        errors.append(f"{path.relative_to(ROOT)}: root must be an object")
        return {}
    return value


def require_i18n(label: str, value: object, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append(f"{label}: description_i18n must be an object")
        return
    for locale in ("en", "zh-CN"):
        text = value.get(locale)
        if not isinstance(text, str) or not text.strip():
            errors.append(f"{label}: description_i18n.{locale} is required")


def main() -> int:
    errors: list[str] = []
    catalog = load_object(ROOT / "marketplace.json", errors)
    entries = catalog.get("plugins")
    if not isinstance(catalog.get("name"), str) or not catalog["name"]:
        errors.append("marketplace.json: name is required")
    if not isinstance(catalog.get("owner"), dict):
        errors.append("marketplace.json: owner is required")
    require_i18n("marketplace.json", catalog.get("description_i18n"), errors)
    if not isinstance(entries, list) or not entries:
        errors.append("marketplace.json: plugins must be a non-empty array")
        entries = []

    seen: set[str] = set()
    registered: set[str] = set()
    for index, entry in enumerate(entries):
        label = f"marketplace.json plugins[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{label}: entry must be an object")
            continue
        name = entry.get("name")
        if not isinstance(name, str) or not NAME.fullmatch(name):
            errors.append(f"{label}: name must be unique kebab-case")
            continue
        if name in seen:
            errors.append(f"{label}: duplicate name {name}")
        seen.add(name)
        source = entry.get("source")
        expected_source = f"./plugins/{name}"
        if source != expected_source:
            errors.append(f"{label}: source must be {expected_source}")
            continue
        plugin_root = PLUGINS_ROOT / name
        registered.add(name)
        if not plugin_root.is_dir():
            errors.append(f"{label}: plugin directory does not exist")
            continue
        if any(path.is_symlink() for path in plugin_root.rglob("*")):
            errors.append(f"{label}: plugin tree must not contain symlinks")

        version = entry.get("version")
        if not isinstance(version, str) or not SEMVER.fullmatch(version):
            errors.append(f"{label}: version must use semantic versioning")
        if entry.get("category") not in CATEGORIES:
            errors.append(f"{label}: unsupported category")
        require_i18n(label, entry.get("description_i18n"), errors)

        manifest_path = plugin_root / ".zcode-plugin" / "plugin.json"
        manifest = load_object(manifest_path, errors)
        for field in ("name", "version", "description", "author"):
            if not manifest.get(field):
                errors.append(f"{manifest_path.relative_to(ROOT)}: {field} is required")
        if manifest.get("name") != name or manifest.get("version") != version:
            errors.append(f"{label}: manifest name/version must match marketplace")
        if manifest.get("description_i18n") != entry.get("description_i18n"):
            errors.append(f"{label}: localized descriptions must match manifest")
        skills = manifest.get("skills", "skills")
        if not isinstance(skills, str) or not (plugin_root / skills).is_dir():
            errors.append(f"{manifest_path.relative_to(ROOT)}: skills path is invalid")
        for readme in ("README.md", "README_CN.md"):
            path = plugin_root / readme
            if not path.is_file() or not path.read_text(encoding="utf-8").strip():
                errors.append(f"{path.relative_to(ROOT)}: non-empty file is required")

    for path in sorted(PLUGINS_ROOT.iterdir()):
        if path.is_dir() and path.name not in registered:
            errors.append(f"plugins/{path.name}: not registered in marketplace.json")

    if errors:
        print(f"FAIL: {len(errors)} problem(s)")
        for error in errors:
            print(f"  - {error}")
        return 1
    print(f"OK: {len(entries)} ZCode plugin(s) validated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
