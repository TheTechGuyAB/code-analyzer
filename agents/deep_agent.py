"""
Deep Analysis Agent — Uses the most powerful model for thorough investigation.
Phase: deep (uses heavy models like Claude Opus or o3)

This agent:
1. Re-examines files related to existing findings with full context
2. Traces data/control flow across files to find cross-cutting issues
3. Looks for subtle bugs, race conditions, hidden assumptions
4. Finds problems that simpler models and developers typically miss
"""

import json
from agents.base_agent import BaseAgent


class DeepAnalysisAgent(BaseAgent):
    AGENT_NAME = "deep-analysis"
    AGENT_VERSION = "2.0"

    def analyze(self, files: list, stack: dict, existing_findings: list,
                user_query: str = None, guidelines: str = None) -> list[dict]:
        self._log("Deep analysis (heavy model)...")

        # ── Pass 1: Cross-file flow tracing ──
        flow_findings = self._analyze_flows(files, stack, user_query)

        # ── Pass 2: Re-examine critical areas with full context ──
        deep_findings = self._deep_examine(files, stack, existing_findings, user_query, guidelines)

        # ── Pass 3: Hidden assumptions & edge cases ──
        edge_findings = self._find_hidden_issues(files, stack, user_query)

        all_new = flow_findings + deep_findings + edge_findings
        self._log(f"Deep analysis found {len(all_new)} additional findings")
        return all_new

    def _analyze_flows(self, files: list, stack: dict, user_query: str) -> list:
        """Trace data and control flow across files to find cross-cutting issues."""
        self._log("Pass 1: Cross-file flow tracing...")

        # Select files that form logical chains (controllers → services → repos)
        chain_files = self._select_chain_files(files)
        if not chain_files:
            return []

        stack_str = self._stack_summary(stack)
        query_section = f'\n## DEVELOPER CONCERN\n"{user_query}"\n' if user_query else ""

        prompt = f"""You are performing DEEP cross-file flow analysis. Your job is to trace how data
and control flows through the application and find issues that only become visible when
you follow the full chain.

## Stack
{stack_str}
{query_section}
## Source Files (arranged by likely call chains)
{self._format_files(chain_files, max_total=100000)}

## ANALYSIS INSTRUCTIONS

Trace these flows through the actual code:

1. **REQUEST FLOW**: HTTP request → controller → service → repository → database
   - Is input validated at the boundary? Does it stay validated?
   - Are errors handled at each layer? Do they propagate correctly?
   - Is auth checked before business logic runs?

2. **DATA FLOW**: Where does data enter? How is it transformed? Where is it stored?
   - Are there places where data types change implicitly?
   - Is sensitive data accidentally exposed in logs, responses, or errors?
   - Are there inconsistent data transformations (encoded one way, decoded another)?

3. **ERROR FLOW**: What happens when things fail at each step?
   - Does a failure in layer N cascade to crash layer N-1?
   - Are there catch blocks that silently swallow errors that should propagate?
   - If an external service returns unexpected data, does the whole chain handle it?

4. **STATE FLOW**: Shared state, singletons, static fields, caching
   - Are there race conditions in shared state?
   - Can cached data go stale and cause incorrect behavior?
   - Are there memory leaks from growing collections never cleared?

5. **DEPENDENCY FLOW**: What happens when dependencies fail?
   - If database is slow, does it cascade to timeout the HTTP request?
   - If an external API changes its response format, where does it break?
   - Are there circular dependencies that could cause deadlocks?

CRITICAL: Only report issues you can PROVE from the code. Reference specific files,
line patterns, and code snippets. Each finding must trace across at least 2 files.

Return JSON array of findings:
[{{
  "id": "DEEP-001",
  "severity": "critical|warning|info",
  "category": "architecture|performance|security|resilience|maintainability",
  "title": "Short title",
  "description": "Detailed multi-file trace showing the issue",
  "affected_files": ["file1.cs", "file2.cs"],
  "evidence": "Code from multiple files showing the issue",
  "recommendation": "Specific fix with code example",
  "effort": "trivial|small|medium|large|epic",
  "agent": "deep-analysis",
  "tags": ["cross-cutting", "flow-trace"]
}}]"""

        system = (
            "You are an elite software architect performing deep code forensics. "
            "You specialize in finding bugs and design flaws that only become visible "
            "when you trace execution across multiple files. You think like a debugger — "
            "following data from entry to exit, looking for where assumptions break down. "
            "You have found production-crashing bugs that teams missed for years. "
            "Every finding must reference actual code from multiple files. Return JSON array."
        )

        try:
            result = self._chat_json("deep", system, prompt)
            return self._normalize(result)
        except Exception as e:
            self._log(f"Flow analysis failed: {e}")
            return []

    def _deep_examine(self, files: list, stack: dict, existing_findings: list,
                      user_query: str, guidelines: str) -> list:
        """Re-examine areas where initial analysis found issues — look deeper."""
        self._log("Pass 2: Deep re-examination of critical areas...")

        # Get files mentioned in existing critical/warning findings
        critical_files = set()
        for f in existing_findings:
            if f.get("severity") in ("critical", "warning"):
                for af in f.get("affected_files", []):
                    critical_files.add(af.lower().replace("\\", "/"))

        if not critical_files:
            # If no findings yet, examine the most complex files
            return self._examine_complex_files(files, stack, user_query)

        # Get full content of those files
        relevant = [f for f in files if f.relative.lower().replace("\\", "/") in critical_files]
        if not relevant:
            # Fuzzy match — filename only
            critical_names = {p.split("/")[-1].lower() for p in critical_files}
            relevant = [f for f in files if f.relative.split("/")[-1].lower() in critical_names
                        or f.relative.split("\\")[-1].lower() in critical_names]

        if not relevant:
            return []

        # Also grab related files (same directory, imported files)
        relevant = self._expand_related(relevant, files)

        findings_summary = "\n".join(
            f"- [{f.get('severity', '?')}] {f.get('title', '?')} in {', '.join(f.get('affected_files', []))}"
            for f in existing_findings if f.get("severity") in ("critical", "warning")
        )

        stack_str = self._stack_summary(stack)
        query_section = f'\n## DEVELOPER CONCERN\n"{user_query}"\n' if user_query else ""
        guidelines_section = f"\n## TEAM GUIDELINES\n{guidelines}\n" if guidelines else ""

        prompt = f"""Previous analysis found these issues. Your job is to go DEEPER — find what
the initial analysis missed. Look for root causes, related problems, and subtle bugs.

## Known Issues (from initial analysis)
{findings_summary}

## Stack
{stack_str}
{query_section}{guidelines_section}
## Files to Deep-Examine (full content)
{self._format_files(relevant, max_total=100000)}

## DEEP EXAMINATION INSTRUCTIONS

For each file, analyze with extreme thoroughness:

1. **ROOT CAUSE ANALYSIS**: The initial findings are symptoms. What's the underlying design
   problem causing them? Is there a systemic issue?

2. **WHAT ELSE IS HIDING**: If this file has one bug, what else is lurking? Similar patterns?
   Copy-pasted code with the same flaw?

3. **EDGE CASES & BOUNDARY CONDITIONS**:
   - What happens with null/empty/zero/negative inputs?
   - What happens with very large inputs? Unicode? Special characters?
   - What happens when collections are empty vs have one item vs many?
   - What happens at midnight, year boundary, DST change?

4. **CONCURRENCY & TIMING**:
   - Is this code thread-safe? What if two requests hit simultaneously?
   - Are there TOCTOU (time-of-check-time-of-use) issues?
   - Could the order of operations ever change?

5. **IMPLICIT CONTRACTS**:
   - What does this code assume about its callers?
   - What does it assume about the data it receives?
   - Are these assumptions documented or enforced?

6. **FAILURE MODES**:
   - What's the worst that can happen if this code fails?
   - Is there data corruption risk?
   - Can partial failures leave the system in an inconsistent state?

DO NOT repeat findings from the initial analysis. Only report NEW discoveries.
Every finding must include specific code evidence.

Return JSON array of findings (same schema as before, agent="deep-analysis")."""

        system = (
            "You are performing a second-pass deep examination of code that already had issues "
            "flagged. Your job is to find what the first pass missed — root causes, related bugs, "
            "edge cases, race conditions, and subtle logic errors. You think adversarially: "
            "'how can this code break in ways nobody expected?' "
            "You have decades of experience debugging production incidents. Return JSON array."
        )

        try:
            result = self._chat_json("deep", system, prompt)
            return self._normalize(result)
        except Exception as e:
            self._log(f"Deep examination failed: {e}")
            return []

    def _find_hidden_issues(self, files: list, stack: dict, user_query: str) -> list:
        """Look for issues that are typically invisible — config problems, implicit
        behavior, missing features, and architectural time bombs."""
        self._log("Pass 3: Hidden issues & time bombs...")

        # Select config files, startup files, and infrastructure files
        hidden_files = self._select_hidden_issue_files(files)
        if not hidden_files:
            return []

        stack_str = self._stack_summary(stack)
        query_section = f'\n## DEVELOPER CONCERN\n"{user_query}"\n' if user_query else ""

        prompt = f"""Analyze for HIDDEN issues — problems that won't show up in normal code review
but will cause production incidents.

## Stack
{stack_str}
{query_section}
## Files
{self._format_files(hidden_files, max_total=80000)}

## WHAT TO LOOK FOR

1. **CONFIGURATION TIME BOMBS**:
   - Default settings that are dangerous in production (debug=true, verbose logging, no HTTPS)
   - Missing rate limiting, request size limits, connection pool limits
   - Timeout values that are too long or missing entirely
   - CORS configured as "*" or overly permissive

2. **MISSING OBSERVABILITY**:
   - No structured logging — will be impossible to debug in production
   - No health checks — orchestrator can't know if service is healthy
   - No metrics/tracing — can't find performance issues
   - Error responses that leak internal details

3. **DEPLOYMENT RISKS**:
   - No graceful shutdown — requests will be dropped during deploy
   - No database migration strategy — schema changes will break
   - Environment-specific config baked into code
   - Missing or incorrect container health probes

4. **SCALABILITY TRAPS**:
   - In-memory state that breaks with multiple instances
   - File system access that won't work in containers
   - Session state stored locally instead of distributed
   - Background jobs that don't coordinate across instances

5. **DEPENDENCY RISKS**:
   - Packages with known vulnerabilities or that are abandoned
   - Tight coupling to specific infrastructure (hard to migrate)
   - Missing dependency injection — can't test or swap implementations
   - Version conflicts or incompatible package combinations

6. **DATA INTEGRITY RISKS**:
   - Missing database transactions where multiple writes should be atomic
   - Eventual consistency issues not handled
   - Missing unique constraints or foreign keys
   - Data validation only on the client side

Return JSON array of findings (agent="deep-analysis", tags should include "hidden-issue")."""

        system = (
            "You are a production reliability engineer who has investigated hundreds of "
            "incidents. You find the problems that 'work fine in dev' but explode in production. "
            "You look at configuration, infrastructure, observability, and the gaps between "
            "what the code does and what production requires. Return JSON array."
        )

        try:
            result = self._chat_json("deep", system, prompt)
            return self._normalize(result)
        except Exception as e:
            self._log(f"Hidden issues analysis failed: {e}")
            return []

    def _examine_complex_files(self, files: list, stack: dict, user_query: str) -> list:
        """When no existing findings, examine the most complex files deeply."""
        # Score by size and complexity indicators
        scored = []
        for f in files:
            if f.content is None:
                continue
            score = f.size
            low = f.content.lower()
            # Boost files with complexity signals
            score += low.count("if ") * 50
            score += low.count("catch") * 100
            score += low.count("async") * 80
            score += low.count("lock") * 200
            score += low.count("static") * 60
            score += low.count("thread") * 200
            score += low.count("concurrent") * 200
            scored.append((score, f))

        scored.sort(key=lambda x: -x[0])
        top_files = [f for _, f in scored[:40]]

        if not top_files:
            return []

        stack_str = self._stack_summary(stack)
        query_section = f'\n## DEVELOPER CONCERN\n"{user_query}"\n' if user_query else ""

        prompt = f"""Perform deep analysis on the most complex files in this codebase.
Find bugs, design flaws, and risks that a normal code review would miss.

## Stack
{stack_str}
{query_section}
## Most Complex Files
{self._format_files(top_files, max_total=100000)}

Analyze for: logic errors, race conditions, null reference chains, resource leaks,
error handling gaps, implicit assumptions, edge cases, and architectural problems.

Every finding must reference specific code. Be thorough but precise.

Return JSON array of findings (agent="deep-analysis")."""

        system = (
            "You are an elite code auditor. You find the bugs that crash production at 3am. "
            "You think adversarially about every code path. Return JSON array."
        )

        try:
            result = self._chat_json("deep", system, prompt)
            return self._normalize(result)
        except Exception as e:
            self._log(f"Complex file examination failed: {e}")
            return []

    # ── File selection helpers ──

    def _select_chain_files(self, files: list) -> list:
        """Select files that form logical call chains."""
        # Group by layer
        layers = {
            "entry": [],      # controllers, endpoints, pages
            "business": [],   # services, handlers, managers
            "data": [],       # repositories, dbcontext, data access
            "config": [],     # startup, program, config
            "infra": [],      # middleware, filters, extensions
        }

        for f in files:
            if f.content is None:
                continue
            low = f.relative.lower() + " " + (f.content[:500].lower() if f.content else "")

            if any(k in low for k in ["controller", "endpoint", "apicontroller", "razor", "page"]):
                layers["entry"].append(f)
            elif any(k in low for k in ["service", "handler", "manager", "usecase", "command"]):
                layers["business"].append(f)
            elif any(k in low for k in ["repository", "dbcontext", "dataaccess", "dal", "store"]):
                layers["data"].append(f)
            elif any(k in low for k in ["startup", "program.cs", "appsettings", "config"]):
                layers["config"].append(f)
            elif any(k in low for k in ["middleware", "filter", "extension", "helper"]):
                layers["infra"].append(f)

        # Take top files from each layer by size
        selected = []
        for layer_files in layers.values():
            layer_files.sort(key=lambda f: f.size, reverse=True)
            selected.extend(layer_files[:20])

        selected.sort(key=lambda f: f.size, reverse=True)
        return selected[:80]

    def _select_hidden_issue_files(self, files: list) -> list:
        """Select config, startup, and infrastructure files."""
        keywords = [
            "appsettings", "config", "startup", "program.cs", "dockerfile",
            "docker-compose", "launchsettings", "web.config", "nginx",
            "package.json", "nuget", "global.json", "directory.build",
            "middleware", "extension", "healthcheck", "health",
            ".env", "secrets", "cors", "auth", "logging", "serilog",
            "nlog", "log4", "telemetry", "applicationinsights",
        ]
        selected = []
        for f in files:
            if f.content is None:
                continue
            low = f.relative.lower()
            if any(k in low for k in keywords):
                selected.append(f)

        # Also add files with configuration patterns
        for f in files:
            if f in selected or f.content is None:
                continue
            low = f.content.lower()
            config_signals = sum(1 for k in [
                "addsingleton", "addscoped", "addtransient", "services.add",
                "builder.services", "app.use", "options.configure",
                "connectionstring", "appsettings", "iconfig",
            ] if k in low)
            if config_signals >= 2:
                selected.append(f)

        return selected[:60]

    def _expand_related(self, core_files: list, all_files: list) -> list:
        """Expand a set of files with related files from same directories."""
        dirs = set()
        for f in core_files:
            parts = f.relative.replace("\\", "/").rsplit("/", 1)
            if len(parts) > 1:
                dirs.add(parts[0].lower())

        related = list(core_files)
        for f in all_files:
            if f in related or f.content is None:
                continue
            fdir = f.relative.replace("\\", "/").rsplit("/", 1)
            if len(fdir) > 1 and fdir[0].lower() in dirs:
                related.append(f)

        related.sort(key=lambda f: f.size, reverse=True)
        return related[:60]

    def _stack_summary(self, stack: dict) -> str:
        parts = []
        langs = stack.get("languages", [])
        if langs:
            parts.append("Languages: " + ", ".join(f"{l['name']} {l.get('version', '')}" for l in langs))
        fws = stack.get("frameworks", [])
        if fws:
            parts.append("Frameworks: " + ", ".join(f"{f['name']} {f.get('version', '')}" for f in fws))
        dbs = stack.get("databases", [])
        if dbs:
            db_names = [d["name"] if isinstance(d, dict) else str(d) for d in dbs]
            parts.append("Databases: " + ", ".join(db_names))
        return "\n".join(parts) if parts else "Unknown stack"

    def _normalize(self, result) -> list:
        if isinstance(result, dict) and "findings" in result:
            result = result["findings"]
        if not isinstance(result, list):
            result = [result]
        # Ensure agent tag
        for f in result:
            if isinstance(f, dict):
                f["agent"] = "deep-analysis"
        return [f for f in result if isinstance(f, dict)]
