import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from fastapi.testclient import TestClient


# ── Supabase stub ─────────────────────────────────────────────────────────────

class _Query:
    """No-op Supabase query chain — every method returns self; execute() is a no-op."""
    def insert(self, *a, **k): return self
    def update(self, *a, **k): return self
    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def or_(self, *a, **k): return self
    def single(self): return self
    def execute(self):
        class _R:
            data = []
        return _R()


class _Supabase:
    def table(self, *a, **k): return _Query()


# ── Fixture ───────────────────────────────────────────────────────────────────

@pytest.fixture
def client(monkeypatch):
    # 1. Stub Supabase on the source module — covers the lazy singleton.
    import utils.supabase_client as sc
    monkeypatch.setattr(sc, "get_supabase", lambda: _Supabase())

    # 2. Stub Supabase on the api module's own imported name — covers all
    #    endpoint calls (Python's `from x import f` creates a second binding).
    import api
    monkeypatch.setattr(api, "get_supabase", lambda: _Supabase())

    # 3. Stub run_graph so background tasks don't boot LangGraph/the LLM in tests.
    #    Returning an error state is the cleanest path — _run_job marks the job
    #    failed via the stubbed Supabase and exits cleanly.
    monkeypatch.setattr(
        api, "run_graph",
        lambda *a, **k: {"error": "test stub — graph not run", "final": True},
    )

    return TestClient(api.app)


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_analyze_rejects_non_audio(client):
    """Non-audio MIME type / extension → 415."""
    resp = client.post(
        "/analyze",
        files={"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert resp.status_code == 415


def test_analyze_accepts_mp3(client):
    """.mp3 upload → 202 + job_id."""
    resp = client.post(
        "/analyze",
        files={"file": ("song.mp3", io.BytesIO(b"\xff\xfb\x00"), "audio/mpeg")},
    )
    assert resp.status_code == 202
    assert "job_id" in resp.json()


def test_analyze_accepts_wav(client):
    """.wav upload → 202 + job_id."""
    resp = client.post(
        "/analyze",
        files={"file": ("loop.wav", io.BytesIO(b"RIFF"), "audio/wav")},
    )
    assert resp.status_code == 202
    assert "job_id" in resp.json()


def test_demo_unknown_track_404(client):
    """Unknown track_id → 404."""
    resp = client.post("/demo", json={"track_id": "not_a_real_track"})
    assert resp.status_code == 404


def test_demo_known_track_202(client):
    """Known demo track → 202 + job_id."""
    resp = client.post("/demo", json={"track_id": "billie_jean_mj"})
    assert resp.status_code == 202
    assert "job_id" in resp.json()


def test_tracks_returns_three(client):
    """GET /tracks returns exactly 3 demo tracks."""
    resp = client.get("/tracks")
    assert resp.status_code == 200
    tracks = resp.json()
    assert len(tracks) == 3
    ids = {t["track_id"] for t in tracks}
    assert ids == {"billie_jean_mj", "humble_kendrick", "blinding_lights_weeknd"}
