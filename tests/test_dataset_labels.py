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

"""Dataset declaration labels name the service, never the library.

Follow-up to the PR #121 price-declaration fix (release-gate follow-up,
recorded 2026-10-15): the non-price Data Sources entries said
"yfinance (company profile)" — yfinance is the client library; the
service the data comes from is Yahoo Finance. All declarations now
come from models.DATASET_SOURCE_LABELS, and every one must resolve a
#74 reference link (the canonical "Yahoo Finance" label previously
matched no URL template at all).
"""
# Module: tests/test_dataset_labels.py

from research_analyst.models import DATASET_SOURCE_LABELS
from research_analyst.orchestrator import _price_declaration, _source_records


def test_labels_name_the_service_not_the_library():
    assert DATASET_SOURCE_LABELS, "label map must not be empty"
    for key, label in DATASET_SOURCE_LABELS.items():
        assert "yfinance" not in label, f"{key} still names the library: {label}"
        assert label.startswith("Yahoo Finance ("), label


def test_every_dataset_declaration_resolves_a_source_link():
    for label in DATASET_SOURCE_LABELS.values():
        records = _source_records("AAPL", [label])
        assert records[0].url == "https://finance.yahoo.com/quote/AAPL", label


def test_price_declaration_resolves_a_source_link():
    records = _source_records("AAPL", [_price_declaration("yfinance")])
    assert records[0].name == "Yahoo Finance (price data)"
    assert records[0].url == "https://finance.yahoo.com/quote/AAPL"


def test_legacy_library_label_still_resolves():
    # Pre-rename declarations (cached reports) keep their link via
    # the legacy template marker.
    records = _source_records("AAPL", ["yfinance (company profile)"])
    assert records[0].url == "https://finance.yahoo.com/quote/AAPL"
