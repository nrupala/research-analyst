# Copyright (C) 2026 2351485 ALBERTA INC.
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

import pytest

from research_analyst.disclaimer import (
    DISCLAIMER_FULL,
    DISCLAIMER_SHORT,
    DISCLAIMER_VERSION,
    render_footer,
)


def test_disclaimer_constants():
    assert DISCLAIMER_SHORT and isinstance(DISCLAIMER_SHORT, str)
    assert DISCLAIMER_FULL and isinstance(DISCLAIMER_FULL, str)
    assert DISCLAIMER_VERSION and isinstance(DISCLAIMER_VERSION, str)

def test_render_footer():
    text = render_footer("text")
    assert "informational purposes only" in text.lower()

    markdown = render_footer("markdown")
    assert "informational purposes only" in markdown.lower()

    html = render_footer("html")
    assert "informational purposes only" in html.lower()

    with pytest.raises(ValueError):
        render_footer("bogus")
