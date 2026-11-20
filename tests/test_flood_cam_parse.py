"""_parse: the JSON in a flood-watch reply, including the bare tile list a small local model sends."""
from backend.vision.flood_cam_service import _parse


def test_object_reply():
    assert _parse('{"level": "none", "confidence": 0.9}') == {"level": "none", "confidence": 0.9}


def test_object_in_code_fence():
    assert _parse('```json\n{"tiles": [{"tile": 1, "level": "none"}]}\n```') == {"tiles": [{"tile": 1, "level": "none"}]}


def test_bare_tile_list_becomes_tiles():
    text = '```json\n[\n  {"tile": 1, "level": "none", "confidence": 0.9},\n  {"tile": 2, "level": "puddle", "confidence": 0.6}\n]\n```'
    assert _parse(text) == {"tiles": [{"tile": 1, "level": "none", "confidence": 0.9},
                                      {"tile": 2, "level": "puddle", "confidence": 0.6}]}


def test_object_holding_a_list_stays_object():
    assert _parse('{"tiles": [{"tile": 1, "level": "none"}]}') == {"tiles": [{"tile": 1, "level": "none"}]}


def test_no_json():
    assert _parse("no answer") == {}
