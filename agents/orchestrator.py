"""
Orchestrator — Coordinates the multi-agent analysis pipeline.

Pipeline:
  1. [scan]       FileCollector + ScoutAgent (fast model)
  2. [analyze]    ArchitectAgent (mid model)
  3. [specialist] 3x SpecialistAgents (mid model)
  4. [deep]       DeepAnalysisAgent (heavy model) — cross-file flows, hidden issues
  5. [report]     SummarizerAgent pass 1 (fast) + pass 2 (mid)
"""

import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from agents.file_collector import FileCollector
from agents.scout_agent import ScoutAgent
from agents.architect_agent import ArchitectAgent
from agents.specialist_agent import SpecialistAgent
from agents.deep_agent import DeepAnalysisAgent
from agents.summarizer_agent import SummarizerAgent
from providers.llm_router import LLMRouter


class Orchestrator:
    def __init__(
        self,
        root_path: Path,
        router: LLMRouter,
        verbose: bool = False,
        max_files: int = 200,
        guidelines: str = None,
    ):
        self.root_path = root_path
        self.router = router
        self.verbose = verbose
        self.max_files = max_files
        self.guidelines = guidelines

    def run(self, user_query: str = None, repo_info: dict = None) -> dict:
        # ── Step 1: Scan ──
        self._step("1/6", "Scanning codebase...")
        collector = FileCollector(self.root_path, max_files=self.max_files)
        files = collector.collect()
        stats = collector.get_stats()
        tree = collector.tree_summary

        self._info(f"Collected {stats['total_files']} files "
                    f"({stats['total_size_kb']} KB), {stats['directories']} dirs")

        if not files:
            return self._empty_report(user_query, repo_info)

        # ── Step 2: Detect stack ──
        self._step("2/6", "Detecting tech stack (fast model)...")
        scout = ScoutAgent(router=self.router, verbose=self.verbose)
        try:
            stack = scout.analyze(files, stats, tree)
        except Exception as e:
            self._warn(f"Scout failed: {e}")
            stack = self._empty_stack()

        self._print_stack(stack)

        # ── Step 3: Architecture ──
        self._step("3/6", "Analyzing architecture (mid model)...")
        architect = ArchitectAgent(router=self.router, verbose=self.verbose)
        try:
            arch_findings = architect.analyze(
                files, stack, user_query, self.guidelines
            )
        except Exception as e:
            self._warn(f"Architect failed: {e}")
            arch_findings = []
        self._info(f"{len(arch_findings)} architecture findings")

        # ── Step 4: Specialists ──
        self._step("4/6", "Running specialists (mid model)...")
        all_findings = list(arch_findings)

        for specialty in ["resilience", "performance", "security"]:
            self._info(f"  {specialty}...")
            try:
                agent = SpecialistAgent(
                    specialty=specialty,
                    router=self.router,
                    verbose=self.verbose,
                )
                findings = agent.analyze(files, stack, user_query)
                all_findings.extend(findings)
                self._info(f"  → {len(findings)} findings")
            except Exception as e:
                self._warn(f"  {specialty} failed: {e}")

        all_findings = self._deduplicate(all_findings)
        self._info(f"Initial findings: {len(all_findings)} (after dedup)")

        # ── Step 5: Deep Analysis ──
        self._step("5/6", "Deep analysis (heavy model)...")
        deep_agent = DeepAnalysisAgent(router=self.router, verbose=self.verbose)
        try:
            deep_findings = deep_agent.analyze(
                files, stack, all_findings, user_query, self.guidelines
            )
            all_findings.extend(deep_findings)
            self._info(f"Deep analysis: {len(deep_findings)} new findings")
        except Exception as e:
            self._warn(f"Deep analysis failed: {e}")

        all_findings = self._deduplicate(all_findings)
        all_findings = self._reassign_ids(all_findings)
        self._info(f"Total: {len(all_findings)} findings (after dedup)")

        # ── Step 6: Summary ──
        self._step("6/6", "Generating report (fast + mid models)...")
        summarizer = SummarizerAgent(router=self.router, verbose=self.verbose)
        try:
            summary = summarizer.analyze(all_findings, stack, user_query)
        except Exception as e:
            self._warn(f"Summarizer failed: {e}")
            summary = self._fallback_summary(all_findings)

        # ── Build report ──
        report = {
            "meta": {
                "analyzed_at": datetime.now(timezone.utc).isoformat(),
                "root_path": str(self.root_path),
                "duration_seconds": 0,
                "user_query": user_query,
                "source": repo_info or {"type": "local", "path": str(self.root_path)},
                "agent_versions": {
                    "scout": ScoutAgent.AGENT_VERSION,
                    "architect": ArchitectAgent.AGENT_VERSION,
                    "specialist": SpecialistAgent.AGENT_VERSION,
                    "deep_analysis": DeepAnalysisAgent.AGENT_VERSION,
                    "summarizer": SummarizerAgent.AGENT_VERSION,
                },
                "cost": self.router.get_cost_summary(),
            },
            "stack": stack,
            "findings": all_findings,
            "summary": summary,
        }

        return report

    def _deduplicate(self, findings: list[dict]) -> list[dict]:
        seen = set()
        unique = []
        for f in findings:
            key = f.get("title", "").lower().strip()[:60]
            if key and key in seen:
                continue
            seen.add(key)
            unique.append(f)
        return unique

    def _reassign_ids(self, findings: list[dict]) -> list[dict]:
        prefix_map = {
            "architecture": "ARCH", "performance": "PERF",
            "security": "SEC", "resilience": "RES",
            "maintainability": "MAINT", "testing": "TEST",
            "dependencies": "DEP", "configuration": "CFG",
            "observability": "OBS",
        }
        counters: dict[str, int] = {}
        for f in findings:
            prefix = prefix_map.get(f.get("category", ""), "GEN")
            counters[prefix] = counters.get(prefix, 0) + 1
            f["id"] = f"{prefix}-{counters[prefix]:03d}"
        return findings

    def _fallback_summary(self, findings):
        c = sum(1 for f in findings if f.get("severity") == "critical")
        w = sum(1 for f in findings if f.get("severity") == "warning")
        i = sum(1 for f in findings if f.get("severity") == "info")
        return {
            "health_score": max(5, 100 - c * 12 - w * 4 - i),
            "critical_count": c, "warning_count": w, "info_count": i,
            "top_priorities": [
                f.get("title") for f in findings if f.get("severity") == "critical"
            ][:5],
            "strengths": ["Analysis completed"],
        }

    def _empty_stack(self):
        return {"languages": [], "frameworks": [], "package_managers": [],
                "databases": [], "infrastructure": {}}

    def _empty_report(self, query, repo_info):
        return {
            "meta": {
                "analyzed_at": datetime.now(timezone.utc).isoformat(),
                "root_path": str(self.root_path), "duration_seconds": 0,
                "user_query": query, "source": repo_info,
                "agent_versions": {}, "cost": {},
            },
            "stack": self._empty_stack(),
            "findings": [],
            "summary": {
                "health_score": 0, "critical_count": 0,
                "warning_count": 0, "info_count": 0,
                "top_priorities": ["No files found"], "strengths": [],
            },
        }

    def _print_stack(self, stack):
        langs = stack.get("languages", [])
        fws = stack.get("frameworks", [])
        if langs:
            self._info("Languages: " + ", ".join(
                f"{l['name']} {l.get('version', '')}" for l in langs))
        if fws:
            self._info("Frameworks: " + ", ".join(
                f"{f['name']} {f.get('version', '')}" for f in fws))

    def _step(self, n, msg):
        print(f"  [{n}] {msg}")

    def _info(self, msg):
        print(f"       {msg}")

    def _warn(self, msg):
        print(f"  ⚠️  {msg}", file=sys.stderr)
