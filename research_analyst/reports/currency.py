"""Currency symbol + money formatting helpers for report rendering.

Introduced in Slice A.3c (v0.3.0 international-markets work) so report money
values render with the symbol of the security's own currency instead of a
hardcoded US dollar sign. USD resolves to "$", keeping US reports byte-identical.
"""
# Module: research_analyst/reports/currency.py | Version: 0.3.0 | Updated: 2026-08-24

from __future__ import annotations

# ISO 4217 currency code -> display symbol used in rendered reports.
# Codes absent from this map fall back to the upper-cased code plus a space
# (e.g. "SEK 12.30"), so an unknown currency is still unambiguous.
_CURRENCY_SYMBOLS: dict[str, str] = {
    "USD": "$",
    "CAD": "$",
    "AUD": "$",
    "HKD": "$",
    "SGD": "$",
    "EUR": "\u20ac",   # €
    "GBP": "\u00a3",   # £
    "INR": "\u20b9",   # ₹
    "JPY": "\u00a5",   # ¥
    "CNY": "\u00a5",   # ¥
    "CHF": "CHF ",
}


def currency_symbol(code: str | None) -> str:
    """Return the display symbol for an ISO 4217 currency ``code``.

    USD/CAD/AUD/HKD/SGD -> "$"; EUR -> "€"; GBP -> "£"; INR -> "₹";
    JPY/CNY -> "¥"; CHF -> "CHF " (trailing space). An unrecognised, non-empty
    code returns the upper-cased code plus a space (e.g. "SEK "). A falsy code
    (None/"") defaults to "$" to preserve legacy US-dollar behaviour.
    """
    if not code:
        return "$"
    key = code.strip().upper()
    if not key:
        return "$"
    return _CURRENCY_SYMBOLS.get(key, f"{key} ")


def money(value: float, code: str | None = "USD", decimals: int = 2) -> str:
    """Format ``value`` as money in the currency named by ``code``.

    Equivalent to ``f"{currency_symbol(code)}{value:.{decimals}f}"``. With the
    default USD this yields e.g. "$12.34" — byte-identical to the previous
    hardcoded formatting.
    """
    return f"{currency_symbol(code)}{value:.{decimals}f}"
