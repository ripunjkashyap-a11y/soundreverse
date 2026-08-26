from typing import TYPE_CHECKING

import os
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from schemas.producer_settings import ProducerSettings
from schemas.signal_signature import SignalSignature

if TYPE_CHECKING:
    from agents.graph import GraphState

CONFIDENCE_THRESHOLD = 0.8
MAX_ITERATIONS = 3
MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")


@retry(
    retry=retry_if_exception_type(Exception),
    wait=wait_exponential(multiplier=3, min=5, max=60),
    stop=stop_after_attempt(2),
    reraise=True,
)
def _invoke_with_retry(llm_with_tool, messages):
    return llm_with_tool.invoke(messages)


class CritiqueBundle(BaseModel):
    """Structured critique the Critic LLM returns after reviewing the Analyst's settings."""
    verdict_narrative: str   # 1-2 sentences: overall pass/fail assessment
    adjustment_hints: list[str]  # one actionable fix per failed check (empty if all pass)


def _run_checks(sig: SignalSignature, settings: ProducerSettings) -> tuple[float, list[dict], list[str]]:
    """
    Run all physical-impossibility checks.
    Returns (confidence, validation_checks, failure_reasons).
    validation_checks: list of {name, passed, detail} dicts.
    confidence = checks_passed / total_applicable_checks.
    """
    checks: list[dict] = []
    failures: list[str] = []

    # Check 1: over-compression — applying compression to an already slammed master
    if settings.compression is not None and sig.master.dynamic_range_db < 4:
        detail = f"compression applied but dynamic_range_db={sig.master.dynamic_range_db}dB < 4dB"
        checks.append({"name": "Over-compression", "passed": False, "detail": detail})
        failures.append(f"Over-compression: {detail}")
    else:
        checks.append({"name": "Over-compression", "passed": True, "detail": None})

    # Check 2: boosting a high shelf that is already bright
    high_shelf_boost = any(b.band == "high_shelf" and b.gain_db > 0 for b in settings.eq)
    if high_shelf_boost and sig.master.spectral_tilt > 0.75:
        detail = f"high_shelf gain > 0 but spectral_tilt={sig.master.spectral_tilt} > 0.75"
        checks.append({"name": "Bright boost contradiction", "passed": False, "detail": detail})
        failures.append(f"Bright boost contradiction: {detail}")
    else:
        checks.append({"name": "Bright boost contradiction", "passed": True, "detail": None})

    # Check 3: pushing a master that is already at or above streaming ceiling
    if settings.master_gain_db > 0 and sig.master.lufs > -9:
        detail = f"master_gain_db={settings.master_gain_db} > 0 but LUFS={sig.master.lufs} > -9"
        checks.append({"name": "Loudness ceiling", "passed": False, "detail": detail})
        failures.append(f"Loudness ceiling breach: {detail}")
    else:
        checks.append({"name": "Loudness ceiling", "passed": True, "detail": None})

    # Check 4: kick boost frequency mismatch (only applicable if a kick EQ band exists)
    drums = sig.stems.get("drums")
    kick_band = next((b for b in settings.eq if b.band == "low_peak"), None)
    if kick_band is not None and drums is not None and drums.kick_fundamental_hz is not None:
        diff = abs(kick_band.freq - drums.kick_fundamental_hz)
        if diff > 20:
            detail = f"EQ targets {kick_band.freq}Hz but kick_fundamental_hz={drums.kick_fundamental_hz}Hz (diff={diff:.1f}Hz > 20Hz)"
            checks.append({"name": "Kick frequency mismatch", "passed": False, "detail": detail})
            failures.append(f"Kick freq mismatch: {detail}")
        else:
            checks.append({"name": "Kick frequency mismatch", "passed": True, "detail": None})
    else:
        checks.append({"name": "Kick frequency mismatch", "passed": True, "detail": None})

    checks_passed = sum(1 for c in checks if c["passed"])
    confidence = round(checks_passed / len(checks), 4) if checks else 1.0
    return confidence, checks, failures


