"""
Summarizer Agent — Two-pass report generation.

Pass 1 (fast model): Structure the report, calculate scores, organize findings.
Pass 2 (mid model): Validate structure, enrich priorities with actionable detail.

This ensures consistent report structure while still getting quality insights.
"""

from agents.base_agent import BaseAgent


class SummarizerAgent(BaseAgent):
    AGENT_NAME = "summarizer"
    AGENT_VERSION = "2.0"

    def analyze(self, findings: list[dict], stack: dict,
                user_query: str = None) -> dict:
        self._log(f"Summarizing {len(findings)} findings (dual-pass)...")

        critical = [f for f in findings if f.get("severity") == "critical"]
        warnings = [f for f in findings if f.get("severity") == "warning"]
        infos = [f for f in findings if f.get("severity") == "info"]

        # ── Pass 1: Fast model structures the report ──
        self._log("Pass 1: Structuring (fast model)...")
        findings_text = self._format_findings(findings)

        structure_prompt = f"""Structure this codebase analysis into a summary.

Counts: {len(critical)} critical, {len(warnings)} warning, {len(infos)} info

## Findings
{findings_text}

Return JSON:
{{
  "health_score": <number 0-100>,
  "critical_count": {len(critical)},
  "warning_count": {len(warnings)},
  "info_count": {len(infos)},
  "top_priorities": ["<max 5 most impactful items to fix>"],
  "strengths": ["<2-5 positive observations>"],
  "categories_breakdown": {{
    "architecture": {{"count": 0, "worst_severity": "info"}},
    "resilience": {{"count": 0, "worst_severity": "info"}}
  }}
}}

Score: start at 100, -12 per critical, -4 per warning, -1 per info. Min 5.
{"User concern: " + user_query if user_query else ""}"""

        structure = self._chat_json("report", (
            "You structure codebase analysis reports. Calculate the health score "
            "precisely. Organize findings into clear priorities."
        ), structure_prompt)

        # Force correct counts
        structure["critical_count"] = len(critical)
        structure["warning_count"] = len(warnings)
        structure["info_count"] = len(infos)

        # ── Pass 2: Mid model validates and enriches ──
        self._log("Pass 2: Enriching (mid model)...")

        enrich_prompt = f"""Review and improve this codebase analysis summary.

## Current Summary
{self._json_str(structure)}

## Stack
Languages: {', '.join(l['name'] for l in stack.get('languages', []))}
Frameworks: {', '.join(f['name'] for f in stack.get('frameworks', []))}

## Key Findings
{findings_text[:4000]}

Improve the summary:
1. Make top_priorities more actionable (include specific finding IDs)
2. Ensure strengths are specific, not generic
3. Validate the health_score makes sense
4. Keep the exact same JSON structure

{"The developer asked: " + user_query + " — ensure priorities address this." if user_query else ""}

Return the improved JSON (same schema)."""

        try:
            enriched = self._chat_json("validate", (
                "You review and improve codebase analysis summaries. "
                "Keep the same JSON structure. Make priorities actionable."
            ), enrich_prompt)

            # Merge: keep enriched text but our verified counts
            enriched["critical_count"] = len(critical)
            enriched["warning_count"] = len(warnings)
            enriched["info_count"] = len(infos)

            return enriched

        except Exception as e:
            self._log(f"Enrichment pass failed ({e}), using structure pass.")
            return structure

    def _format_findings(self, findings: list[dict]) -> str:
        lines = []
        for f in findings:
            lines.append(
                f"[{f.get('severity', '?').upper()}] {f.get('id', '?')}: "
                f"{f.get('title', '?')} ({f.get('category', '?')})"
            )
            desc = f.get("description", "")[:150]
            if desc:
                lines.append(f"  {desc}")
            lines.append("")
        return "\n".join(lines)

    def _json_str(self, obj: dict) -> str:
        import json
        return json.dumps(obj, indent=2, ensure_ascii=False)
