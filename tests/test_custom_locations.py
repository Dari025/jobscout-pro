from job_scout.workspace import parse_custom_locations


def test_custom_locations_preserve_commas_and_split_lines():
    assert parse_custom_locations("Bilbao, Spain\nRemote, UK\nSan Francisco, CA, USA") == [
        "Bilbao, Spain", "Remote, UK", "San Francisco, CA, USA"
    ]


def test_custom_locations_deduplicate_and_reject_urls():
    assert parse_custom_locations("Madrid, Spain; madrid, spain; https://example.com; Remote, Europe") == [
        "Madrid, Spain", "Remote, Europe"
    ]


def test_custom_locations_are_bounded():
    assert len(parse_custom_locations("\n".join(f"City {i}" for i in range(20)))) == 8
