import asyncio
import os
import sys
import traceback
import uuid
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from contextlib import asynccontextmanager

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv(override=True)

from fastapi import BackgroundTasks, FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

try:  # postgrest ships with supabase-py; tolerate a move so a rename can't take the API down
    from postgrest import APIError
except ImportError:  # pragma: no cover
    class APIError(Exception):  # type: ignore[no-redef]
        """Fallback so `except APIError` stays valid — a missing row then reads as 503, not 404."""

from agents.graph import run as run_graph
from utils.supabase_client import get_supabase

# ── Lifespan & Background Tasks ──────────────────────────────────────────────

async def reap_orphan_jobs() -> None:
    """Startup check: Mark processing/pending jobs older than 10 minutes as failed."""
    try:
        sb = get_supabase()
        
        # Find all processing/pending jobs
        res = sb.table("jobs").select("id, status, updated_at, created_at").or_("status.eq.processing,status.eq.pending").execute()
        
        if res.data:
            reaped_count = 0
            for job in res.data:
                # Compare timestamp
                time_str = job.get("updated_at") or job.get("created_at")
                if time_str:
                    try:
                        # Parse ISO timestamp, normalizing Z to +00:00 for compatibility
                        dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
                        if dt < datetime.now(timezone.utc) - timedelta(minutes=10):
                            sb.table("jobs").update({
                                "status": "failed",
                                "error_message": "Job orphaned (process terminated or timed out).",
                                "updated_at": datetime.now(timezone.utc).isoformat()
                            }).eq("id", job["id"]).execute()
                            reaped_count += 1
                    except Exception as parse_err:
                        print(f"[Orphan Reaper] Error parsing timestamp for job {job['id']}: {parse_err}")
            if reaped_count > 0:
                print(f"[Orphan Reaper] Successfully reaped {reaped_count} stuck/orphaned jobs.")
    except Exception as e:
        print(f"[Orphan Reaper] Failed to reap jobs: {e}")


def sweep_expired_outputs(max_age_seconds: int = 3600) -> None:
    """Deletes files in OUTPUT_DIR that are older than max_age_seconds (1 hour)."""
    if not OUTPUT_DIR.exists():
        return
    now = time.time()
    deleted_count = 0
    for file_path in OUTPUT_DIR.glob("*"):
        if file_path.is_file():
            try:
                age = now - file_path.stat().st_mtime
                if age > max_age_seconds:
                    file_path.unlink()
                    deleted_count += 1
            except Exception as e:
                print(f"[Sweeper] Failed to delete file {file_path.name}: {e}")
    if deleted_count > 0:
        print(f"[Sweeper] Deleted {deleted_count} expired files from output directory.")


async def output_sweeper_task() -> None:
    """Periodic background task that sweeps expired outputs every 15 minutes."""
    print("[Sweeper] Output file sweeper background task started.")
    while True:
        try:
            sweep_expired_outputs(max_age_seconds=3600)  # 1 hour expiration
        except Exception as e:
            print(f"[Sweeper task error] {e}")
        await asyncio.sleep(900)  # Sleep for 15 minutes


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup tasks
    await reap_orphan_jobs()
    
    # Start periodic file sweeper if running in production
    is_prod = os.getenv("ENV") == "production" or os.getenv("PRODUCTION", "false").lower() == "true"
    if is_prod:
        asyncio.create_task(output_sweeper_task())
        print("[Lifespan] Production output sweeper task launched.")
    else:
        print("[Lifespan] Running in development mode: periodic file sweeper disabled.")
        
    yield

# ── App Setup ─────────────────────────────────────────────────────────────────

app = FastAPI(title="SoundReverse API", version="2.0.0", lifespan=lifespan)

_cors_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174",
    ).split(",")
    if origin.strip()
]


