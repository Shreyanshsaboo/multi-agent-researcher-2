from app.agents.workers import decide_status, parse_report

REPORT = """STATUS: partial
REPORT: Found two strong HN threads; the web article was paywalled.

FINDING: https://blog.example.com/prices
TITLE: **Inference prices fell 80%**
- Prices fell 80% this year
- 1. Commenters credit open-weight models
FINDING: <https://news.ycombinator.com/item?id=102>
TITLE: Ask HN thread
* Teams cap spend with per-user budgets
FINDING: https://empty.example.com
TITLE: No points here
"""


def test_parse_report_reads_status_summary_and_findings():
    report = parse_report(REPORT)
    assert report.status == "partial"
    assert report.summary.startswith("Found two strong HN threads")
    assert [f.url for f in report.findings] == [
        "https://blog.example.com/prices",
        "https://news.ycombinator.com/item?id=102",
    ]
    first = report.findings[0]
    assert first.title == "Inference prices fell 80%"
    assert first.key_points == ["Prices fell 80% this year", "1. Commenters credit open-weight models"]


def test_parse_report_skips_findings_without_points_and_handles_missing_status():
    report = parse_report("Nothing useful.\nFINDING: https://x.example.com\nTITLE: t\n")
    assert report.status is None
    assert report.findings == []
    assert report.summary == "Nothing useful."


def test_parse_report_accepts_url_on_the_line_after_finding():
    report = parse_report("STATUS: success\nFINDING:\nhttps://a.example.com/x\n- a point\n")
    assert report.findings[0].url == "https://a.example.com/x"


def test_decide_status_never_reports_success_without_evidence():
    assert decide_status("success", saved=0, errors=0) == "failed"
    assert decide_status("partial", saved=2, errors=0) == "partial"
    assert decide_status(None, saved=2, errors=1) == "partial"
    assert decide_status(None, saved=2, errors=0) == "success"
