from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
import os
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from schemas.producer_settings import Compression, EQBand, ProducerSettings
from schemas.signal_signature import SignalSignature

if TYPE_CHECKING:
    from agents.graph import GraphState

RULES_PATH = Path(__file__).parent.parent / "rules" / "rules.yaml"
MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")


# ── Tool schema the LLM must call to return reasons ─────────────────────────

class ReasonBundle(BaseModel):
    """Structured reasons for each producer setting, grounded in the actual metric values."""
    eq_reasons: list[str]
    compression_reason: str | None
    master_gain_reason: str


# ── Pure-Python rule evaluation ──────────────────────────────────────────────

def _apply_rules(sig: SignalSignature, rules: list[dict], iteration_count: int = 0, stress_test: bool = False) -> dict[str, Any]:
    """
    Evaluate each rule condition against the SignalSignature.
    Returns a dict with: eq_bands, compression, master_gain_db, reasons_templates.
    """
    eq_bands: list[dict] = []
    compression: dict | None = None
    master_gain_db: float = 0.0
    reason_templates: list[str] = []
    compression_reason_template: str | None = None
    master_gain_reason_template: str = ""

    drums = sig.stems.get("drums")

    for rule in rules:
        rule_id = rule["id"]
        action = rule["action"]
        template = rule["reason_template"]

        if rule_id == "spectral_tilt_bright":
            if sig.master.spectral_tilt > 0.7:
                band = dict(action["eq_band"])
                band["reason"] = template.replace("{value}", str(sig.master.spectral_tilt))
                eq_bands.append(band)
                reason_templates.append(band["reason"])

        elif rule_id == "spectral_tilt_dark":
            if sig.master.spectral_tilt < 0.4:
                band = dict(action["eq_band"])
                band["reason"] = template.replace("{value}", str(sig.master.spectral_tilt))
                eq_bands.append(band)
                reason_templates.append(band["reason"])

        elif rule_id == "kick_fundamental_boost":
            if drums and drums.kick_fundamental_hz is not None:
                freq = int(drums.kick_fundamental_hz)

                # Stress test: deliberately overshoot kick freq on iteration 0 to exercise the
                # Analyst→Critic rejection loop. Enabled via GraphState, not hardcoded per track.
                if stress_test and iteration_count == 0:
                    freq += 30

                band = {
                    "band": "low_peak",
                    "freq": freq,
                    "gain_db": action["eq_band"]["gain_db"],
                    "q": action["eq_band"]["q"],
                    "reason": template.replace("{value}", str(freq)),
                }
                eq_bands.append(band)
                reason_templates.append(band["reason"])

        elif rule_id == "heavy_compression_skip":
            if sig.master.dynamic_range_db < 5:
                compression = None
                compression_reason_template = template.replace("{value}", str(sig.master.dynamic_range_db))

        elif rule_id == "moderate_compression":
            if 5 <= sig.master.dynamic_range_db <= 10:
                if compression_reason_template is None:  # heavy_compression_skip didn't fire
                    compression = dict(action["compression"])
                    compression_reason_template = template.replace("{value}", str(sig.master.dynamic_range_db))

        elif rule_id == "loud_master":
            if sig.master.lufs > -10:
                master_gain_db = action["master_gain_db"]
                master_gain_reason_template = template.replace("{value}", str(sig.master.lufs))

        elif rule_id == "quiet_master":
            if sig.master.lufs < -14:
                master_gain_db = action["master_gain_db"]
                master_gain_reason_template = template.replace("{value}", str(sig.master.lufs))

    # Default master_gain_reason if neither loud nor quiet rule fired
    if not master_gain_reason_template:
        master_gain_reason_template = f"LUFS={sig.master.lufs} — within normal range, no gain adjustment"

    return {
        "eq_bands": eq_bands,
        "compression": compression,
        "compression_reason_template": compression_reason_template,
        "master_gain_db": master_gain_db,
        "master_gain_reason_template": master_gain_reason_template,
    }


# ── Retry wrapper for transient Groq errors ──────────────────────────────────

@retry(
    retry=retry_if_exception_type(Exception),
    wait=wait_exponential(multiplier=3, min=5, max=60),
    stop=stop_after_attempt(2),
    reraise=True,
)
def _invoke_with_retry(llm_with_tool, messages):
    return llm_with_tool.invoke(messages)


# ── LLM call: refine reason strings only ────────────────────────────────────

