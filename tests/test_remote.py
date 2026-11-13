import os, sys, time, types
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import nab_remote


class FakeTG:
    TG_API = "x"
    _SSL_CTX = None
    def __init__(s): s.sent = []
    def _tg_send(s, t, chat_id=None): s.sent.append((chat_id, t))
    def _tg_error_detail(s, e): return str(e)


def test_sign_headers_and_decision(monkeypatch):
    monkeypatch.setattr(nab_remote.nab_secrets, "get", lambda k: "k3y" if k == "sign_key" else "")
    h = nab_remote.sign_headers("PC1")
    assert len(h["X-NAB-Sig"]) == 64 and abs(int(h["X-NAB-Ts"]) - time.time()) < 5
    monkeypatch.setattr(nab_remote, "cloud_url", lambda: "")
    assert nab_remote.get_decision("r", "PC1") is None and not nab_remote.available()


def test_live_events_and_zoom(monkeypatch):
    tg = FakeTG()
    lv = nab_remote.Live(tg, "PC1")
    lv.send_event("z_tl"); assert lv.zoom == "tl"
    lv.send_event("faster"); assert lv.every == 2.0
    lv.send_event("faster"); lv.send_event("faster"); assert lv.every == 1.5       # floor
    lv.send_event("slower"); assert lv.every == 3.5
    lv.send_event("z_bogus"); assert lv.zoom == "tl"                               # unknown zoom ignored
    lv.on = True; lv.chat = "42"
    lv.send_event("stop"); assert not lv.on and tg.sent and tg.sent[0][0] == "42"
    assert "nabL|PC1|stop" in lv.keyboard()


def test_frame_crop(monkeypatch):
    from PIL import Image
    import PIL.ImageGrab as G
    monkeypatch.setattr(G, "grab", lambda: Image.new("RGB", (2000, 1000), (9, 9, 9)))
    lv = nab_remote.Live(FakeTG(), "PC1")
    full = lv._frame(); lv.zoom = "tl"; tl = lv._frame()
    assert full[:2] == b"\xff\xd8" and tl[:2] == b"\xff\xd8"
    im = Image.open(__import__("io").BytesIO(tl)); assert im.size == (1000, 500)


def test_approval_uses_relay(monkeypatch):
    try:
        import tkinter  # noqa
    except ImportError:                                  # the Linux CI box has no Tk; the Windows build does
        tk = types.ModuleType("tkinter"); tk.messagebox = types.ModuleType("tkinter.messagebox"); tk.messagebox.__getattr__ = lambda n: (lambda *a, **k: None)
        st = types.ModuleType("surgical_tools"); st.SurgicalWorkspace = object; sys.modules.setdefault("surgical_tools", st)
        sys.modules["tkinter"] = tk; sys.modules["tkinter.messagebox"] = tk.messagebox
    import nab_auth
    TA = nab_auth.TelegramAuth
    sent = []
    monkeypatch.setattr(nab_remote, "available", lambda: True)
    monkeypatch.setattr(nab_remote, "get_decision", lambda rid, pc: ("allow2", "Ana"))
    monkeypatch.setattr(nab_auth, "_tg_send_callback_buttons", lambda text, buttons, chat_id=None: sent.append(buttons) or 7)
    monkeypatch.setattr(nab_auth, "_tg_edit_message", lambda *a, **k: None)
    monkeypatch.setattr(nab_auth, "_tg_send", lambda *a, **k: None)
    monkeypatch.setattr(nab_auth, "_log_access_attempt", lambda *a, **k: None)
    monkeypatch.setattr(nab_auth, "_load_blocked_pcs", lambda: {})
    monkeypatch.setattr(nab_auth, "ALLOWED_HOURS", None)
    monkeypatch.setattr(time, "sleep", lambda s: None)
    assert TA.request_access(mode="group") is True
    assert all(b[1].startswith("nabA|") for b in sent[0])                          # request id in every button, no PC name
    assert TA._access_deadline and TA._access_deadline > time.time()               # "2 Hours" answer applied