def _generate_critique(
    sig: SignalSignature,
    settings: ProducerSettings,
    checks: list[dict],
    failures: list[str],
    llm: ChatGroq,
) -> CritiqueBundle:
    """
    LLM call: given the deterministic check results, write a structured critique.
    The Analyst receives this on the next iteration so it can fix specific issues.
    """
    checks_summary = "\n".join(
        f"  {'PASS' if c['passed'] else 'FAIL'} — {c['name']}: {c['detail'] or 'ok'}"
        for c in checks
    )
    eq_summary = "\n".join(
        f"  {b.band} @ {b.freq}Hz, gain={b.gain_db}dB, Q={b.q}" for b in settings.eq
    )
    compression_summary = (
        f"ratio={settings.compression.ratio}, attack={settings.compression.attack_ms}ms, "
        f"release={settings.compression.release_ms}ms"
        if settings.compression else "null (skipped)"
    )

    system = SystemMessage(content=(
        "You are a mastering quality-control agent. "
        "You receive deterministic check results from a rule engine and the proposed producer settings. "
        "Your job is to write a clear, technically precise critique for the Analyst agent. "
        "If settings pass, write a confident sign-off. "
        "If settings fail, write specific, actionable correction hints — each hint must name the exact metric "
        "and the exact correction needed (e.g. 'reduce kick boost from 90Hz to 60Hz to match stem fundamental'). "
        "Do not invent new rules. Base your critique only on the check results provided. "
        "Call the CritiqueBundle tool to return your answer."
    ))
    human = HumanMessage(content=(
        f"Track: {sig.track_id} | Genre: {sig.metadata.get('genre', 'Unknown')}\n"
        f"Master: LUFS={sig.master.lufs}, DR={sig.master.dynamic_range_db}dB, "
        f"spectral_tilt={sig.master.spectral_tilt}\n\n"
        f"Proposed EQ:\n{eq_summary}\n"
        f"Compression: {compression_summary}\n"
        f"Master gain: {settings.master_gain_db}dB\n\n"
        f"Validation check results:\n{checks_summary}\n\n"
        f"Failed checks: {len(failures)}/{len(checks)}\n"
        + (f"Failure details: {'; '.join(failures)}" if failures else "All checks passed.")
        + "\n\nWrite your verdict_narrative and adjustment_hints now."
    ))

    llm_with_tool = llm.bind_tools([CritiqueBundle], tool_choice="CritiqueBundle")
    response = _invoke_with_retry(llm_with_tool, [system, human])
    tool_call = response.tool_calls[0]
    return CritiqueBundle.model_validate(tool_call["args"])


def critic_node(state: "GraphState") -> "GraphState":
    if state.get("error"):
        return state

    sig: SignalSignature = state["signal_signature"]
    settings: ProducerSettings = state["producer_settings"]
    iteration_count: int = state.get("iteration_count", 0) + 1

    confidence, validation_checks, failures = _run_checks(sig, settings)

    # LLM call: write a structured critique narrative the Analyst can act on
    llm = ChatGroq(model=MODEL, temperature=0, timeout=30.0)
    try:
        bundle = _generate_critique(sig, settings, validation_checks, failures, llm)
    except Exception as e:
        return {**state, "error": f"Groq API request failed: {e}"}

    # Pass the LLM-written hints as the critique so Analyst gets actionable feedback
    critique = bundle.verdict_narrative
    if bundle.adjustment_hints:
        critique += " Corrections needed: " + "; ".join(bundle.adjustment_hints)

    settings = settings.model_copy(update={"confidence": confidence, "iteration_count": iteration_count})

    history = state.get("critique_history", []) + ([critique] if critique else [])

    rejected = confidence < CONFIDENCE_THRESHOLD and iteration_count < MAX_ITERATIONS
    round_entry = {
        "iteration": iteration_count,
        "confidence": confidence,
        "rejected": rejected,
        "reason": critique if critique else None,
    }
    critic_rounds = state.get("critic_rounds", []) + [round_entry]

    if confidence >= CONFIDENCE_THRESHOLD or iteration_count >= MAX_ITERATIONS:
        critique_note = ""
        if iteration_count >= MAX_ITERATIONS and confidence < CONFIDENCE_THRESHOLD:
            critique_note = f" (max iterations reached, signing off with confidence={confidence})"

        final_critique = critique + critique_note
        return {
            **state,
            "producer_settings": settings,
            "confidence": confidence,
            "iteration_count": iteration_count,
            "critique": final_critique,
            "critique_history": history,
            "critic_rounds": critic_rounds,
            "validation_checks": validation_checks,
            "final": True,
        }

    return {
        **state,
        "producer_settings": settings,
        "confidence": confidence,
        "iteration_count": iteration_count,
        "critique": critique,
        "critique_history": history,
        "critic_rounds": critic_rounds,
        "validation_checks": validation_checks,
        "final": False,
    }
