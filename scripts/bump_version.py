# Copyright (C) 2026 Nrupal Akolkar <nrupalakolkar@gmail.com>
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#
# A separate commercial license is available for uses incompatible with
# the AGPL-3.0. See COMMERCIAL-LICENSE.md.

#!/usr/bin/env python3
"""Version bump utility for Research Analyst.

Usage:
    python scripts/bump_version.py patch   # 0.1.0 -> 0.1.1
    python scripts/bump_version.py minor   # 0.1.0 -> 0.2.0
    python scripts/bump_version.py major   # 0.1.0 -> 1.0.0

Updates version in:
  - pyproject.toml
  - research_analyst/__init__.py
  - ui/manifest.json
  - All Python file version headers
  - CHANGELOG.md (adds Unreleased section)

Designed to be run before git tag + push.
"""

from __future__ import annotations

import os
import re
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INIT_FILE = PROJECT_ROOT / "research_analyst" / "__init__.py"
PYPROJECT = PROJECT_ROOT / "pyproject.toml"
MANIFEST = PROJECT_ROOT / "ui" / "manifest.json"
CHANGELOG = PROJECT_ROOT / "CHANGELOG.md"

VERSION_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)")
FILE_VERSION_RE = re.compile(r"# Module: .+ \| Version: [\d.]+ \| Updated: [\d-]+")


def read_current_version() -> str:
    """Read current version from __init__.py."""
    content = INIT_FILE.read_text()
    match = re.search(r'__version__\s*=\s*"([^"]+)"', content)
    if not match:
        raise RuntimeError("Cannot find __version__ in __init__.py")
    return match.group(1)


def bump(current: str, part: str) -> str:
    """Compute next version."""
    m = VERSION_RE.match(current)
    if not m:
        raise ValueError(f"Invalid version: {current}")
    major, minor, patch = int(m.group(1)), int(m.group(2)), int(m.group(3))

    if part == "major":
        return f"{major + 1}.0.0"
    elif part == "minor":
        return f"{major}.{minor + 1}.0"
    elif part == "patch":
        return f"{major}.{minor}.{patch + 1}"
    else:
        raise ValueError(f"Invalid part: {part}. Use major/minor/patch.")


def update_init(new_version: str) -> None:
    content = INIT_FILE.read_text()
    content = re.sub(r'__version__\s*=\s*"[^"]+"', f'__version__ = "{new_version}"', content)
    INIT_FILE.write_text(content)


def update_pyproject(new_version: str) -> None:
    content = PYPROJECT.read_text()
    content = re.sub(r'version\s*=\s*"[^"]+"', f'version = "{new_version}"', content, count=1)
    PYPROJECT.write_text(content)


def update_manifest(new_version: str) -> None:
    if MANIFEST.exists():
        import json
        data = json.loads(MANIFEST.read_text())
        data["version"] = new_version
        MANIFEST.write_text(json.dumps(data, indent=4) + "\n")


def update_file_headers(new_version: str) -> int:
    """Update version headers in all Python files. Returns count updated."""
    today = date.today().isoformat()
    count = 0
    for root, _, files in os.walk(PROJECT_ROOT):
        # Skip hidden dirs, venv, node_modules
        if any(skip in root for skip in [".git", ".venv", "venv", "node_modules", "__pycache__"]):
            continue
        for f in files:
            if not f.endswith(".py"):
                continue
            path = Path(root) / f
            content = path.read_text()
            if FILE_VERSION_RE.search(content):
                rel = path.relative_to(PROJECT_ROOT)
                new_header = f"# Module: {rel} | Version: {new_version} | Updated: {today}"
                content = FILE_VERSION_RE.sub(new_header, content)
                path.write_text(content)
                count += 1
    return count


def update_changelog(old_version: str, new_version: str) -> None:
    """Insert new version section in CHANGELOG."""
    if not CHANGELOG.exists():
        return
    content = CHANGELOG.read_text()
    today = date.today().isoformat()
    new_section = f"""## [{new_version}] - {today}

### Changed

- Version bump from {old_version} to {new_version}.

---

"""
    # Insert after the "---" following the header
    marker = "## [Unreleased]"
    if marker in content:
        content = content.replace(marker, f"{marker}\n\n{new_section}")
    else:
        # Insert after first ---
        idx = content.find("---", content.find("---") + 3)
        if idx >= 0:
            content = content[:idx+3] + "\n\n" + new_section + content[idx+3:]

    # Update footer links
    footer_line = f"[{new_version}]: https://github.com/nrupala/research-analyst/releases/tag/v{new_version}"
    unreleased_line = f"[Unreleased]: https://github.com/nrupala/research-analyst/compare/v{new_version}...HEAD"

    # Replace old unreleased link
    content = re.sub(
        r"\[Unreleased\]: .+",
        unreleased_line,
        content,
    )
    # Add new version link before unreleased
    if f"[{new_version}]:" not in content:
        content = content.rstrip() + "\n" + footer_line + "\n"

    CHANGELOG.write_text(content)


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in ("major", "minor", "patch"):
        print("Usage: python scripts/bump_version.py [major|minor|patch]")
        sys.exit(1)

    part = sys.argv[1]
    old = read_current_version()
    new = bump(old, part)

    print(f"Bumping version: {old} -> {new}")

    update_init(new)
    print("  Updated: research_analyst/__init__.py")

    update_pyproject(new)
    print("  Updated: pyproject.toml")

    update_manifest(new)
    print("  Updated: ui/manifest.json")

    n = update_file_headers(new)
    print(f"  Updated: {n} Python file headers")

    update_changelog(old, new)
    print("  Updated: CHANGELOG.md")

    print(f"\nVersion bumped to {new}.")
    print("Next steps:")
    print("  git add -A")
    print(f"  git commit -m \"chore: bump version to {new}\"")
    print(f"  git tag v{new}")
    print("  git push origin main --tags")


if __name__ == "__main__":
    main()
