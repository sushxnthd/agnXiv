from pathlib import Path


def test_public_verifier_uses_auto_verify_contract() -> None:
    javascript = Path("site/verify.js").read_text(encoding="utf-8")
    assert '"AUTO_VERIFY"' in javascript
    assert '"AUTO_PLAN"' not in javascript
    assert "public research code may execute" in javascript


def test_all_public_html_pages_have_browser_security_policy() -> None:
    pages = sorted(Path("site").glob("*.html"))
    assert pages
    for page in pages:
        html = page.read_text(encoding="utf-8")
        assert 'name="referrer" content="no-referrer"' in html, page
        assert 'http-equiv="Content-Security-Policy"' in html, page
        assert "default-src 'self'" in html, page
        assert "object-src 'none'" in html, page
        assert "base-uri 'none'" in html, page
        assert "https://api.github.com" in html, page
        assert "upgrade-insecure-requests" in html, page


def test_public_homepage_does_not_publish_stale_test_count() -> None:
    html = Path("site/index.html").read_text(encoding="utf-8")
    assert "78+ core tests" not in html
    assert "signed evidence records" in html
