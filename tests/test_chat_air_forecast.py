"""Chat: the PM2.5 outlook for Bangkok is one line in the air section, with or without station readings."""
from backend.agents import chat_context as ctx

FORECAST = {"updated_at": 0, "ratio": 1.0, "hours": [], "days": [
    {"date": "2026-10-18", "label": "วันนี้", "mean": 23.4, "max": 35.2, "level": "good", "label_th": "ดี"},
    {"date": "2026-10-19", "label": "พรุ่งนี้", "mean": 61.7, "max": 88.0, "level": "moderate", "label_th": "ปานกลาง"},
    {"date": "2026-10-20", "label": "มะรืนนี้", "mean": 45.0, "max": 60.0, "level": "moderate", "label_th": "ปานกลาง"},
]}
STATIONS = {"avg_pm25": 20, "total": 1, "counts": {"good": 1}, "updated_at": 0,
            "items": [{"name": "สถานี 1", "area": "เขต 1", "province": "กทม.", "pm25": 20, "label": "ดี"}]}


def test_air_context_adds_outlook():
    text = "\n".join(ctx.air_context(STATIONS, "ฝุ่นวันนี้", forecast=FORECAST))
    assert "พรุ่งนี้ เฉลี่ย 62 ปานกลาง" in text
    assert "วันนี้ เฉลี่ย 23 ดี สูงสุด 35" in text
    lines = ctx.air_context(STATIONS, "ฝุ่นวันนี้", forecast=FORECAST)
    assert lines[1].startswith("ฝุ่นคาดการณ์ กทม. (ค่าประมาณ)")


def test_air_context_outlook_without_stations():
    lines = ctx.air_context({"items": []}, "ฝุ่นวันนี้", forecast=FORECAST)
    assert len(lines) == 1
    assert lines[0].startswith("ฝุ่นคาดการณ์ กทม. (ค่าประมาณ)")


def test_air_context_without_outlook_unchanged():
    assert ctx.air_context(STATIONS, "ฝุ่นวันนี้", forecast=None) == ctx.air_context(STATIONS, "ฝุ่นวันนี้")
    assert ctx.air_context({"items": []}, "ฝุ่น", forecast=None) == []


def test_offline_air_reply_has_outlook(monkeypatch):
    from backend.agents import chat_offline as offline
    reply = offline.rule_based_reply(None, "ฝุ่นวันนี้เป็นยังไง", None, {"air": {"items": []}, "air_forecast": FORECAST})
    assert "พรุ่งนี้" in reply