def _refine_reasons(
    sig: SignalSignature,
    draft: dict[str, Any],
    critique: str,
    llm: ChatGroq,
) -> ReasonBundle:
    eq_summaries = "\n".join(
        f"  - {b['band']} @ {b['freq']}Hz, gain={b['gain_db']}dB — template: {b['reason']}"
        for b in draft["eq_bands"]
    )
    compression_summary = (
        f"compression=null — template: {draft['compression_reason_template']}"
        if draft["compression"] is None
        else f"compression {draft['compression']} — template: {draft['compression_reason_template']}"
    )

    critique_block = f"\nPrevious critique to address: {critique}" if critique else ""

    system = SystemMessage(content=(
        "You are an elite, high-end mastering engineer assistant. Your only job is to write professional, "
        "highly nuanced reason strings for a set of producer settings. "
        "Each reason must be technically grounded in the metrics provided. "
        "When explaining compression skips or gain choices, reference the track's genre and the "
        "intentional production aesthetic (e.g., 'already brick-walled', 'preserving transients'). "
        "Do not invent new settings or change any numbers. "
        "Return your answer by calling the ReasonBundle tool."
    ))
    human = HumanMessage(content=(
        f"Track: {sig.track_id} (Genre: {sig.metadata.get('genre', 'Unknown')})\n"
        f"Master LUFS: {sig.master.lufs}, spectral_tilt: {sig.master.spectral_tilt}, "
        f"dynamic_range_db: {sig.master.dynamic_range_db}\n\n"
        f"EQ settings to justify:\n{eq_summaries}\n\n"
        f"Compression: {compression_summary}\n"
        f"Master gain: {draft['master_gain_db']}dB — template: {draft['master_gain_reason_template']}"
        f"{critique_block}\n\n"
        "Write one reason string per EQ band, one for compression (even if skipped), and one for master gain. "
        "Be technical and authoritative. Refer to the genre's typical loudness profile if relevant. "
        "Keep each reason under 25 words and quote the specific metric values."
    ))

    llm_with_tool = llm.bind_tools([ReasonBundle], tool_choice="ReasonBundle")
    response = _invoke_with_retry(llm_with_tool, [system, human])

    tool_call = response.tool_calls[0]
    return ReasonBundle.model_validate(tool_call["args"])


# ── Main node ────────────────────────────────────────────────────────────────

def analyst_node(state: "GraphState") -> "GraphState":
    if state.get("error"):
        return state

    sig: SignalSignature = state["signal_signature"]
    critique: str = state.get("critique", "")
    iteration_count: int = state.get("iteration_count", 0)
    stress_test: bool = state.get("stress_test", False)

    rules_data = yaml.safe_load(RULES_PATH.read_text(encoding="utf-8"))
    rules = rules_data["rules"]

    draft = _apply_rules(sig, rules, iteration_count, stress_test)

    llm = ChatGroq(model=MODEL, temperature=0, timeout=30.0)
    try:
        bundle = _refine_reasons(sig, draft, critique, llm)
    except Exception as e:
        return {**state, "error": f"Groq API request failed: {e}"}

    # Build EQBand objects with LLM-refined reasons
    eq_bands = []
    for i, band_dict in enumerate(draft["eq_bands"]):
        reason = bundle.eq_reasons[i] if i < len(bundle.eq_reasons) else band_dict["reason"]
        eq_bands.append(EQBand(
            band=band_dict["band"],
            freq=band_dict["freq"],
            gain_db=band_dict["gain_db"],
            q=band_dict.get("q"),
            reason=reason,
        ))

    compression = None
    compression_skip_reason = None
    if draft["compression"] is not None:
        compression = Compression(
            ratio=draft["compression"]["ratio"],
            attack_ms=draft["compression"]["attack_ms"],
            release_ms=draft["compression"]["release_ms"],
            reason=bundle.compression_reason or draft["compression_reason_template"],
        )
    else:
        compression_skip_reason = bundle.compression_reason or draft["compression_reason_template"]

    settings = ProducerSettings(
        eq=eq_bands,
        compression=compression,
        compression_skip_reason=compression_skip_reason,
        master_gain_db=draft["master_gain_db"],
        master_gain_reason=bundle.master_gain_reason or draft["master_gain_reason_template"],
        iteration_count=iteration_count,
    )

    return {**state, "producer_settings": settings}
