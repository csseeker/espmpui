#!/usr/bin/env python3
"""
scripts/bump_version.py

Automates version bumping across:
  - src/espmui/__init__.py (__version__)
  - pyproject.toml (project.version)
  - package.json (version for MicroPython mip)
  - CHANGELOG.md (adds new unreleased/version section)
"""

import argparse
import datetime
import json
import re
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

INIT_PATH = ROOT_DIR / "src" / "espmui" / "__init__.py"
PYPROJECT_PATH = ROOT_DIR / "pyproject.toml"
PACKAGE_JSON_PATH = ROOT_DIR / "package.json"
CHANGELOG_PATH = ROOT_DIR / "CHANGELOG.md"


def get_current_version() -> str:
    content = INIT_PATH.read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', content, re.M)
    if not match:
        raise ValueError("Could not find __version__ in src/espmui/__init__.py")
    return match.group(1)


def parse_semver(version_str: str) -> tuple:
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?$", version_str)
    if not match:
        raise ValueError(f"Version '{version_str}' is not valid semantic versioning (e.g. 1.2.3 or 1.2.3-rc1)")
    major, minor, patch, pre = match.groups()
    return int(major), int(minor), int(patch), pre


def bump_semver(current: str, part: str) -> str:
    major, minor, patch, _ = parse_semver(current)
    if part == "major":
        return f"{major + 1}.0.0"
    elif part == "minor":
        return f"{major}.{minor + 1}.0"
    elif part == "patch":
        return f"{major}.{minor}.{patch + 1}"
    else:
        # direct version specified
        parse_semver(part)
        return part


def update_init(new_version: str):
    content = INIT_PATH.read_text(encoding="utf-8")
    new_content, count = re.subn(
        r'^__version__\s*=\s*["\'][^"\']+["\']',
        f'__version__ = "{new_version}"',
        content,
        flags=re.M,
    )
    if count == 0:
        raise ValueError("Failed to replace __version__ in src/espmui/__init__.py")
    INIT_PATH.write_text(new_content, encoding="utf-8")
    print(f"  ✓ Updated {INIT_PATH.relative_to(ROOT_DIR)} -> {new_version}")


def update_pyproject(new_version: str):
    content = PYPROJECT_PATH.read_text(encoding="utf-8")
    new_content, count = re.subn(
        r'(?m)^version\s*=\s*["\'][^"\']+["\']',
        f'version = "{new_version}"',
        content,
        count=1,
    )
    if count == 0:
        raise ValueError("Failed to replace version in pyproject.toml")
    PYPROJECT_PATH.write_text(new_content, encoding="utf-8")
    print(f"  ✓ Updated {PYPROJECT_PATH.relative_to(ROOT_DIR)} -> {new_version}")


def update_package_json(new_version: str):
    data = json.loads(PACKAGE_JSON_PATH.read_text(encoding="utf-8"))
    data["version"] = new_version
    PACKAGE_JSON_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"  ✓ Updated {PACKAGE_JSON_PATH.relative_to(ROOT_DIR)} -> {new_version}")


def update_changelog(new_version: str):
    if not CHANGELOG_PATH.exists():
        return
    content = CHANGELOG_PATH.read_text(encoding="utf-8")
    today = datetime.date.today().isoformat()
    new_header = f"## [{new_version}] - {today}\n"

    # If already has this version header, do nothing
    if f"## [{new_version}]" in content:
        print(f"  ℹ {CHANGELOG_PATH.relative_to(ROOT_DIR)} already contains section for [{new_version}]")
        return

    # Look for insertion marker or first release header
    match = re.search(r"(?m)^## \[[0-9]", content)
    if match:
        idx = match.start()
        template = (
            f"{new_header}\n"
            f"### Added\n- \n\n"
            f"### Changed\n- \n\n"
            f"### Fixed\n- \n\n"
        )
        updated_content = content[:idx] + template + content[idx:]
        CHANGELOG_PATH.write_text(updated_content, encoding="utf-8")
        print(f"  ✓ Prepended release template in {CHANGELOG_PATH.relative_to(ROOT_DIR)}")
    else:
        print(f"  ⚠ Could not find release section marker in {CHANGELOG_PATH.name}")


def main():
    parser = argparse.ArgumentParser(description="Bump version for espmui.")
    parser.add_argument(
        "target",
        help="Semantic increment ('patch', 'minor', 'major') or explicit version (e.g. '0.2.0')",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print changes without modifying files",
    )

    args = parser.parse_args()

    current = get_current_version()
    new_version = bump_semver(current, args.target)

    print(f"Bumping version: {current} -> {new_version}")

    if args.dry_run:
        print("Dry run requested. No files modified.")
        return

    update_init(new_version)
    update_pyproject(new_version)
    update_package_json(new_version)
    update_changelog(new_version)

    print("\nNext steps:")
    print("1. Review changes in CHANGELOG.md")
    print("2. Run tests & packaging: make release-check")
    print(f"3. Git tag manually when ready: git tag -a v{new_version} -m 'Release v{new_version}'")


if __name__ == "__main__":
    main()
