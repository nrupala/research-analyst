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

"""Writable matplotlib config directory, resolved before matplotlib is imported.

matplotlib resolves its config directory exactly once, at import time, from
``MPLCONFIGDIR`` and otherwise from ``$XDG_CONFIG_HOME/matplotlib`` and then
``~/.config/matplotlib``. When RA runs as the ``--no-create-home`` system user
``ra`` that last fallback cannot be created, so every service start logged::

    mkdir -p failed for path /home/ra/.config/matplotlib: [Errno 13] Permission denied
    Matplotlib created a temporary cache directory in /tmp/matplotlib-XXXX

and matplotlib silently relocated to a throwaway temp directory, discarding its
font cache on every boot.

This module is imported from ``research_analyst/__init__.py`` — the package
initialiser runs before *any* submodule, which is what makes the ordering
guarantee hold. Configuring it from inside ``reports/svg_charts.py`` instead
would only work while nothing else imported matplotlib first, which is a
fragile invariant to rely on.
"""
# Module: research_analyst/mpl_config.py | Version: 1.0 | Updated: 2026-09-27

from __future__ import annotations

import os
import tempfile
from pathlib import Path

#: Environment variable matplotlib itself reads, and the only supported override.
ENV_VAR = "MPLCONFIGDIR"


def _is_writable_dir(path: Path) -> bool:
    """True when *path* is an existing directory this process can write to."""
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".ra-write-probe"
        probe.touch()
        probe.unlink()
    except OSError:
        return False
    return path.is_dir()


def _candidates() -> list[Path]:
    """Ordered fallback locations, most preferred first.

    The primary candidate is derived from ``RA_MARKET_CACHE_DIR`` so that the
    path matches the systemd deployment (``/var/lib/research-analyst/mpl``) and
    stays inside the unit's ``ReadWritePaths`` hardening. A per-user temp
    directory is the last resort for read-only or otherwise constrained hosts.
    """
    candidates: list[Path] = []
    try:
        from .config import settings

        candidates.append(settings.market.cache_dir.parent / "mpl")
    except Exception:  # noqa: BLE001 - never block import on config problems
        pass
    # getuid() is POSIX-only; getpid() keeps the name unique on Windows.
    unique = getattr(os, "getuid", os.getpid)()
    candidates.append(Path(tempfile.gettempdir()) / f"ra-mpl-{unique}")
    return candidates


def configure_mpl_cache_dir() -> str | None:
    """Ensure ``MPLCONFIGDIR`` points at a writable directory.

    Resolution order — an operator's explicit choice always wins:

      1. ``MPLCONFIGDIR`` already set: respect it verbatim.
      2. The first writable candidate from :func:`_candidates`.
      3. Otherwise leave the environment alone; matplotlib keeps its own
         temp-dir fallback rather than failing the import.

    Returns the selected directory, or ``None`` when nothing writable was found.
    """
    existing = os.environ.get(ENV_VAR)
    if existing:
        return existing

    for candidate in _candidates():
        if _is_writable_dir(candidate):
            os.environ[ENV_VAR] = str(candidate)
            return str(candidate)
    return None


MPL_CONFIG_DIR: str | None = configure_mpl_cache_dir()
