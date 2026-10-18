"""Deterministic recipe extraction and token reduction tests."""

from webtoolbox.extract import compact_text, extract_fields, approx_tokens, read_recipe


HTML = '''<html><head><title>Example</title></head><body><main><h1>Contact our team</h1>
<a href="mailto:hello@example.org?subject=Job">Apply</a>
<a href="mailto:hello@example.org">Same address</a>
<a href="/careers">Our jobs</a><p>Remote Python developer</p></main></body></html>'''


def test_structured_extraction():
    # A recipe can be passed as an object without a config file or LLM.
    recipe = {"scope": "main", "fields": {
        "emails": {"selector": "a[href^='mailto:']", "attribute": "href", "pattern": r"^mailto:([^?]+)", "all": True},
        "link": {"selector": "a[href='/careers']", "attribute": "href", "absolute_url": True},
        "title": {"selector": "h1"},
    }}
    result = extract_fields(HTML, read_recipe(recipe), "https://example.org/jobs")
    assert result == {"emails": ["hello@example.org"], "link": "https://example.org/careers", "title": "Contact our team"}


def test_relevance_truncation():
    result = compact_text("Navigation\nPricing\nPython developer role\nNavigation\nRemote work", "Python developer", 38)
    assert result.startswith("Python developer role")
    assert approx_tokens("a" * 11) == 3
