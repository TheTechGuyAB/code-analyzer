"""
Architect Agent — Deep architecture & code quality analysis.
Phase: analyze (uses mid-tier models like Claude Sonnet or GPT-4o)

Examines: coupling, patterns, error handling, SOLID violations,
external API handling, code organization, technical debt.
"""

from agents.base_agent import BaseAgent


class ArchitectAgent(BaseAgent):
    AGENT_NAME = "architect"
    AGENT_VERSION = "2.0"

    def analyze(self, files: list, stack: dict, user_query: str = None,
                guidelines: str = None) -> list[dict]:
        self._log("Architecture analysis (mid-tier model)...")

        arch_files = self._select_files(files)
        self._log(f"Selected {len(arch_files)} files")

        stack_summary = self._stack_str(stack)

        query_section = ""
        if user_query:
            query_section = f"""
## DEVELOPER'S CONCERN
"{user_query}"
Prioritize findings related to this concern.
"""

        guidelines_section = ""
        if guidelines:
            guidelines_section = f"""
## TEAM GUIDELINES TO CHECK AGAINST
The team has established these guidelines. Check if the codebase follows them:
{guidelines}
Report violations as findings with category "architecture" or "resilience".
"""

        prompt = f"""Analyze this codebase for architectural issues and code quality problems.

## Stack
{stack_summary}
{query_section}{guidelines_section}
## Source Files
{self._format_files(arch_files, max_total=80000)}

Return a JSON array of findings:
[{{
  "id": "ARCH-001",
  "severity": "critical|warning|info",
  "category": "architecture|performance|security|resilience|maintainability|testing|dependencies|configuration|observability",
  "title": "Short title (max 120 chars)",
  "description": "Detailed description",
  "affected_files": ["path/to/file.cs"],
  "evidence": "Code snippet or proof",
  "recommendation": "How to fix",
  "effort": "trivial|small|medium|large|epic",
  "agent": "architect",
  "tags": ["coupling", "solid-violation"]
}}]

ANALYZE FOR:
1. Tight coupling / missing abstraction layers
2. God classes / files doing too much
3. Missing error handling — especially external API calls with no try/catch, no retry, no timeout
4. Hardcoded config / secrets in code
5. Missing or inadequate logging/observability
6. N+1 query patterns
7. Missing async/await where appropriate
8. DI issues / missing interfaces
9. Outdated or risky dependency patterns
10. Direct HttpClient usage without IHttpClientFactory
11. Missing health checks
12. External API calls without resilience patterns (retry, circuit breaker, fallback, timeout)
13. Catch blocks that swallow exceptions silently
14. Business logic in controllers
15. Missing input validation

THINK ERRORS: Look for logical mistakes, patterns that will cause runtime failures,
race conditions, null reference risks, and incorrect assumptions in the code.

Severity: critical = outage/data-loss risk, warning = should fix, info = suggestion.
Be specific — reference actual files and code. Don't invent issues."""

        system = (
            "You are a senior software architect with 20+ years across .NET, Node.js, "
            "Python, and cloud architectures. You perform evidence-based code reviews. "
            "Every finding must reference actual code. You understand common anti-patterns "
            "and can spot subtle issues like race conditions, missing error handling in "
            "external integrations, and architectural drift. Return findings as JSON array."
        )

        result = self._chat_json("analyze", system, prompt)

        if isinstance(result, dict) and "findings" in result:
            result = result["findings"]
        if not isinstance(result, list):
            result = [result]
        return result

    def _select_files(self, files: list) -> list:
        priority_names = {
            "program.cs", "startup.cs", "appsettings.json",
            "package.json", "tsconfig.json", "docker-compose.yml",
        }
        priority_exts = {".cs", ".ts", ".tsx", ".py", ".go", ".java", ".rs", ".rb", ".php"}
        config_exts = {".json", ".yaml", ".yml", ".toml", ".xml", ".config"}

        high = [f for f in files if f.relative.lower().split("/")[-1] in priority_names]
        code = [f for f in files if f.ext in priority_exts and f not in high]
        config = [f for f in files if f.ext in config_exts and f not in high]

        code.sort(key=lambda f: f.size, reverse=True)
        return (high + code[:120] + config[:30])[:200]

    def _stack_str(self, stack: dict) -> str:
        lines = []
        langs = stack.get("languages", [])
        if langs:
            lines.append("Languages: " + ", ".join(
                f"{l['name']} {l.get('version', '')}" for l in langs
            ))
        fws = stack.get("frameworks", [])
        if fws:
            lines.append("Frameworks: " + ", ".join(
                f"{f['name']} {f.get('version', '')} [{f.get('category', '')}]"
                for f in fws
            ))
        dbs = stack.get("databases", [])
        if dbs:
            db_names = [d["name"] if isinstance(d, dict) else str(d) for d in dbs]
            lines.append(f"Databases: {', '.join(db_names)}")
        return "\n".join(lines)
