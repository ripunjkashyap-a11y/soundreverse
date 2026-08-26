import math
from typing import TYPE_CHECKING

import os
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from schemas.signal_signature import SignalSignature, MasterMetrics
from schemas.musician_notes import MusicianNotes, TuningTarget

if TYPE_CHECKING:
    from agents.graph import GraphState

MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")

_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


# ── Deterministic fact extraction ────────────────────────────────────────────

def _hz_to_note(hz: float | None) -> str:
    """Nearest equal-tempered note name (A4 = 440 Hz). e.g. 62 Hz -> 'B1'."""
    if not hz or hz <= 0:
        return "-"
    midi = round(69 + 12 * math.log2(hz / 440.0))
    return f"{_NOTE_NAMES[midi % 12]}{midi // 12 - 1}"


def _tuning_targets(sig: SignalSignature) -> list[TuningTarget]:
    """Pull per-stem fundamentals straight from the signature (no LLM)."""
    targets: list[TuningTarget] = []

    def add(element: str, hz: float | None):
        if hz:
            targets.append(TuningTarget(element=element, hz=round(hz, 1), note=_hz_to_note(hz)))

    drums  = sig.stems.get("drums")
    bass   = sig.stems.get("bass")
    vocals = sig.stems.get("vocals")
    if drums:
        add("Kick",  drums.kick_fundamental_hz)
        add("Snare", drums.snare_fundamental_hz)
    if bass:
        add("Bass", bass.fundamental_hz)
    if vocals:
        add("Vocal presence", vocals.presence_peak_hz)
    return targets


def _tonal_tags(m: MasterMetrics) -> list[str]:
    """Rule-based plain-language tags. Thresholds are deliberately simple and easy to tune."""
    tags: list[str] = []

    ratios = {"low": m.low_energy_ratio, "mid": m.mid_energy_ratio, "high": m.high_energy_ratio}
    dominant = max(ratios, key=ratios.get)
    spread = max(ratios.values()) - min(ratios.values())
    if spread < 0.10:
        tags.append("Balanced spectrum")
    elif dominant == "low":
        tags.append("Bass-forward")
    elif dominant == "high":
        tags.append("Top-heavy")
    else:
        tags.append("Midrange-focused")

    if m.spectral_tilt > 0.60:
        tags.append("Bright")
    elif m.spectral_tilt < 0.40:
        tags.append("Warm / dark")

    if m.stereo_width >= 0.50:
        tags.append("Wide")
    elif m.stereo_width <= 0.30:
        tags.append("Narrow / centered")

    if m.stereo_correlation < 0:
        tags.append("Phase-risk")
    elif m.stereo_correlation >= 0.50:
        tags.append("Mono-solid")

    return tags


# ── LLM phrasing (grounded in the facts above) ───────────────────────────────

class _NotesDraft(BaseModel):
    """Plain-language notes for a non-technical musician/producer."""
    tuning_tip: str
    tonal_character: str


@retry(
    retry=retry_if_exception_type(Exception),
    wait=wait_exponential(multiplier=3, min=5, max=60),
    stop=stop_after_attempt(2),
    reraise=True,
)
def _invoke_with_retry(llm_with_tool, messages):
    return llm_with_tool.invoke(messages)


def _phrase_notes(sig: SignalSignature, targets: list[TuningTarget], tags: list[str],
                  llm: ChatGroq) -> tuple[str, str]:
    r = sig.rhythm
    target_lines = "\n".join(f"  - {t.element}: {t.hz:g} Hz (~{t.note})" for t in targets) or "  (none detected)"

    system = SystemMessage(content=(
        "You help non-technical musicians and bedroom producers. Write warm, plain-language guidance "
        "with no jargon. Do not invent any numbers; only use what is given. "
        "Return your answer by calling the _NotesDraft tool."
    ))
    human = HumanMessage(content=(
        f"Track: {sig.metadata.get('title', sig.track_id)} "
        f"(Genre: {sig.metadata.get('genre', 'Unknown')}, Key: {r.key}, {r.bpm:g} BPM).\n\n"
        f"Instrument fundamentals (tuning targets):\n{target_lines}\n\n"
        f"Tonal character tags: {', '.join(tags) or 'n/a'}\n\n"
        "Write TWO things:\n"
        "1. tuning_tip: ONE friendly sentence (<= 22 words) on how a musician can use these tuning "
        "targets (e.g. layering kick and bass, where vocals sit).\n"
        "2. tonal_character: 1-2 friendly sentences (<= 40 words) describing how the track sounds, "
        "based on the tags above."
    ))

    llm_with_tool = llm.bind_tools([_NotesDraft], tool_choice="_NotesDraft")
    resp = _invoke_with_retry(llm_with_tool, [system, human])
    draft = _NotesDraft.model_validate(resp.tool_calls[0]["args"])
    return draft.tuning_tip.strip(), draft.tonal_character.strip()


def _fallback_text(targets: list[TuningTarget], tags: list[str]) -> tuple[str, str]:
    tip = (
        "Lock your low end to the kick and bass fundamentals listed, and keep vocals clear around their presence peak."
        if targets else "No strong instrument fundamentals were detected for this track."
    )
    character = ("This mix reads as " + ", ".join(t.lower() for t in tags) + ".") if tags else ""
    return tip, character


# ── Node ─────────────────────────────────────────────────────────────────────

def musician_node(state: "GraphState") -> "GraphState":
    """Derive musician/producer-facing notes from the SignalSignature.

    Supplementary output: an LLM failure degrades to deterministic text and never
    fails the run.
    """
    if state.get("error"):
        return state

    sig: SignalSignature = state.get("signal_signature")
    if sig is None:
        return state

    targets = _tuning_targets(sig)
    tags = _tonal_tags(sig.master)

    try:
        llm = ChatGroq(model=MODEL, temperature=0.3, timeout=30.0)
        tip, character = _phrase_notes(sig, targets, tags, llm)
    except Exception:
        tip, character = _fallback_text(targets, tags)

    notes = MusicianNotes(
        tuning_targets=targets,
        tuning_tip=tip,
        tonal_tags=tags,
        tonal_character=character,
    )
    return {**state, "musician_notes": notes}
