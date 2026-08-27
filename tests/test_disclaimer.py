import pytest
from research_analyst.disclaimer import DISCLAIMER_SHORT, DISCLAIMER_FULL, DISCLAIMER_VERSION, render_footer

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