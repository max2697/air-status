import json

from air_status.providers.aircanada import AirCanada


def _later(raw, seconds_tag, **changes):
    raw = json.loads(json.dumps(raw))
    raw["flightInfo"]["utcTime"] = f"2026-01-15T18:20:{seconds_tag}.000Z"
    raw["flightInfo"].update(changes)
    return raw


def test_saves_changes_only_and_skips_duplicates(tmp_path, gogo_response):
    history = AirCanada().history(tmp_path)
    assert history.save(gogo_response) is True
    assert history.save(gogo_response) is False  # same reading again

    assert history.save(_later(gogo_response, "08", latitude=31.6)) is True

    lines = history.path_for(gogo_response).read_text().splitlines()
    assert len(lines) == 2
    assert set(json.loads(lines[1])) == {"flightInfo.utcTime", "flightInfo.latitude"}


def test_load_round_trip(tmp_path, gogo_response):
    provider = AirCanada()
    history = provider.history(tmp_path)
    later = _later(gogo_response, "08", altitude=30000.0)
    history.save(gogo_response)
    history.save(later)
    assert history.load(history.path_for(gogo_response)) == [provider.parse(gogo_response), provider.parse(later)]
    assert history.track(later)[-1].altitude_ft == 30000.0


def test_no_duplicates_across_two_writers(tmp_path, gogo_response):
    a, b = AirCanada().history(tmp_path), AirCanada().history(tmp_path)  # e.g. two running copies
    assert a.save(gogo_response) is True
    assert b.save(gogo_response) is False
    assert len(a.path_for(gogo_response).read_text().splitlines()) == 1


def test_file_name_and_listing(tmp_path, gogo_response):
    history = AirCanada().history(tmp_path)
    assert history.path_for(gogo_response).name == "2026-01-15_ACA123_AUS-YYZ.jsonl"
    assert history.files() == []
    history.save(gogo_response)
    assert [p.name for p in history.files()] == ["2026-01-15_ACA123_AUS-YYZ.jsonl"]


def test_private_and_noise_fields_not_saved(tmp_path, gogo_response):
    history = AirCanada().history(tmp_path)
    history.save(gogo_response)
    text = history.path_for(gogo_response).read_text()
    for value in ("10.0.0.2", "02:00:00:00:00:01", "device_iid", "trivia"):
        assert value not in text
    assert "systemInfo.flightPhase" in text  # raw Gogo fields are kept


def test_history_file_names_stay_in_folder(tmp_path, gogo_response):
    from air_status.flightlog import safe_part
    from air_status.providers.aircanada import AirCanada

    assert safe_part("../../etc/passwd") == "etcpasswd"
    assert safe_part("..") == "unknown"
    assert safe_part(None) == "unknown"
    f = gogo_response["flightInfo"]
    f["flightNumberInfo"] = "../../evil"
    f["departureAirportCodeIata"] = "/tmp"
    path = AirCanada().history(tmp_path).path_for(gogo_response)
    assert path.parent == tmp_path
    assert path.name == "2026-01-15_evil_tmp-YYZ.jsonl"
