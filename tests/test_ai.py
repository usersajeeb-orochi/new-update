import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import nab_ai


def fresh(monkeypatch, tmp_path, **cfg):
    monkeypatch.setattr(nab_ai, "FILE", str(tmp_path / "ai.json"))
    if cfg:
        (tmp_path / "ai.json").write_text(json.dumps(cfg))
    return nab_ai.AI()


def test_retired_groq_models_are_replaced(monkeypatch, tmp_path):
    a = fresh(monkeypatch, tmp_path, text_model="llama-3.3-70b-versatile", fast_model="llama-3.1-8b-instant", vision_model="meta-llama/llama-4-scout-17b-16e-instruct")
    assert a.cfg["text_model"] == "openai/gpt-oss-120b" and a.cfg["fast_model"] == "openai/gpt-oss-20b" and a.cfg["vision_model"] == ""


def test_cloud_answers_first_and_groq_is_not_touched(monkeypatch, tmp_path):
    a = fresh(monkeypatch, tmp_path)
    monkeypatch.setattr(a, "_cloud_on", lambda: True)
    monkeypatch.setattr(a, "_cloud_chat", lambda kind, m, j, mt, t: ("hello", ""))
    monkeypatch.setattr(a, "_request", lambda *x, **k: (_ for _ in ()).throw(AssertionError("groq must not be called")))
    assert a.chat([{"role": "user", "content": "hi"}]) == ("hello", "")
    j, why = a.ask_json("s", "u")
    assert j is None and why                      # 'hello' is not JSON: soft failure, no crash


def test_falls_back_to_groq_when_cloud_fails_and_handles_empty_content(monkeypatch, tmp_path):
    a = fresh(monkeypatch, tmp_path, keys=["gsk_x"])
    monkeypatch.setattr(a, "_cloud_on", lambda: True)
    monkeypatch.setattr(a, "_cloud_chat", lambda *x: (None, "cloud AI: down"))
    seen = {}
    def req(path, body=None, **k):
        seen.update(body)
        return {"choices": [{"message": {"content": None}}]}, ""
    monkeypatch.setattr(a, "_request", req)
    out, why = a.chat([{"role": "user", "content": "hi"}], max_tokens=50)
    assert out is None and seen["reasoning_effort"] == "low" and seen["max_tokens"] >= 400     # gpt-oss: short thinking, room to answer
    monkeypatch.setattr(a, "_request", lambda *x, **k: ({"choices": [{"message": {"content": " ok "}}]}, ""))
    assert a.chat([{"role": "user", "content": "hi"}]) == ("ok", "")


def test_vision_goes_to_cloud_and_big_images_shrink(monkeypatch, tmp_path):
    a = fresh(monkeypatch, tmp_path)
    got = {}
    monkeypatch.setattr(a, "_cloud_on", lambda: True)
    monkeypatch.setattr(a, "_cloud_chat", lambda kind, m, j, mt, t: got.update(kind=kind, size=len(json.dumps(m))) or ("Prothom Alo", ""))
    from PIL import Image
    import io, random
    im = Image.frombytes("RGB", (3000, 2000), bytes(random.getrandbits(8) for _ in range(3000 * 2000 * 3)))
    buf = io.BytesIO(); im.save(buf, "PNG")
    assert len(buf.getvalue()) > 5_000_000
    assert a.vision(buf.getvalue(), "which paper?", "image/png") == ("Prothom Alo", "")
    assert got["kind"] == "vision" and got["size"] < 2_500_000


def test_ready_and_status_know_the_cloud(monkeypatch, tmp_path):
    a = fresh(monkeypatch, tmp_path)
    monkeypatch.setattr(a, "_cloud_on", lambda: True)
    assert a.ready() and a.status()["cloud"] is True
    monkeypatch.setattr(a, "_cloud_on", lambda: False)
    assert not a.ready()
