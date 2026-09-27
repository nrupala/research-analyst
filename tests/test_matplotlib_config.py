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

"""matplotlib config-dir resolution must never depend on a writable $HOME.

Regression: on the Oracle Aetheris box RA runs as the ``--no-create-home``
system user ``ra``, so ``~/.config/matplotlib`` cannot be created. matplotlib
resolved its config dir at import time, logged ``mkdir -p failed for path
/home/ra/.config/matplotlib``, and silently relocated to a throwaway /tmp
directory on every service start — discarding the font cache each boot.

These tests pin the fix: MPLCONFIGDIR is chosen *before* ``import matplotlib``
and always points at a writable directory, in every launch mode.
"""
# Module: tests/test_matplotlib_config.py | Version: 1.0 | Updated: 2026-09-27

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from research_analyst.mpl_config import configure_mpl_cache_dir

REPO_ROOT = Path(__file__).resolve().parent.parent
SERVICE_UNIT = REPO_ROOT / "deploy" / "oci-native" / "ra.service"
BOOTSTRAP = REPO_ROOT / "deploy" / "oci-native" / "bootstrap.sh"


def _is_writable_dir(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".test-probe"
        probe.touch()
        probe.unlink()
    except OSError:
        return False
    return path.is_dir()


# ---------------------------------------------------------------------------
# Selection logic
# ---------------------------------------------------------------------------


def test_respects_preexisting_mplconfigdir(monkeypatch, tmp_path):
    """An operator's explicit MPLCONFIGDIR always wins, verbatim."""
    chosen = tmp_path / "operator-chosen"
    chosen.mkdir()
    monkeypatch.setenv("MPLCONFIGDIR", str(chosen))

    result = configure_mpl_cache_dir()

    assert result == str(chosen)
    assert os.environ["MPLCONFIGDIR"] == str(chosen)


def test_selects_writable_dir_when_unset(monkeypatch, tmp_path):
    """With no MPLCONFIGDIR, a writable directory is chosen and exported."""
    monkeypatch.delenv("MPLCONFIGDIR", raising=False)
    monkeypatch.setenv("RA_MARKET_CACHE_DIR", str(tmp_path / "cache"))

    result = configure_mpl_cache_dir()

    assert result is not None, "no writable matplotlib config dir could be selected"
    selected = Path(result)
    assert selected.is_dir()
    assert _is_writable_dir(selected)
    assert os.environ["MPLCONFIGDIR"] == str(selected)


def test_selected_dir_survives_a_cache_dir_that_cannot_be_created(monkeypatch, tmp_path):
    """An unwritable primary candidate must not break the import path."""
    monkeypatch.delenv("MPLCONFIGDIR", raising=False)
    # Point the primary candidate at a path that cannot be created: a regular
    # file used as a parent directory. mkdir() then fails with NotADirectoryError.
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory")
    monkeypatch.setenv("RA_MARKET_CACHE_DIR", str(blocker / "cache"))

    result = configure_mpl_cache_dir()

    assert result is not None
    assert _is_writable_dir(Path(result))


# ---------------------------------------------------------------------------
# Import-time resolution — the actual regression
# ---------------------------------------------------------------------------


def _probe_configdir(
    env_overrides: dict[str, str], home: Path, entrypoint: str
) -> subprocess.CompletedProcess[str]:
    """Import *entrypoint* in a clean interpreter and report matplotlib's configdir.

    Mirrors the real launch order: the process entrypoint is
    ``research_analyst.server:app``, so ``research_analyst/__init__.py`` runs
    before anything can import matplotlib.
    """
    env = dict(os.environ)
    env.pop("MPLCONFIGDIR", None)
    env.pop("XDG_CONFIG_HOME", None)
    env["HOME"] = str(home)
    env["PYTHONPATH"] = str(REPO_ROOT)
    env.update(env_overrides)
    script = (
        f"import {entrypoint}, matplotlib;"
        "print('CONFIGDIR=' + matplotlib.get_configdir());"
        "print('SELECTED=' + str(research_analyst.MPL_CONFIG_DIR))"
    )
    return subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )


def _field(output: str, key: str) -> str:
    for line in output.splitlines():
        if line.startswith(key):
            return line.split("=", 1)[1]
    raise AssertionError(f"{key} missing from interpreter output:\n{output}")