class CatchUnhandledErrors:
    """Turn unhandled exceptions into a JSON 500 that still carries CORS headers.

    Starlette routes `@app.exception_handler(Exception)` to ServerErrorMiddleware,
    which sits *outside* CORSMiddleware — so its bare `Internal Server Error` reply
    has no Access-Control-Allow-Origin, the browser blocks it, and the frontend only
    ever sees "TypeError: Failed to fetch" with the real cause hidden. Catching here
    (registered before CORSMiddleware, so it nests inside it) lets the response pass
    back out through CORS and reach the caller intact.

    Plain ASGI rather than BaseHTTPMiddleware: it must not interfere with the
    BackgroundTasks that /analyze and /demo depend on.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        response_started = False

        async def _send(message):
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, _send)
        except Exception as exc:
            traceback.print_exc()
            if response_started:
                raise  # headers already flushed — can't rewrite the reply
            await JSONResponse(
                status_code=500,
                content={"detail": f"{type(exc).__name__}: {exc}"},
            )(scope, receive, send)


# Order matters: add_middleware() prepends, so the LAST call is the outermost layer.
# CORS must wrap the catcher, otherwise error responses lose their CORS headers.
app.add_middleware(CatchUnhandledErrors)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", str(Path(__file__).parent / "output")))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/outputs", StaticFiles(directory=str(OUTPUT_DIR)), name="outputs")

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", str(Path(__file__).parent / "tmp")))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

MAX_UPLOAD_BYTES = 50 * 1024 * 1024            # 50 MB
ALLOWED_EXTS = {".mp3", ".wav"}

# ── Health check (Koyeb / load-balancer probe) ────────────────────────────────

@app.get("/health")
async def health():
    """Lightweight liveness probe — returns 200 as soon as the process is up.

    Deliberately does *not* touch Supabase: the frontend splash screen gates on this,
    so it must stay fast and must not fail when only a downstream dependency is out.
    Use /readyz to check dependencies.
    """
    return JSONResponse({"status": "ok", "version": "2.0.0"})


@app.get("/readyz")
async def readyz():
    """Dependency probe — reports whether the job store is actually reachable.

    /health only proves the process is up; a paused Supabase project or bad
    credentials leave it green while every write endpoint 500s. This is the
    one call that tells the two apart.
    """
    checks: dict[str, str] = {}
    try:
        await asyncio.to_thread(
            lambda: get_supabase().table("jobs").select("id").limit(1).execute()
        )
        checks["job_store"] = "ok"
    except Exception as exc:
        checks["job_store"] = f"unreachable: {type(exc).__name__}: {exc}"

    checks["sonic_mcp_url"] = "set" if os.getenv("SONIC_MCP_URL") else "missing"
    checks["groq_api_key"] = "set" if os.getenv("GROQ_API_KEY") else "missing"

    ready = checks["job_store"] == "ok"
    return JSONResponse(
        {"status": "ready" if ready else "degraded", "checks": checks},
        status_code=200 if ready else 503,
    )


# ── Supabase client alias ─────────────────────────────────────────────────────

_get_supabase = get_supabase


# ── Job-store access ──────────────────────────────────────────────────────────

def _create_job_row(job_id: str, user_input: str | None, stress_test: bool) -> None:
    """Insert the pending job row, translating a job-store outage into a clean 503.

    Without this the raw connection error escapes as a bare 500, which historically
    reached the browser stripped of CORS headers and surfaced as "Failed to fetch".
    """
    try:
        get_supabase().table("jobs").insert({
            "id": job_id,
            "status": "pending",
            "user_input": user_input,
            "stress_test": stress_test,
        }).execute()
    except Exception as exc:
        traceback.print_exc()
        print(
            "[Job store] Insert failed. Check that the Supabase project is running "
            "(free-tier projects auto-pause when idle) and that SUPABASE_URL / "
            "SUPABASE_ANON_KEY are correct."
        )
        raise HTTPException(
            status_code=503,
            detail=(
                f"Job store unavailable ({type(exc).__name__}). The analysis database "
                "could not be reached — it may be paused or restarting. Try again shortly."
            ),
        ) from exc


# ── Track registry ────────────────────────────────────────────────────────────

TRACKS = [
    {"track_id": "billie_jean_mj",         "label": "Billie Jean — Michael Jackson", "stress_test": False},
    {"track_id": "humble_kendrick",        "label": "HUMBLE. — Kendrick Lamar",      "stress_test": True},
    {"track_id": "blinding_lights_weeknd", "label": "Blinding Lights — The Weeknd",  "stress_test": False},
]
TRACKS_BY_ID = {t["track_id"]: t for t in TRACKS}


# ── Request model ─────────────────────────────────────────────────────────────

class DemoRequest(BaseModel):
    track_id: str


# ── Background worker ─────────────────────────────────────────────────────────

def _build_result_payload(state: dict, api_base: str = "") -> dict:
    sig             = state["signal_signature"]
    settings        = state["producer_settings"]
    meta            = sig.metadata if sig else {}
    musician_notes  = state.get("musician_notes")
    track_id        = state.get("_track_id", "unknown")
    job_id          = state.get("job_id")

    # Use job_id for namespacing filenames if present to avoid overwrite conflicts
    prefix = job_id if job_id else track_id

    return {
        "track": {
            "title":  meta.get("title", track_id),
            "artist": meta.get("artist", ""),
            "lufs":   sig.master.lufs if sig else None,
            "bpm":    sig.rhythm.bpm if sig else None,
            "key":    sig.rhythm.key if sig else None,
        },
        "pipeline": {
            "confidence":        state["confidence"],
            "iteration_count":   state["iteration_count"],
            "max_iterations":    3,
            "critic_rounds":     state.get("critic_rounds", []),
            "validation_checks": state.get("validation_checks", []),
        },
        "settings":  settings.model_dump() if settings else None,
        "musician":  musician_notes.model_dump() if musician_notes else None,
        "trace_url": state.get("trace_url"),
        "outputs": {
            "pdf_url":      f"{api_base}/outputs/{prefix}_blueprint.pdf",
            "json_url":     f"{api_base}/outputs/{prefix}_preset.json",
            "metadata_url": f"{api_base}/outputs/{prefix}_metadata.json",
        },
    }


def _api_base() -> str:
    """Origin to prefix onto /outputs URLs so downloads point at this API, not the frontend.

    Falls back to RENDER_EXTERNAL_URL, which Render injects automatically — without it
    the payload carries bare "/outputs/..." paths that resolve against the Vercel origin
    and 404, since the generated PDF/JSON live here.
    """
    return (os.getenv("API_BASE_URL") or os.getenv("RENDER_EXTERNAL_URL") or "").rstrip("/")


def _mark_job_failed(job_id: str, message: str) -> None:
    """Best-effort 'failed' write. Never raises — it runs from except blocks, and if
    the job store is what broke, re-raising here would replace the real error with a
    connection error and leave the row stuck on 'processing' either way."""
    try:
        get_supabase().table("jobs").update({
            "status": "failed",
            "error_message": message,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", job_id).execute()
    except Exception as exc:
        print(f"[Job {job_id}] Could not record failure ({message!r}): {exc}")


async def _run_job(
    job_id: str,
    api_base: str,
    *,
    audio_path: str | None = None,
    audio_filename: str | None = None,
    demo_track_id: str | None = None,
    stress_test: bool = False,
) -> None:
    # TODO(live-progress): wire Modal's real /jobs stage into a `stage` column and
    # surface it in GET /jobs/{id} so the loader shows true progress (deferred — V2).
    try:
        sb = get_supabase()
        now_iso = datetime.now(timezone.utc).isoformat()
        sb.table("jobs").update({"status": "processing", "updated_at": now_iso}).eq("id", job_id).execute()

        # Run the graph in a background thread; covers Modal cold start + analysis + LLM.
        state = await asyncio.wait_for(
            asyncio.to_thread(
                run_graph,
                audio_path,
                audio_filename,
                demo_track_id,
                stress_test,
                job_id,
            ),
            timeout=560.0,
        )

        now_iso = datetime.now(timezone.utc).isoformat()
        if state.get("error"):
            sb.table("jobs").update({
                "status": "failed", "error_message": state["error"], "updated_at": now_iso
            }).eq("id", job_id).execute()
            return

        sb.table("jobs").update({
            "status": "completed",
            "result_payload": _build_result_payload(state, api_base),
            "updated_at": now_iso,
        }).eq("id", job_id).execute()

    except asyncio.TimeoutError:
        _mark_job_failed(job_id, "Analysis timed out after 560 seconds.")
    except Exception as exc:
        _mark_job_failed(job_id, str(exc))
    finally:
        if audio_path:
            try:
                Path(audio_path).unlink(missing_ok=True)
            except Exception as e:
                print(f"[Upload cleanup] Failed to delete {audio_path}: {e}")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/tracks")
def get_tracks():
    return TRACKS


@app.post("/analyze", status_code=202)
async def analyze(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTS:
        raise HTTPException(status_code=415, detail="Unsupported file type. Upload an mp3 or wav.")

    job_id = str(uuid.uuid4())
    audio_path = UPLOAD_DIR / f"{job_id}_input{ext}"

    # Stream to disk in chunks; enforce the size cap without buffering the whole file.
    size = 0
    with open(audio_path, "wb") as out:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                out.close()
                audio_path.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="File too large. Max 50 MB.")
            out.write(chunk)

    try:
        _create_job_row(job_id, file.filename, stress_test=False)
    except HTTPException:
        audio_path.unlink(missing_ok=True)  # don't leak the upload if the job never starts
        raise

    api_base = _api_base()
    background_tasks.add_task(
        _run_job, job_id, api_base,
        audio_path=str(audio_path), audio_filename=file.filename, stress_test=False,
    )
    return {"job_id": job_id}


@app.post("/demo", status_code=202)
async def demo(req: DemoRequest, background_tasks: BackgroundTasks):
    track = TRACKS_BY_ID.get(req.track_id)
    if track is None:
        raise HTTPException(status_code=404, detail=f"Unknown demo track: {req.track_id}")

    job_id = str(uuid.uuid4())
    stress_test = track["stress_test"]

    _create_job_row(job_id, req.track_id, stress_test=stress_test)

    api_base = _api_base()
    background_tasks.add_task(
        _run_job, job_id, api_base,
        demo_track_id=req.track_id, stress_test=stress_test,
    )
    return {"job_id": job_id}


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    try:
        response = get_supabase().table("jobs").select("*").eq("id", job_id).single().execute()
    except APIError as exc:
        # .single() raises rather than returning empty data when no row matches.
        raise HTTPException(status_code=404, detail="Job not found") from exc
    except Exception as exc:
        # Connection/DNS/auth failure — distinct from "this job doesn't exist", and
        # the frontend polls this every 3s, so it must not look like a dead job.
        traceback.print_exc()
        raise HTTPException(
            status_code=503,
            detail=(
                f"Job store unavailable ({type(exc).__name__}). Could not read job status."
            ),
        ) from exc

    if not response.data:
        raise HTTPException(status_code=404, detail="Job not found")

    job = response.data
    out = {"job_id": job["id"], "status": job["status"]}

    # TODO(mcp-integration): expose live pipeline stage to the frontend loader.
    # Once _run_job writes a `stage` column (see placeholder there), surface it:
    #     if job.get("stage"):
    #         out["stage"] = job["stage"]
    if job["status"] == "completed":
        out["result"] = job["result_payload"]
    elif job["status"] == "failed":
        out["error"] = job["error_message"]

    return out
