from research_analyst.models import SymbolMatch
from research_analyst.resolver import resolve_subject

def M(sym, name="", qt="EQUITY", score=1.0):
    return SymbolMatch(symbol=sym, name=name, quote_type=qt, score=score)

def test_explicit_suffix_resolves_without_search():
    r = resolve_subject("reliance.ns", [])
    assert r.status == "resolved" and r.resolved.symbol == "RELIANCE.NS"
    assert r.resolved.market == "IN" and r.resolved.currency == "INR"

def test_exact_symbol_resolves():
    r = resolve_subject("AAPL", [M("AAPL","Apple Inc.",score=10), M("APLE","Apple Hospitality REIT",score=1)])
    assert r.status == "resolved" and r.resolved.symbol == "AAPL"

def test_exact_name_resolves():
    r = resolve_subject("Microsoft Corporation",
                        [M("MSFT","Microsoft Corporation",score=9), M("MSF.DE","Microsoft XETRA",score=3)])
    assert r.status == "resolved" and r.resolved.symbol == "MSFT"

def test_sole_match_resolves():
    r = resolve_subject("someco", [M("SMC","Some Company PLC",score=5)])
    assert r.status == "resolved" and r.resolved.symbol == "SMC"

def test_dominant_resolves():
    r = resolve_subject("microsoft", [M("MSFT","Microsoft Corporation",score=20), M("XYZ","Micro Systems",score=1)])
    assert r.status == "resolved" and r.resolved.symbol == "MSFT"

def test_cross_exchange_is_ambiguous():
    r = resolve_subject("reliance industries",
                        [M("RELIANCE.NS","Reliance Industries Limited",score=8),
                         M("RELIANCE.BO","Reliance Industries Limited",score=7)])
    assert r.status == "ambiguous"
    assert {c.symbol for c in r.candidates} == {"RELIANCE.NS","RELIANCE.BO"}

def test_non_equity_filtered_to_not_found():
    r = resolve_subject("usd", [M("USDINR=X","US Dollar / Rupee",qt="CURRENCY",score=5)])
    assert r.status == "not_found"

def test_no_matches_not_found():
    r = resolve_subject("zzzznotacompany", [])
    assert r.status == "not_found"

def test_etf_eligible():
    r = resolve_subject("INDA", [M("INDA","iShares MSCI India ETF",qt="ETF",score=9)])
    assert r.status == "resolved" and r.resolved.symbol == "INDA"
