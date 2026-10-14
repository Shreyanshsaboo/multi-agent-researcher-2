from app.evidence import EvidenceStore, check_citations, closest_url, normalize_url


def test_normalize_url_ignores_tracking_case_and_trailing_slash():
    a = normalize_url("https://WWW.Example.com/post/?utm_source=hn&id=7#comments")
    b = normalize_url("https://example.com/post?id=7")
    assert a == b


def test_normalize_url_keeps_meaningful_query():
    assert normalize_url("https://news.ycombinator.com/item?id=1") != normalize_url(
        "https://news.ycombinator.com/item?id=2"
    )


def test_add_assigns_sequential_ids():
    store = EvidenceStore()
    first, created1 = store.add(url="https://a.com/1", title="A", source_type="web",
                                agent="web_researcher", key_points=["x"])
    second, created2 = store.add(url="https://b.com/2", title="B", source_type="hackernews",
                                 agent="hn_scout", key_points=["y"])
    assert (first.id, second.id) == ("E1", "E2")
    assert created1 and created2
    assert len(store) == 2


def test_same_url_from_another_agent_merges_instead_of_duplicating():
    store = EvidenceStore()
    store.add(url="https://a.com/post", title="Post", source_type="hackernews",
              agent="hn_scout", key_points=["120 points on HN"])
    merged, created = store.add(url="https://www.a.com/post/", title="Post (full)",
                                source_type="article", agent="article_reader",
                                key_points=["Cost fell 40%", "120 points on HN"],
                                full_text_read=True)
    assert not created
    assert merged.id == "E1"
    assert merged.found_by == ["hn_scout", "article_reader"]
    assert merged.key_points == ["120 points on HN", "Cost fell 40%"]
    assert merged.full_text_read
    assert len(store) == 1


def test_render_index_flags_full_text_and_finders():
    store = EvidenceStore()
    store.add(url="https://a.com/1", title="A story", source_type="article",
              agent="article_reader", key_points=["p"], full_text_read=True)
    line = store.render_index()
    assert "[E1] A story" in line
    assert "full text read" in line
    assert "by article_reader" in line


def test_check_citations_flags_unknown_ids_and_uncited_paragraphs():
    store = EvidenceStore()
    store.add(url="https://a.com/1", title="A", source_type="web", agent="web_researcher",
              key_points=["p"])
    long_uncited = "This paragraph makes a substantive claim about inference prices " * 3
    markdown = (
        "# Title\n\n"
        "Prices fell sharply last year [E1], and again this year [E9].\n\n"
        f"{long_uncited}\n\n"
        "## Open questions\n\nNobody knows what happens next and this section is allowed "
        "to have no citations because it lists limitations of the research."
    )
    check = check_citations(markdown, store)
    assert check.cited_ids == ["E1", "E9"]
    assert check.unknown_ids == ["E9"]
    assert len(check.uncited_paragraphs) == 1
    assert check.evidence_total == 1


def test_closest_url_forgives_a_mis_copied_long_url_but_never_guesses_between_short_ones():
    real = ("https://www.manilatimes.net/2026/10/08/tmt-newswire/pr-newswire/hong-kongs-m-mark-esports-"
            "event-returns-sellout-blast-premier-rivals-confirmed-for-second-year-following-historic-"
            "debut/2442043")
    known = {normalize_url(real), normalize_url("https://variety.com/2026/sports/news/ipl")}
    assert closest_url(real.replace("esports-event-returns", "esports-returns"), known) == normalize_url(real)
    assert closest_url("https://variety.com/2026/sports/news/nba", known) is None
    assert closest_url("https://elsewhere.com/2026/10/08/tmt-newswire", known) is None


def test_tracking_parameters_do_not_create_duplicate_evidence():
    store = EvidenceStore()
    first, created = store.add(
        url="https://example.com/article?id=42&utm_source=newsletter",
        title="Article",
        source_type="web",
        agent="web_researcher",
        key_points=["Original finding"],
    )
    second, created_again = store.add(
        url="https://www.example.com/article/?id=42&fbclid=tracking",
        title="Same article",
        source_type="article",
        agent="article_reader",
        key_points=["Additional finding"],
    )

    assert created
    assert not created_again
    assert first.id == second.id
    assert len(store) == 1
    assert second.found_by == ["web_researcher", "article_reader"]


def test_evidence_key_points_are_limited_and_deduplicated():
    store = EvidenceStore()
    item, _ = store.add(
        url="https://example.com/report",
        title="Report",
        source_type="web",
        agent="web_researcher",
        key_points=["Fact A", "Fact A", "Fact B", "Fact C"],
    )
    store.add(
        url="https://example.com/report",
        title="Report",
        source_type="article",
        agent="article_reader",
        key_points=["Fact D", "Fact E", "Fact F", "Fact G"],
    )

    assert len(item.key_points) <= 6
    assert item.key_points.count("Fact A") == 1


def test_citation_check_deduplicates_repeated_ids():
    store = EvidenceStore()
    store.add(
        url="https://example.com/source",
        title="Source",
        source_type="web",
        agent="web_researcher",
        key_points=["Verified fact"],
    )

    result = check_citations(
        "First claim [E1]. Second claim [E1]. Unknown [E9]. Again [E9].",
        store,
    )

    assert result.cited_ids == ["E1", "E9"]
    assert result.unknown_ids == ["E9"]


def test_find_by_url_accepts_normalized_variants():
    store = EvidenceStore()
    item, _ = store.add(
        url="https://www.example.com/story/?id=7&utm_medium=email",
        title="Story",
        source_type="web",
        agent="web_researcher",
        key_points=["Finding"],
    )

    assert store.find_by_url("https://example.com/story?id=7") is item
    assert store.find_by_url("https://example.com/story?id=8") is None


def test_empty_evidence_renders_placeholder():
    store = EvidenceStore()

    assert store.render_index() == "(empty)"
    assert store.render_full() == "(empty)"
