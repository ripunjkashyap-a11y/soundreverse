import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from fpdf import FPDF
from fpdf.enums import XPos, YPos

if TYPE_CHECKING:
    from agents.graph import GraphState

OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", str(Path(__file__).parent.parent / "output")))

# ── Colour palette ───────────────────────────────────────────────────────────
PRIMARY   = (15,  23,  42)   # slate-900
ACCENT    = (99, 102, 241)   # indigo-500
LIGHT_BG  = (241, 245, 249)  # slate-100
MID_GREY  = (100, 116, 139)  # slate-500
WHITE     = (255, 255, 255)
RED_SOFT  = (220,  38,  38)
GREEN_SOFT= (22, 163,  74)

CONTENT_W = 182  # usable width with 14mm side margins


# ── PDF class ────────────────────────────────────────────────────────────────

class BlueprintPDF(FPDF):
    def __init__(self, track_id: str, display_name: str | None = None):
        super().__init__()
        self.track_id     = track_id
        self.display_name = display_name or track_id
        self.set_auto_page_break(auto=True, margin=16)
        self.set_margins(14, 14, 14)

    def normalize_text(self, txt: str) -> str:
        """Override to silently replace any non-latin-1 chars instead of crashing."""
        try:
            return super().normalize_text(txt)
        except Exception:
            return txt.encode("latin-1", errors="replace").decode("latin-1")

    @staticmethod
    def _safe(text: str) -> str:
        """Replace Unicode chars outside latin-1 range so Helvetica doesn't choke."""
        return (
            str(text)
            .replace("—", "--")   # em dash
            .replace("–", "-")    # en dash
            .replace("‘", "'").replace("’", "'")   # curly single quotes
            .replace("“", '"').replace("”", '"')   # curly double quotes
            .encode("latin-1", errors="replace").decode("latin-1")
        )

    # -- Header ---------------------------------------------------------------
    def header(self):
        self.set_fill_color(*PRIMARY)
        self.rect(0, 0, 210, 16, "F")
        self.set_xy(14, 4)
        self.set_font("Helvetica", "B", 12)
        self.set_text_color(*WHITE)
        self.cell(0, 8, self._safe("SoundReverse"))
        self.set_xy(14, 5)
        self.set_font("Helvetica", "", 9)
        self.set_text_color(200, 205, 220)
        self.cell(CONTENT_W, 7, self._safe(self.display_name), align="R")
        self.set_text_color(*PRIMARY)
        self.set_y(24)

    # -- Footer ---------------------------------------------------------------
    def footer(self):
        self.set_y(-13)
        self.set_draw_color(225, 230, 238)
        self.set_line_width(0.3)
        self.line(14, self.get_y(), 196, self.get_y())
        self.ln(2)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*MID_GREY)
        # {nb} is auto-substituted with the total page count by fpdf2 at output time
        self.cell(0, 5, self._safe(f"SoundReverse  \xb7  Producer Session Pack  \xb7  Page {self.page_no()}/{{nb}}"), align="C")

    # -- Hero title block -----------------------------------------------------
    def hero(self, title: str, subtitle: str = ""):
        self.set_font("Helvetica", "B", 26)
        self.set_text_color(*PRIMARY)
        self.cell(0, 13, self._safe(title), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        if subtitle:
            self.set_font("Helvetica", "", 12)
            self.set_text_color(*MID_GREY)
            self.cell(0, 7, self._safe(subtitle), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(*PRIMARY)
        self.ln(5)

    # -- Headline stat cards --------------------------------------------------
    def stat_cards(self, cards: list[tuple[str, str]]):
        n = len(cards)
        gap = 4
        card_w = (CONTENT_W - gap * (n - 1)) / n
        card_h = 26
        x0 = self.l_margin
        y0 = self.get_y()
        for i, (label, value) in enumerate(cards):
            x = x0 + i * (card_w + gap)
            self.set_fill_color(*LIGHT_BG)
            self.rect(x, y0, card_w, card_h, "F")
            self.set_fill_color(*ACCENT)
            self.rect(x, y0, card_w, 2.5, "F")
            self.set_xy(x, y0 + 6)
            self.set_font("Helvetica", "B", 19)
            self.set_text_color(*PRIMARY)
            self.cell(card_w, 11, self._safe(str(value)), align="C")
            self.set_xy(x, y0 + 17)
            self.set_font("Helvetica", "B", 8)
            self.set_text_color(*MID_GREY)
            self.cell(card_w, 5, self._safe(label.upper()), align="C")
        self.set_xy(x0, y0 + card_h)
        self.set_text_color(*PRIMARY)

    # -- Section title --------------------------------------------------------
    def section_title(self, text: str):
        self.set_fill_color(*ACCENT)
        self.set_text_color(*WHITE)
        self.set_font("Helvetica", "B", 12)
        self.cell(0, 9, self._safe(f"  {text}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)
        self.set_text_color(*PRIMARY)
        self.ln(2.5)

    # -- Key/value row --------------------------------------------------------
    def kv_row(self, label: str, value: str, shade: bool = False):
        self.set_fill_color(*(LIGHT_BG if shade else WHITE))
        self.set_font("Helvetica", "B", 11)
        self.cell(58, 9, self._safe(f"  {label}"), fill=True)
        self.set_font("Helvetica", "", 11)
        self.cell(0, 9, self._safe(str(value)), new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)

    # -- Two-column key/value grid --------------------------------------------
    def kv_grid(self, pairs: list[tuple[str, str]], cols: int = 2):
        col_w   = CONTENT_W / cols
        label_w = 42
        val_w   = col_w - label_w
        h = 9
        for idx, (k, v) in enumerate(pairs):
            shade = (idx // cols) % 2 == 0
            self.set_fill_color(*(LIGHT_BG if shade else WHITE))
            self.set_font("Helvetica", "B", 10)
            self.cell(label_w, h, self._safe(f"  {k}"), fill=True)
            self.set_font("Helvetica", "", 10)
            if idx % cols == cols - 1:
                self.cell(val_w, h, self._safe(str(v)), fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            else:
                self.cell(val_w, h, self._safe(str(v)), fill=True)
        if len(pairs) % cols != 0:
            self.ln(h)

    # -- Table header / row ---------------------------------------------------
    def table_header(self, cols: list[tuple[str, float]]):
        self.set_fill_color(*PRIMARY)
        self.set_text_color(*WHITE)
        self.set_font("Helvetica", "B", 10)
        for label, width in cols:
            self.cell(width, 9, self._safe(f"  {label}"), fill=True)
        self.ln()
        self.set_text_color(*PRIMARY)

    def table_row(self, cells: list[tuple[str, float]], shade: bool = False):
        self.set_fill_color(*(LIGHT_BG if shade else WHITE))
        self.set_font("Helvetica", "", 11)
        for text, width in cells:
            self.cell(width, 9, self._safe(f"  {text}"), fill=True)
        self.ln()

    # -- Reason block ---------------------------------------------------------
    def reason_block(self, label: str, reason: str, shade: bool = False):
        self.set_fill_color(*(LIGHT_BG if shade else WHITE))
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(*PRIMARY)
        self.cell(0, 8, self._safe(f"  {label}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)
        self.set_font("Helvetica", "", 11)
        self.set_text_color(*MID_GREY)
        self.multi_cell(0, 6, self._safe(f"  {reason}"), fill=True)
        self.set_text_color(*PRIMARY)
        self.ln(3)


# ── Page builders ────────────────────────────────────────────────────────────

def _musician_sections(pdf: BlueprintPDF, state: "GraphState"):
    """Musician-first content: how the track sounds + instrument tuning targets."""
    notes = state.get("musician_notes")
    if not notes:
        return

    if notes.tonal_tags or notes.tonal_character:
        pdf.section_title("Tonal Character")
        if notes.tonal_tags:
            pdf.set_font("Helvetica", "B", 11)
            pdf.set_text_color(*ACCENT)
            pdf.cell(0, 8, pdf._safe("  " + "    \xb7    ".join(notes.tonal_tags)),
                     new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_text_color(*PRIMARY)
        if notes.tonal_character:
            pdf.set_font("Helvetica", "", 11)
            pdf.multi_cell(0, 6, pdf._safe("  " + notes.tonal_character))
        pdf.ln(6)

    if notes.tuning_targets:
        pdf.section_title("Sound & Tuning Targets")
        pdf.table_header([("Element", 74), ("Frequency", 54), ("Nearest Note", 54)])
        for i, t in enumerate(notes.tuning_targets):
            pdf.table_row([(t.element, 74), (f"{t.hz:g} Hz", 54), (t.note, 54)], shade=(i % 2 == 0))
        if notes.tuning_tip:
            pdf.ln(1)
            pdf.set_font("Helvetica", "I", 10)
            pdf.set_text_color(*MID_GREY)
            pdf.multi_cell(0, 6, pdf._safe("  " + notes.tuning_tip))
            pdf.set_text_color(*PRIMARY)
        pdf.ln(6)


def _signal_profile(pdf: BlueprintPDF, sig: "SignalSignature"):
    """Detailed (more technical) measured metrics — page 2 reference."""
    m = sig.master
    r = sig.rhythm
    drums = sig.stems.get("drums")
    kick_hz = f"{drums.kick_fundamental_hz:g} Hz" if (drums and drums.kick_fundamental_hz) else "-"
    pdf.section_title("Mix Signal Profile")
    pdf.kv_grid([
        ("Loudness",         f"{m.lufs:g} LUFS"),
        ("True Peak",        f"{m.true_peak_dbtp:g} dBTP"),
        ("Dynamic Range",    f"{m.dynamic_range_db:g} dB"),
        ("Sample Peak",      f"{m.peak_db:g} dB"),
        ("Spectral Tilt",    f"{m.spectral_tilt:g}"),
        ("Stereo Width",     f"{m.stereo_width:g}"),
        ("Stereo Corr.",     f"{m.stereo_correlation:g}"),
        ("Kick Fundamental", kick_hz),
        ("Tempo",            f"{r.bpm:g} BPM  ({r.time_signature})"),
        ("Key",              r.key),
    ], cols=2)


def _page1_overview(pdf: BlueprintPDF, state: "GraphState"):
    """Page 1 - the complete at-a-glance producer pack."""
    pdf.add_page()

    sig      = state["signal_signature"]
    settings = state["producer_settings"]
    meta     = sig.metadata
    m        = sig.master
    r        = sig.rhythm

    # -- Hero ------------------------------------------------------------------
    title = meta.get("title", sig.track_id)
    subtitle_bits = [b for b in [
        meta.get("artist"),
        meta.get("album"),
        f"{meta.get('year')}" if meta.get("year") else None,
        meta.get("genre"),
    ] if b]
    pdf.hero(title, "   \xb7   ".join(subtitle_bits))

    # -- Headline stat cards ---------------------------------------------------
    pdf.stat_cards([
        ("BPM",              f"{r.bpm:g}"),
        ("Key",              r.key),
        ("Loudness \xb7 LUFS", f"{m.lufs:g}"),
        ("Dyn. Range \xb7 dB", f"{m.dynamic_range_db:g}"),
    ])
    pdf.ln(8)

    # -- Musician-first: how it sounds + tuning targets ------------------------
    _musician_sections(pdf, state)

    # -- EQ moves --------------------------------------------------------------
    pdf.section_title("EQ Moves")
    pdf.table_header([("Band", 50), ("Freq (Hz)", 44), ("Gain (dB)", 44), ("Q", 44)])
    if settings.eq:
        for i, band in enumerate(settings.eq):
            q_str = f"{band.q:g}" if band.q is not None else "-"
            pdf.table_row([
                (band.band,              50),
                (f"{band.freq:g}",       44),
                (f"{band.gain_db:+.1f}", 44),
                (q_str,                  44),
            ], shade=(i % 2 == 0))
    else:
        pdf.table_row([("No corrective EQ recommended -- mix is balanced", 182)], shade=True)
    pdf.ln(7)

    # -- Dynamics --------------------------------------------------------------
    pdf.section_title("Bus Compression  &  Master Gain")
    if settings.compression:
        c = settings.compression
        pdf.kv_row("Compression Ratio", c.ratio,           shade=True)
        pdf.kv_row("Attack",            f"{c.attack_ms} ms")
        pdf.kv_row("Release",           f"{c.release_ms} ms", shade=True)
    else:
        pdf.kv_row("Bus Compression", "None -- signal already controlled", shade=True)
    pdf.kv_row("Master Gain", f"{settings.master_gain_db:+.1f} dB")


def _page2_reasoning(pdf: BlueprintPDF, state: "GraphState"):
    """Page 2 - measured signal detail + the engineering rationale behind each move."""
    pdf.add_page()

    sig      = state["signal_signature"]
    settings = state["producer_settings"]

    # Detailed measured metrics (more technical reference)
    _signal_profile(pdf, sig)
    pdf.ln(7)

    pdf.section_title("Why These Settings")
    pdf.ln(1)
    pdf.set_font("Helvetica", "I", 10)
    pdf.set_text_color(*MID_GREY)
    pdf.multi_cell(0, 6, pdf._safe("Every move below is grounded in the measured signal metrics on page 1."))
    pdf.set_text_color(*PRIMARY)
    pdf.ln(4)

    for i, band in enumerate(settings.eq):
        label = f"EQ \xb7 {band.band} @ {band.freq:g} Hz  ({band.gain_db:+.1f} dB)"
        pdf.reason_block(label, band.reason, shade=(i % 2 == 0))

    if settings.compression:
        c = settings.compression
        label = f"Compression \xb7 {c.ratio}  attack {c.attack_ms}ms  release {c.release_ms}ms"
        pdf.reason_block(label, c.reason, shade=(len(settings.eq) % 2 == 0))
    else:
        reason = settings.compression_skip_reason or "Bus compression not applied."
        pdf.reason_block("Compression \xb7 skipped", reason, shade=(len(settings.eq) % 2 == 0))

    pdf.reason_block(
        f"Master Gain \xb7 {settings.master_gain_db:+.1f} dB",
        settings.master_gain_reason or f"Master LUFS = {sig.master.lufs}",
        shade=((len(settings.eq) + 1) % 2 == 0),
    )

    # -- Confidence pill -------------------------------------------------------
    pdf.ln(8)
    conf_text = f"Confidence  {state['confidence']:.2f}"
    pdf.set_font("Helvetica", "B", 12)
    pill_w = pdf.get_string_width(conf_text) + 18
    pdf.set_x((210 - pill_w) / 2)
    pdf.set_fill_color(*ACCENT)
    pdf.set_text_color(*WHITE)
    pdf.cell(pill_w, 11, pdf._safe(conf_text), align="C", fill=True,
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(*PRIMARY)


# ── Output node ──────────────────────────────────────────────────────────────

def output_node(state: "GraphState") -> "GraphState":
    if state.get("error"):
        return state

    settings  = state["producer_settings"]
    track_id  = state["track_request"].track_id
    trace_url = state.get("trace_url")
    job_id    = state.get("job_id")

    # Use job_id as the filename prefix if it exists to prevent concurrent user file overwrites
    prefix = job_id if job_id else track_id

    OUTPUT_DIR.mkdir(exist_ok=True)

    # ── JSON preset ──────────────────────────────────────────────────────────
    preset = {
        "track_id":        track_id,
        "trace_url":       trace_url,
        "confidence":      state["confidence"],
        "iteration_count": state["iteration_count"],
        **settings.model_dump(),
    }
    preset_path = OUTPUT_DIR / f"{prefix}_preset.json"
    preset_path.write_text(json.dumps(preset, indent=2), encoding="utf-8")

    # ── PDF blueprint ────────────────────────────────────────────────────────
    try:
        # Producer-facing display name (e.g. "Billie Jean - Michael Jackson")
        sig   = state["signal_signature"]
        meta  = sig.metadata if sig else {}
        title = meta.get("title") or track_id
        artist = meta.get("artist")
        display_name = f"{title} - {artist}" if artist else title

        pdf = BlueprintPDF(track_id=track_id, display_name=display_name)
        _page1_overview(pdf, state)
        _page2_reasoning(pdf, state)
        pdf_path = OUTPUT_DIR / f"{prefix}_blueprint.pdf"
        pdf.output(str(pdf_path))
    except Exception as pdf_err:
        print(f"[PDF] generation failed for {track_id}: {pdf_err}")

    # ── Metadata JSON ────────────────────────────────────────────────────────
    run_id = None
    if trace_url:
        # trace URL ends with the run UUID, grab first 8 chars
        run_id = trace_url.rstrip("/").split("/")[-1][:8]

    metadata = {
        "run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "track_id": track_id,
        "pipeline": {
            "gateway": {"source": "cache", "latency_ms": None},
            "analyst": {
                "iterations": state["iteration_count"],
                # Read at write time so the metadata names the model that actually ran.
                # Mirrors the default in agents/analyst.py.
                "model": os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
                "latency_ms": None,
            },
            "critic": {"rounds": state.get("critic_rounds", [])},
        },
        "trace_url": trace_url,
    }
    metadata_path = OUTPUT_DIR / f"{prefix}_metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    return {**state, "trace_url": trace_url}