def test_matplotlib_resolves_our_dir_at_import_time(tmp_path):
    """matplotlib.get_configdir() must equal the dir we selected before import."""
    proc = _probe_configdir({}, home=tmp_path / "home", entrypoint="research_analyst")
    assert proc.returncode == 0, f"interpreter failed:\n{proc.stdout}\n{proc.stderr}"

    configdir = _field(proc.stdout, "CONFIGDIR=")
    selected = _field(proc.stdout, "SELECTED=")

    assert selected, "the package initialiser did not select a matplotlib config dir"
    assert configdir == selected, (
        f"matplotlib resolved {configdir!r} but the initialiser selected {selected!r}; "
        "MPLCONFIGDIR was not set before the import"
    )
    assert _is_writable_dir(Path(configdir))


def test_deep_submodule_import_also_configures_matplotlib(tmp_path):
    """The guarantee must hold for any submodule, not just the top-level package.

    This is the regression that made the first attempt wrong: configuring from
    inside ``reports/svg_charts.py`` only works while nothing else imports
    matplotlib first. Configuring from ``__init__.py`` holds for every import
    path into the package.
    """
    proc = _probe_configdir(
        {},
        home=tmp_path / "home",
        entrypoint="research_analyst.reports.svg_charts",
    )
    assert proc.returncode == 0, f"interpreter failed:\n{proc.stdout}\n{proc.stderr}"
    assert _field(proc.stdout, "CONFIGDIR=") == _field(proc.stdout, "SELECTED=")


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission semantics")
def test_unwritable_home_does_not_trigger_matplotlib_relocation(tmp_path):
    """Reproduce the box: a --no-create-home user with an unwritable $HOME.

    Before the fix this printed "mkdir -p failed for path .../matplotlib" and
    relocated to /tmp. Now $HOME is never consulted.
    """
    readonly = tmp_path / "readonly-home"
    readonly.mkdir()
    readonly.chmod(0o500)  # read+execute only: no mkdir, no writes
    try:
        proc = _probe_configdir({}, home=readonly, entrypoint="research_analyst")
        assert proc.returncode == 0, f"interpreter failed:\n{proc.stdout}\n{proc.stderr}"
        assert "mkdir -p failed" not in proc.stderr, (
            "matplotlib still tried to build its config dir under $HOME:\n" + proc.stderr
        )
        configdir = _field(proc.stdout, "CONFIGDIR=")
        assert Path(configdir) != readonly, "matplotlib fell back to the unwritable $HOME"
        assert _is_writable_dir(Path(configdir))
    finally:
        readonly.chmod(0o700)


# ---------------------------------------------------------------------------
# Deployment artifacts stay in sync with the code
# ---------------------------------------------------------------------------


def _unit_env_value(unit: str, name: str) -> str | None:
    """Return the value of ``Environment=NAME=VALUE`` in a systemd unit.

    Parses the full directive rather than a substring so that an unrelated
    ``Environment=`` line cannot be mistaken for the one under test.
    """
    prefix = "Environment="
    for line in unit.splitlines():
        stripped = line.strip()
        if not stripped.startswith(prefix):
            continue
        for assignment in stripped[len(prefix):].split():
            key, _, value = assignment.partition("=")
            if key == name:
                return value
    return None


def test_service_unit_sets_mplconfigdir_under_readwritepaths():
    """The unit must set MPLCONFIGDIR inside its own hardening allowlist."""
    unit = SERVICE_UNIT.read_text(encoding="utf-8")

    mpl_dir = _unit_env_value(unit, "MPLCONFIGDIR")
    assert mpl_dir, "ra.service must set MPLCONFIGDIR for the no-create-home user"
    assert mpl_dir.startswith("/"), f"expected an absolute path, got {mpl_dir!r}"

    prefix = "ReadWritePaths="
    allowed = [
        stripped[len(prefix):]
        for stripped in (line.strip() for line in unit.splitlines())
        if stripped.startswith(prefix)
    ]
    assert allowed, "ra.service must declare ReadWritePaths for ProtectSystem=strict"
    assert any(
        mpl_dir == rw.rstrip("/") or mpl_dir.startswith(rw.rstrip("/") + "/") for rw in allowed
    ), f"{mpl_dir} is not covered by ReadWritePaths={allowed}; ProtectSystem=strict would deny it"


def test_bootstrap_creates_the_mpl_cache_dir():
    """bootstrap.sh must pre-create the dir the unit points at, owned by ra."""
    body = BOOTSTRAP.read_text(encoding="utf-8")

    assert "/var/lib/research-analyst/mpl" in body, (
        "bootstrap.sh must create /var/lib/research-analyst/mpl; "
        "otherwise a fresh box starts with no writable matplotlib cache"
    )
    assert "chown" in body, "the mpl cache dir must be chowned to ra"
