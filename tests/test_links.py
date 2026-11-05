"""Link classification and negative-control tests."""

from pipeline.verify.links import classify_html, page_title


LONG_BODY = "<html><body><p>" + ("filed financial statement " * 40) + "</p></body></html>"


def test_valid_filing_page_requires_accession_and_content():
    result, reason = classify_html("EDGAR Filing Documents", LONG_BODY, "0000000000-25-000001")
    assert result == "broken"
    assert "accession number not found" in reason

    body = LONG_BODY.replace("</body>", "0000000000-25-000001</body>")
    result, reason = classify_html("EDGAR Filing Documents", body, "0000000000-25-000001")
    assert result == "ok"
    assert reason == ""


def test_soft404_titles_are_rejected():
    for title in ["", "Default", "Page not found", "404", "Access denied"]:
        result, _ = classify_html(title, LONG_BODY)
        assert result == "soft404", title


def test_short_body_is_rejected_even_with_good_title():
    result, reason = classify_html("EDGAR Filing Documents", "<html><body>ok</body></html>")
    assert result == "soft404"
    assert "body too short" in reason


def test_page_title_is_extracted_and_collapsed():
    html = "<html><head><title>  EDGAR   Filing  </title></head></html>"
    assert page_title(html) == "EDGAR Filing"
