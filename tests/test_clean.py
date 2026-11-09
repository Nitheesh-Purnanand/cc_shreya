import json

from clean import clean, reject_reason

from worker import build_prompt, shard


def rec(id_, text, reply):
    return {"id": id_, "text": text, "teacher_raw": reply if isinstance(reply, str) else json.dumps(reply)}


GOOD = {"intent": "weather_query", "date": None, "time": None, "place": "london"}


def test_reject_reasons():
    assert reject_reason(rec("C1", "weather in london", "not json")) == "a"
    assert reject_reason(rec("C1", "weather in london", {**GOOD, "extra": 1})) == "b"
    assert reject_reason(rec("C1", "weather in london", [1, 2])) == "b"
    assert reject_reason(rec("C1", "weather in london", {**GOOD, "intent": "music_play"})) == "c"
    assert reject_reason(rec("C1", "weather in london", {**GOOD, "place": "paris"})) == "d"
    assert reject_reason(rec("C1", "weather in london", {**GOOD, "place": 5})) == "d"
    assert reject_reason(rec("C1", "Weather in London", GOOD)) is None  # case-insensitive match


def test_clean_dedup_keeps_smallest_id_and_counts_add_up():
    records = [
        rec("C0003", "weather in london", GOOD),
        rec("C0001", "Weather in London ", GOOD),  # duplicate text, smaller id
        rec("C0002", "weather in london", "oops"),
    ]
    kept, counts = clean(records)
    assert [r["id"] for r in kept] == ["C0001"]
    assert counts == {"input": 3, "a": 1, "b": 0, "c": 0, "d": 0, "duplicates": 1, "kept": 1}


def test_shards_cover_every_line_exactly_once():
    lines = list(range(3000))
    parts = [shard(lines, i, 2) for i in range(2)]
    assert sorted(parts[0] + parts[1]) == lines
    assert parts[0][:3] == [0, 2, 4] and parts[1][:3] == [1, 3, 5]


def test_build_prompt_placeholder():
    assert build_prompt("A {command} B", "hi") == "A hi B"
    assert build_prompt("A", "hi").endswith("Command: hi\nJSON:")
