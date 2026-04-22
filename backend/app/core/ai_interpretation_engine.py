"""
AI Interpretation Engine — UrjaRakshak v2.2
============================================
Physics-grounded, structured AI interpretation layer.

Architecture:
  Layer 1 — Deterministic core (physics + GHI + risk) builds structured context
  Layer 2 — Structured prompt builder (never sends raw DB rows)
  Layer 3 — LLM call (Anthropic Claude or OpenAI GPT — temperature 0.2)
  Layer 4 — Output validation + guardrails (strips speculation)
  Layer 5 — Audit: prompt hash, model, tokens, timestamp stored in DB

Ethics contract:
  - SYSTEM_PROMPT explicitly forbids individual attribution
  - Output schema is bounded — no free-text accusation fields
  - If confidence < threshold, interpretation is refused
  - All outputs stored for audit traceability

Author: Vipin Baniya
"""

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Prompt templates ──────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are a senior infrastructure risk analyst for an energy utility company.
Your role is to interpret physics-based grid diagnostics and recommend engineering actions.

STRICT RULES — violation will invalidate this response:
1. DO NOT speculate about individuals, customers, or specific people.
2. All analysis must refer to INFRASTRUCTURE (transformers, lines, meters, substations).
3. Express uncertainty explicitly — use phrases like "may indicate", "possible", "warrants investigation".
4. Be conservative: prefer recommending investigation over definitive conclusions.
5. DO NOT invent data not present in the summary provided.
6. Output ONLY valid JSON matching the schema below. No prose outside JSON.

OUTPUT SCHEMA (return exactly this structure):
{
  "risk_level": "<LOW|MEDIUM|HIGH|CRITICAL>",
  "primary_infrastructure_hypothesis": "<one sentence, infrastructure-scoped>",
  "inspection_priority": "<INFORMATIONAL|LOW|MEDIUM|HIGH|CRITICAL>",
  "recommended_actions": ["<action 1>", "<action 2>", "<action 3>"],
  "confidence_commentary": "<one sentence about confidence and uncertainty>",
  "trend_assessment": "<one sentence about temporal trend if data present, else 'Insufficient trend data'>",
  "estimated_investigation_scope": "<FIELD_CREW|DESK_REVIEW|SENIOR_ENGINEER>"
}
"""

USER_PROMPT_TEMPLATE = """\
GRID SECTION DIAGNOSTIC SUMMARY
=================================
Substation: {substation_id}
Analysis Timestamp: {timestamp}

PHYSICS RESULTS:
  Input Energy:         {input_mwh:.2f} MWh
  Output Energy:        {output_mwh:.2f} MWh
  Expected Tech Loss:   {expected_loss_mwh:.2f} MWh
  Actual Loss:          {actual_loss_mwh:.2f} MWh
  Residual (unexplained): {residual_pct:.2f}% of input
  Balance Status:       {balance_status}
  Measurement Quality:  {measurement_quality}

ANOMALY DETECTION:
  Anomaly Rate:         {anomaly_rate_pct:.1f}% of readings
  Anomalies Flagged:    {anomalies_flagged}
  Detection Method:     Z-Score + Isolation Forest ensemble

GRID HEALTH INDEX:
  GHI Score:            {ghi:.1f} / 100
  Classification:       {ghi_class}
  PBS (Physics Balance): {pbs:.3f}
  ASS (Anomaly Stability): {ass:.3f}
  CS  (Confidence):     {cs:.3f}
  TSS (Trend Stability): {tss:.3f}
  DIS (Data Integrity): {dis:.3f}

RISK CLASSIFICATION (deterministic):
  Priority:             {priority}
  Category:             {category}

TREND DATA ({trend_count} recent analyses):
{trend_summary}

Physics Engine Confidence: {confidence_pct:.0f}%

