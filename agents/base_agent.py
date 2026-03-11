"""
Base agent — shared logic for all analysis agents.
Uses the LLMRouter for multi-provider support.
"""

import sys
from providers.llm_router import LLMRouter, LLMResponse


class BaseAgent:
    AGENT_NAME = "base"
    AGENT_VERSION = "1.0"

    def __init__(self, router: LLMRouter, verbose: bool = False):
        self.router = router
        self.verbose = verbose

    def _log(self, msg: str):
        if self.verbose:
            print(f"  [{self.AGENT_NAME}] {msg}", file=sys.stderr)

    def _chat(self, phase: str, system: str, user: str) -> str:
        resp = self.router.chat(phase, system, user)
        return resp.text

    def _chat_json(self, phase: str, system: str, user: str) -> dict:
        return self.router.chat_json(phase, system, user)

    def _truncate(self, content: str, max_chars: int = 15000) -> str:
        if len(content) <= max_chars:
            return content
        half = max_chars // 2
        return (
            content[:half]
            + f"\n\n... [TRUNCATED {len(content) - max_chars} chars] ...\n\n"
            + content[-half:]
        )

    def _format_files(self, files: list, max_total: int = 80000) -> str:
        parts = []
        total = 0
        for f in files:
            if f.content is None:
                parts.append(f'<file path="{f.relative}">[binary, {f.size}B]</file>')
                continue
            content = self._truncate(f.content)
            entry = f'<file path="{f.relative}">\n{content}\n</file>'
            if total + len(entry) > max_total:
                remaining = len(files) - len(parts)
                parts.append(f"\n[... {remaining} more files omitted ...]")
                break
            parts.append(entry)
            total += len(entry)
        return "\n\n".join(parts)
