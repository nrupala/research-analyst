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

"""Research Analyst — Institutional-grade equity and ETF research agent."""
# Module: research_analyst/__init__.py | Version: 0.4.0 | Updated: 2026-09-27

__version__ = "0.4.0"

# matplotlib resolves its config directory once, at import time. On hosts where
# $HOME is not writable (the systemd `ra` user is created with --no-create-home)
# it cannot build ~/.config/matplotlib and silently relocates to a fresh temp
# directory on every start, discarding the font cache. Configure it here, in the
# package initialiser, so it is set before any submodule — and therefore before
# any matplotlib import — can run.
from .mpl_config import MPL_CONFIG_DIR  # noqa: E402

__all__ = ["MPL_CONFIG_DIR", "__version__"]