Interpret this diagnostic. Output JSON only.
"""


# ── Data structures ────────────────────────────────────────────────────────

@dataclass
class AIInterpretationInput:
    substation_id:    str
    timestamp:        str
    input_mwh:        float
    output_mwh:       float
    expected_loss_mwh: float
    actual_loss_mwh:  float
    residual_pct:     float
    balance_status:   str
    measurement_quality: str
    anomaly_rate:     float       # fraction
    anomalies_flagged: int
    ghi:              float
    ghi_class:        str
    pbs:              float
    ass:              float
    cs:               float
    tss:              float
    dis:              float
    priority:         str
    category:         str
    confidence:       float
    trend:            List[Dict]  # [{ts, residual_pct}, …]


@dataclass
class AIInterpretationResult:
    risk_level:                    str
    primary_infrastructure_hypothesis: str
    inspection_priority:           str
    recommended_actions:           List[str]
    confidence_commentary:         str
    trend_assessment:              str
    estimated_investigation_scope: str
    model_name:                    str
    model_version:                 str
    prompt_hash:                   str
    token_usage:                   int
    raw_response:                  Optional[str] = None
    error:                         Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "risk_level":                    self.risk_level,
            "primary_infrastructure_hypothesis": self.primary_infrastructure_hypothesis,
            "inspection_priority":           self.inspection_priority,
            "recommended_actions":           self.recommended_actions,
            "confidence_commentary":         self.confidence_commentary,
            "trend_assessment":              self.trend_assessment,
            "estimated_investigation_scope": self.estimated_investigation_scope,
            "model_name":                    self.model_name,
            "model_version":                 self.model_version,
            "prompt_hash":                   self.prompt_hash,
            "token_usage":                   self.token_usage,
            "error":                         self.error,
        }


# ── Allowed values for guardrail validation ───────────────────────────────

_VALID_RISK_LEVELS = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
_VALID_PRIORITIES  = {"INFORMATIONAL", "LOW", "MEDIUM", "HIGH", "CRITICAL"}
_VALID_SCOPES      = {"FIELD_CREW", "DESK_REVIEW", "SENIOR_ENGINEER"}


# ── Engine ─────────────────────────────────────────────────────────────────

class AIInterpretationEngine:
    """
    AI-powered interpretation layer.

    Supports:
      - Anthropic Claude (claude-haiku-4-5 via Messages API)
      - OpenAI GPT-4o-mini
      - Offline mock mode (no API key configured)

    The engine NEVER sends raw DB rows. It builds a structured summary from
    the deterministic physics + GHI + risk results, then asks the LLM to
    interpret within a bounded JSON schema.
    """

    MIN_CONFIDENCE_THRESHOLD = 0.5  # refuse interpretation below this

    def __init__(
        self,
        anthropic_key: Optional[str] = None,
        openai_key: Optional[str] = None,
        groq_key: Optional[str] = None,
    ):
        self._anthropic_key = anthropic_key
        self._openai_key    = openai_key
        self._groq_key      = groq_key

    @property
    def is_configured(self) -> bool:
        return bool(self._anthropic_key or self._groq_key or self._openai_key)

    @property
    def preferred_provider(self) -> str:
        if self._anthropic_key: return "anthropic"
        if self._groq_key:      return "groq"
        if self._openai_key:    return "openai"
        return "none"

    def interpret(self, inp: AIInterpretationInput) -> AIInterpretationResult:
        """
        Main entry point. Builds prompt, calls LLM, validates output.
        Returns a structured AIInterpretationResult.
        Fallback chain: Anthropic → Groq → OpenAI → offline
        """
        # Refuse if confidence too low
        if inp.confidence < self.MIN_CONFIDENCE_THRESHOLD:
            return self._refused_result(
                reason=f"Confidence {inp.confidence*100:.0f}% is below threshold "
                       f"({self.MIN_CONFIDENCE_THRESHOLD*100:.0f}%). Cannot interpret reliably.",
                inp=inp,
            )

        # Build bounded prompt
        prompt = self._build_user_prompt(inp)
        prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()[:16]

        if not self.is_configured:
            return self._offline_result(inp, prompt_hash)

        # Try providers in priority order: Anthropic → Groq → OpenAI → offline
        providers_to_try = []
        if self._anthropic_key:
            providers_to_try.append("anthropic")
        if self._groq_key:
            providers_to_try.append("groq")
        if self._openai_key:
            providers_to_try.append("openai")

        last_error: Optional[str] = None
        for provider in providers_to_try:
            try:
                if provider == "anthropic":
                    return self._call_anthropic(prompt, prompt_hash, inp)
                elif provider == "groq":
                    return self._call_groq(prompt, prompt_hash, inp)
                else:
                    return self._call_openai(prompt, prompt_hash, inp)
            except Exception as e:
                logger.warning("AI interpretation failed for %s: %s — trying next provider", provider, e)
                last_error = str(e)

        logger.warning("All AI providers failed — returning offline result")
        result = self._offline_result(inp, prompt_hash)
        result.error = f"All API providers failed. Last error: {(last_error or '')[:200]}"
        return result

    # ── Prompt builder ────────────────────────────────────────────────────

    @staticmethod
    def _build_user_prompt(inp: AIInterpretationInput) -> str:
        # Build trend summary
        if inp.trend:
            lines = []
            for t in inp.trend[-7:]:  # last 7 data points
                ts = t.get("ts", "")[:10]
                r  = t.get("residual_pct", 0)
                lines.append(f"  {ts}: residual {r:.2f}%")
            trend_summary = "\n".join(lines)
        else:
            trend_summary = "  No trend data available"

        return USER_PROMPT_TEMPLATE.format(
            substation_id=inp.substation_id,
            timestamp=inp.timestamp,
            input_mwh=inp.input_mwh,
            output_mwh=inp.output_mwh,
            expected_loss_mwh=inp.expected_loss_mwh,
            actual_loss_mwh=inp.actual_loss_mwh,
            residual_pct=inp.residual_pct,
            balance_status=inp.balance_status,
            measurement_quality=inp.measurement_quality,
            anomaly_rate_pct=inp.anomaly_rate * 100,
            anomalies_flagged=inp.anomalies_flagged,
            ghi=inp.ghi,
            ghi_class=inp.ghi_class,
            pbs=inp.pbs,
            ass=inp.ass,
            cs=inp.cs,
            tss=inp.tss,
            dis=inp.dis,
            priority=inp.priority,
            category=inp.category,
            confidence_pct=inp.confidence * 100,
            trend_count=len(inp.trend),
            trend_summary=trend_summary,
        )

    # ── Provider callers ──────────────────────────────────────────────────

    def _call_anthropic(
        self, prompt: str, prompt_hash: str, inp: AIInterpretationInput
    ) -> AIInterpretationResult:
        import anthropic
        client = anthropic.Anthropic(api_key=self._anthropic_key)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=800,
            temperature=0.2,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text
        tokens = response.usage.input_tokens + response.usage.output_tokens
        parsed = self._parse_and_validate(raw)
        return AIInterpretationResult(
            **parsed,
            model_name="claude-haiku-4-5",
            model_version="20251001",
            prompt_hash=prompt_hash,
            token_usage=tokens,
            raw_response=raw,
        )

    def _call_openai(
        self, prompt: str, prompt_hash: str, inp: AIInterpretationInput
    ) -> AIInterpretationResult:
        from openai import OpenAI
        client = OpenAI(api_key=self._openai_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.2,
            max_tokens=800,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )
        raw = response.choices[0].message.content
        tokens = response.usage.total_tokens
        parsed = self._parse_and_validate(raw)
        return AIInterpretationResult(
            **parsed,
            model_name="gpt-4o-mini",
            model_version="2024",
            prompt_hash=prompt_hash,
            token_usage=tokens,
            raw_response=raw,
        )

    def _call_groq(
        self, prompt: str, prompt_hash: str, inp: AIInterpretationInput
    ) -> AIInterpretationResult:
        """Call Groq API using the OpenAI-compatible SDK (free tier, works on Render)."""
        from openai import OpenAI
        client = OpenAI(
            api_key=self._groq_key,
            base_url="https://api.groq.com/openai/v1",
        )
        response = client.chat.completions.create(
            model="llama3-8b-8192",
            temperature=0.2,
            max_tokens=800,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )
        raw = response.choices[0].message.content
        tokens = response.usage.total_tokens if response.usage else 0
        parsed = self._parse_and_validate(raw)
        return AIInterpretationResult(
            **parsed,
            model_name="llama3-8b-8192",
            model_version="groq",
            prompt_hash=prompt_hash,
            token_usage=tokens,
            raw_response=raw,
        )

    # ── Validation / guardrails ───────────────────────────────────────────

    def _parse_and_validate(self, raw: str) -> Dict[str, Any]:
        """
        Parse LLM JSON response and enforce guardrails.
        Raises ValueError on invalid structure.
        """
        # Extract JSON from response (LLM sometimes wraps in code blocks)
        json_str = raw.strip()
        if json_str.startswith("```"):
            json_str = re.sub(r"^```[a-z]*\n?", "", json_str)
            json_str = re.sub(r"\n?```$", "", json_str)

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"LLM returned invalid JSON: {e}. Raw: {raw[:200]}")

        # Validate required fields
        required = {
            "risk_level", "primary_infrastructure_hypothesis",
            "inspection_priority", "recommended_actions",
            "confidence_commentary", "trend_assessment",
            "estimated_investigation_scope",
        }
        missing = required - set(data.keys())
        if missing:
            raise ValueError(f"LLM response missing fields: {missing}")

        # Enforce allowed values
        data["risk_level"] = self._coerce_enum(
            data["risk_level"], _VALID_RISK_LEVELS, "MEDIUM"
        )
        data["inspection_priority"] = self._coerce_enum(
            data["inspection_priority"], _VALID_PRIORITIES, "MEDIUM"
        )
        data["estimated_investigation_scope"] = self._coerce_enum(
            data["estimated_investigation_scope"], _VALID_SCOPES, "FIELD_CREW"
        )

        # Ensure recommended_actions is a list of strings
        if not isinstance(data["recommended_actions"], list):
            data["recommended_actions"] = [str(data["recommended_actions"])]
        data["recommended_actions"] = [str(a)[:300] for a in data["recommended_actions"][:8]]

        # Guardrail: strip any individual-accusing language
        data = self._apply_guardrails(data)

        return data

    @staticmethod
    def _coerce_enum(value: str, valid: set, default: str) -> str:
        normalized = str(value).strip().upper()
        return normalized if normalized in valid else default

    @staticmethod
    def _apply_guardrails(data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Strip any content that references individuals or makes direct accusations.
        Also enforce infrastructure-scoped language.
        """
        # Patterns to detect and neutralise
        _ACCUSATION_PATTERNS = [
            r"\btheft\b", r"\bstolen\b", r"\bfraud\b",
            r"\bsuspect\b", r"\bcriminal\b", r"\billegal\b",
            r"\bcustomer\s+\w+\s+is\b", r"\bperson\b", r"\bindividual\b",
        ]

        def clean(text: str) -> str:
            for pattern in _ACCUSATION_PATTERNS:
                if re.search(pattern, text, re.IGNORECASE):
                    text = re.sub(
                        pattern,
                        "[infrastructure-scoped language required]",
                        text, flags=re.IGNORECASE,
                    )
            return text

        data["primary_infrastructure_hypothesis"] = clean(
            data["primary_infrastructure_hypothesis"]
        )
        data["confidence_commentary"] = clean(data["confidence_commentary"])
        data["recommended_actions"] = [clean(a) for a in data["recommended_actions"]]
        return data

    # ── Fallback results ──────────────────────────────────────────────────

    @staticmethod
    def _offline_result(inp: AIInterpretationInput, prompt_hash: str) -> AIInterpretationResult:
        """
        Deterministic rule-based interpretation when no external AI key is configured.

        Uses physics thresholds, GHI components, and anomaly rates to generate
        structured, domain-specific explanations — no LLM required.
        """
        # ── Risk level from multiple signals ──────────────────────────────
        risk_map_ghi = {
            "HEALTHY": "LOW", "STABLE": "LOW",
            "DEGRADED": "MEDIUM", "CRITICAL": "HIGH", "SEVERE": "CRITICAL",
        }
        risk_from_ghi = risk_map_ghi.get(inp.ghi_class, "MEDIUM")
        _risk_levels = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]

        def _upgrade_risk(current: str, candidate: str) -> str:
            """Return the higher of two risk levels; falls back to 'MEDIUM' for unknown values."""
            curr_idx = _risk_levels.index(current) if current in _risk_levels else 1
            cand_idx = _risk_levels.index(candidate) if candidate in _risk_levels else 1
            return _risk_levels[max(curr_idx, cand_idx)]

        # Override risk upward based on residual and anomaly rate
        if inp.residual_pct > 15 or inp.anomaly_rate > 0.20:
            risk = "CRITICAL"
        elif inp.residual_pct > 10 or inp.anomaly_rate > 0.10:
            risk = "HIGH"
        elif inp.residual_pct > 5 or inp.anomaly_rate > 0.05:
            risk = _upgrade_risk(risk_from_ghi, "MEDIUM")
        else:
            risk = risk_from_ghi

        # ── Primary hypothesis ─────────────────────────────────────────────
        if inp.residual_pct > 10 and inp.anomaly_rate > 0.10:
            hypothesis = (
                f"Substation {inp.substation_id}: combined high residual loss "
                f"({inp.residual_pct:.1f}%) and elevated anomaly rate ({inp.anomaly_rate*100:.1f}%) "
                f"suggest simultaneous technical losses and possible non-technical losses. "
                f"Infrastructure audit and metering review are both warranted."
            )
        elif inp.residual_pct > 10:
            hypothesis = (
                f"Substation {inp.substation_id}: residual energy gap of {inp.residual_pct:.1f}% "
                f"exceeds normal technical-loss range (2–5%). "
                f"Likely causes: transformer efficiency degradation, line resistance increase, "
                f"or unmetered connections. Field inspection recommended."
            )
        elif inp.anomaly_rate > 0.10:
            hypothesis = (
                f"Substation {inp.substation_id}: anomaly rate of {inp.anomaly_rate*100:.1f}% "
                f"is above the expected 2–5% baseline. "
                f"Individual meter readings show irregular consumption patterns. "
                f"Meter health verification and tamper inspection advised."
            )
        elif inp.ghi < 50:
            hypothesis = (
                f"Substation {inp.substation_id} GHI score is low ({inp.ghi:.1f}/100). "
                f"PBS={inp.pbs:.3f}, ASS={inp.ass:.3f}, DIS={inp.dis:.3f}. "
                f"Grid health is below acceptable threshold — engineering review required."
            )
        else:
            hypothesis = (
                f"Substation {inp.substation_id} is operating within normal parameters. "
                f"Residual loss of {inp.residual_pct:.2f}% is within technical-loss bounds. "
                f"GHI {inp.ghi:.1f} ({inp.ghi_class}). Routine monitoring is sufficient."
            )

        # ── Recommended actions based on findings ─────────────────────────
        actions = []
        if inp.residual_pct > 10:
            actions.append(
                f"Investigate unexplained energy loss of {inp.residual_pct:.1f}% — "
                "check transformer efficiency, line losses, and unmetered connections"
            )
        if inp.anomaly_rate > 0.05:
            actions.append(
                f"Review {inp.anomalies_flagged} flagged meters for tamper indicators "
                "and verify calibration records"
            )
        if inp.dis < 0.8:
            actions.append("Improve data quality — check AMR communication links and meter clocks")
        if inp.pbs < 0.7:
            actions.append("Physics balance score low — verify input and output meter accuracy")
        if not actions:
            actions = [
                "Continue routine meter reading schedule",
                "Verify transformer oil levels and cooling system as part of preventive maintenance",
            ]
        # Always include escalation path
        actions.append(
            f"Re-run analysis after corrective actions to confirm GHI improvement above 70"
        )

        # ── Confidence commentary ──────────────────────────────────────────
        conf_commentary = (
            f"Deterministic rule-based analysis — confidence: {inp.confidence*100:.0f}%. "
            f"GHI sub-scores: PBS={inp.pbs:.2f}, ASS={inp.ass:.2f}, CS={inp.cs:.2f}, "
            f"TSS={inp.tss:.2f}, DIS={inp.dis:.2f}. "
            f"Configure ANTHROPIC_API_KEY or OPENAI_API_KEY for LLM-based interpretation."
        )

        # ── Trend assessment ───────────────────────────────────────────────
        if len(inp.trend) >= 3:
            recent_ghi = [t.get("ghi", 0) for t in inp.trend[-3:] if isinstance(t, dict)]
            if len(recent_ghi) >= 2:
                trend_dir = "improving" if recent_ghi[-1] > recent_ghi[0] else "declining"
                trend_note = (
                    f"GHI trend over last {len(recent_ghi)} analyses is {trend_dir}. "
                    f"Latest: {recent_ghi[-1]:.1f}, Earlier: {recent_ghi[0]:.1f}."
                )
            else:
                trend_note = f"{len(inp.trend)} data points available for trend analysis."
        else:
            trend_note = "Insufficient trend data — upload more analyses to track GHI changes."

        return AIInterpretationResult(
            risk_level=risk,
            primary_infrastructure_hypothesis=hypothesis,
            inspection_priority=inp.priority,
            recommended_actions=actions,
            confidence_commentary=conf_commentary,
            trend_assessment=trend_note,
            estimated_investigation_scope=(
                "SENIOR_ENGINEER" if inp.ghi < 50
                else "FIELD_CREW" if inp.ghi < 70
                else "DESK_REVIEW"
            ),
            model_name="offline",
            model_version="rule-based-v2",
            prompt_hash=prompt_hash,
            token_usage=0,
        )

    @staticmethod
    def _refused_result(reason: str, inp: AIInterpretationInput) -> AIInterpretationResult:
        return AIInterpretationResult(
            risk_level="MEDIUM",
            primary_infrastructure_hypothesis="Interpretation refused — insufficient confidence.",
            inspection_priority="MEDIUM",
            recommended_actions=["Collect more data before drawing conclusions", "Verify measurement equipment"],
            confidence_commentary=reason,
            trend_assessment="Insufficient data quality for trend analysis.",
            estimated_investigation_scope="DESK_REVIEW",
            model_name="refused",
            model_version="n/a",
            prompt_hash="",
            token_usage=0,
            error=reason,
        )

    def chat_answer(self, question: str, context: Optional[str] = None) -> Dict[str, Any]:
        """
        Conversational AI response. Returns {answer, model, error}.
        Uses CHAT_SYSTEM_PROMPT for free-form responses (not bounded JSON schema).
        Fallback chain: Anthropic → Groq → OpenAI → offline.
        """
        if not self.is_configured:
            return {
                "answer": self._offline_chat_answer(question, context),
                "model": "offline",
                "error": None,
            }

        user_msg = question
        if context:
            user_msg = f"Context:\n{context}\n\nQuestion: {question}"

        # Try providers in priority order
        providers_to_try = []
        if self._anthropic_key:
            providers_to_try.append("anthropic")
        if self._groq_key:
            providers_to_try.append("groq")
        if self._openai_key:
            providers_to_try.append("openai")

        last_error: Optional[str] = None
        for provider in providers_to_try:
            try:
                if provider == "anthropic":
                    return self._chat_anthropic(user_msg)
                elif provider == "groq":
                    return self._chat_groq(user_msg)
                else:
                    return self._chat_openai(user_msg)
            except Exception as e:
                logger.warning("Chat call failed for %s: %s — trying next provider", provider, e)
                last_error = str(e)

        return {
            "answer": self._offline_chat_answer(question, context),
            "model": "offline-fallback",
            "error": f"All AI providers failed. Last error: {(last_error or '')[:200]}",
        }

    @staticmethod
    def _offline_chat_answer(question: str, context: Optional[str]) -> str:
        """
        Physics-based offline answer that uses the context data to give a
        meaningful response even without an external AI API key.
        """
        import re

        q = question.lower()

        # ── Parse context ──────────────────────────────────────────────────
        substation_id = "unknown substation"
        input_mwh: Optional[float] = None
        output_mwh: Optional[float] = None
        residual_pct: Optional[float] = None
        balance_status: Optional[str] = None
        confidence_pct: Optional[float] = None

        if context:
            for line in context.splitlines():
                line = line.strip()
                if line.startswith("Substation:"):
                    substation_id = line.split(":", 1)[1].strip()
                m = re.search(r"Input energy:\s*([\d.]+)", line)
                if m:
                    input_mwh = float(m.group(1))
                m = re.search(r"Output energy:\s*([\d.]+)", line)
                if m:
                    output_mwh = float(m.group(1))
                m = re.search(r"Residual loss:\s*([\d.]+)", line)
                if m:
                    residual_pct = float(m.group(1))
                m = re.search(r"Balance status:\s*(\S+)", line)
                if m:
                    balance_status = m.group(1).lower()
                m = re.search(r"Confidence:\s*([\d.]+)", line)
                if m:
                    confidence_pct = float(m.group(1))

        has_data = input_mwh is not None

        # ── No context / no data yet ───────────────────────────────────────
        if not has_data:
            if "no analysis" in (context or "").lower() or not context:
                return (
                    f"No analysis data is available for substation '{substation_id}' yet. "
                    "Please upload meter readings and run the Physics Analysis first. "
                    "Once data is available I can answer questions about energy loss, anomalies, and grid health."
                )

        # ── Build a concise data summary ───────────────────────────────────
        loss_kwh = (input_mwh - output_mwh) * 1000 if (input_mwh and output_mwh) else None
        status_label = {
            "balanced": "balanced (within normal technical-loss range)",
            "minor_imbalance": "showing a minor imbalance — worth monitoring",
            "significant_imbalance": "showing a significant imbalance — investigation recommended",
            "critical_imbalance": "in a critical imbalance state — urgent review required",
            "uncertain": "uncertain — more data is needed for a reliable assessment",
            "refused": "refused (insufficient data quality)",
        }.get(balance_status or "", balance_status or "unknown")

        # ── Answer by question intent ──────────────────────────────────────
        if any(kw in q for kw in ("anomal", "anomaly", "anomalies", "detect", "flag", "suspicious")):
            if residual_pct is not None and residual_pct > 10:
                return (
                    f"Substation {substation_id} shows a residual energy gap of {residual_pct:.1f}%, "
                    f"which is above the normal technical-loss threshold (~5%). "
                    f"The balance status is {status_label}. "
                    "This level of residual may indicate metering inaccuracy, unrecorded outages, or non-technical losses. "
                    "I recommend reviewing the individual meter readings for any Z-score outliers flagged during the last upload."
                )
            elif residual_pct is not None:
                return (
                    f"Substation {substation_id} has a residual gap of only {residual_pct:.1f}%, "
                    f"which is within normal technical-loss bounds. "
                    f"Balance status: {status_label}. No significant anomalies detected in the latest analysis."
                )
            return (
                f"Substation {substation_id} has been analysed but no anomaly scores are available yet. "
                "Upload more meter data and run anomaly detection to get detailed results."
            )

        if any(kw in q for kw in ("loss", "energy loss", "theft", "gap", "residual")):
            if input_mwh is not None and output_mwh is not None:
                eff = (output_mwh / input_mwh * 100) if input_mwh > 0 else 0
                return (
                    f"Substation {substation_id} — Energy balance summary:\n"
                    f"  • Input:   {input_mwh:.2f} MWh\n"
                    f"  • Output:  {output_mwh:.2f} MWh\n"
                    f"  • Loss:    {loss_kwh:.1f} kWh ({residual_pct:.1f}%)\n"
                    f"  • Efficiency: {eff:.1f}%\n"
                    f"  • Status: {status_label}\n\n"
                    "Typical technical losses (I²R + transformer) account for 2–5%. "
                    f"A residual of {residual_pct:.1f}% "
                    + ("is within normal range." if (residual_pct or 0) <= 5 else "exceeds normal range and warrants investigation.")
                )
            return f"No energy data found for substation '{substation_id}'. Upload meter readings first."

        if any(kw in q for kw in ("health", "ghi", "grid health", "status", "summary", "overall", "report")):
            if has_data:
                conf_str = f"{confidence_pct:.0f}%" if confidence_pct is not None else "N/A"
                return (
                    f"Grid health summary for substation {substation_id}:\n"
                    f"  • Balance: {status_label}\n"
                    f"  • Input / Output: {input_mwh:.2f} MWh / {output_mwh:.2f} MWh\n"
                    f"  • Residual loss: {residual_pct:.1f}%\n"
                    f"  • Analysis confidence: {conf_str}\n\n"
                    "For a full Grid Health Index (GHI) score please visit the Dashboard page."
                )

        if any(kw in q for kw in ("forecast", "predict", "next", "future", "load")):
            return (
                f"Load forecasting for substation {substation_id}: "
                "The physics engine uses historical meter readings to build a per-meter model. "
                "With sufficient data (≥ 10 readings per meter) the system predicts expected consumption "
                "and flags readings that deviate beyond the forecast band. "
                "Visit the Dashboard → GHI panel for trend charts and the Anomaly page for flagged deviations."
            )

        if any(kw in q for kw in ("efficien", "performance", "throughput")):
            if input_mwh and output_mwh and input_mwh > 0:
                eff = output_mwh / input_mwh * 100
                return (
                    f"Substation {substation_id} efficiency: {eff:.1f}% "
                    f"(delivered {output_mwh:.2f} MWh of {input_mwh:.2f} MWh injected). "
                    f"Balance status: {status_label}."
                )

        # ── Generic / fallback ─────────────────────────────────────────────
        if has_data:
            return (
                f"Here is a quick summary for substation {substation_id}:\n"
                f"  • Input energy: {input_mwh:.2f} MWh\n"
                f"  • Output energy: {output_mwh:.2f} MWh\n"
                f"  • Residual loss: {residual_pct:.1f}%\n"
                f"  • Balance: {status_label}\n\n"
                "You can ask about energy loss, anomalies, efficiency, or load forecasts. "
                "For richer AI analysis, configure an OPENAI_API_KEY or ANTHROPIC_API_KEY."
            )
        return (
            "I am running in offline mode (no AI provider configured). "
            f"Your question was: \"{question}\". "
            "Upload meter data and run physics analysis for substation-specific answers, "
            "or configure an AI provider key for natural-language responses."
        )

    def _chat_openai(self, user_msg: str) -> Dict[str, Any]:
        from openai import OpenAI
        client = OpenAI(api_key=self._openai_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.4,
            max_tokens=500,
            messages=[
                {"role": "system", "content": CHAT_SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
        )
        return {
            "answer": response.choices[0].message.content or "No response.",
            "model": "gpt-4o-mini",
            "error": None,
        }

    def _chat_anthropic(self, user_msg: str) -> Dict[str, Any]:
        import anthropic
        client = anthropic.Anthropic(api_key=self._anthropic_key)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            temperature=0.4,
            system=CHAT_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        content = response.content[0].text if response.content else "No response."
        return {
            "answer": content,
            "model": "claude-haiku-4-5",
            "error": None,
        }

    def _chat_groq(self, user_msg: str) -> Dict[str, Any]:
        """Call Groq API for chat using the OpenAI-compatible SDK (free tier, works on Render)."""
        from openai import OpenAI
        client = OpenAI(
            api_key=self._groq_key,
            base_url="https://api.groq.com/openai/v1",
        )
        response = client.chat.completions.create(
            model="llama3-8b-8192",
            temperature=0.4,
            max_tokens=500,
            messages=[
                {"role": "system", "content": CHAT_SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
        )
        return {
            "answer": response.choices[0].message.content or "No response.",
            "model": "llama3-8b-8192 (groq)",
            "error": None,
        }

# ── Conversational chat prompt ────────────────────────────────────────────

CHAT_SYSTEM_PROMPT = """\
You are UrjaRakshak, an intelligent grid analytics assistant for an energy utility.
You help engineers understand energy loss patterns, anomaly alerts, grid health, and infrastructure risks.

Guidelines:
- Answer concisely and clearly in plain English (2-4 sentences unless more detail is needed).
- Stay infrastructure-scoped. Never speculate about individuals.
- If no analysis data is available, give general guidance based on the question.
- Be helpful, professional, and precise.
"""


# ── Singleton (keys injected at startup) ─────────────────────────────────
_ai_engine: Optional[AIInterpretationEngine] = None


def get_ai_engine() -> AIInterpretationEngine:
    global _ai_engine
    if _ai_engine is None:
        _ai_engine = AIInterpretationEngine()
    return _ai_engine


def init_ai_engine(
    anthropic_key: Optional[str],
    openai_key: Optional[str],
    groq_key: Optional[str] = None,
) -> AIInterpretationEngine:
    global _ai_engine
    _ai_engine = AIInterpretationEngine(
        anthropic_key=anthropic_key,
        openai_key=openai_key,
        groq_key=groq_key,
    )
    return _ai_engine
