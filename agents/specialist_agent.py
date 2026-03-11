"""
Specialist Agent — Focused analysis on resilience, performance, or security.
Phase: specialist (uses mid-tier models)
"""

from agents.base_agent import BaseAgent

CONFIGS = {
    "resilience": {
        "system": (
            "You are a resilience engineering specialist. You focus on failure handling: "
            "external API calls, timeouts, retry policies, circuit breakers, fallbacks, "
            "graceful degradation, caching strategies. You've seen production outages "
            "caused by every missing pattern."
        ),
        "focus": [
            "External HTTP calls without retry/timeout/circuit breaker",
            "Missing fallback when external services fail",
            "No caching for external API responses",
            "Missing health checks for dependencies",
            "Page crashes when one dependency is down (no graceful degradation)",
            "Fire-and-forget without error handling",
            "No dead letter queue for failed messages",
            "Database connections without retry/pooling config",
            "HttpClient without IHttpClientFactory (socket exhaustion)",
            "Missing Polly or equivalent resilience library",
            "Unbounded timeouts (default HttpClient 100s timeout)",
        ],
        "prefix": "RES",
    },
    "performance": {
        "system": (
            "You are a performance specialist. You find N+1 queries, missing caching, "
            "synchronous blocking, memory issues, and scalability bottlenecks."
        ),
        "focus": [
            "N+1 query patterns (loading in loops)",
            "Missing database indexes (from query patterns)",
            "Synchronous blocking where async needed",
            "Missing caching for expensive operations",
            "Large allocations in hot paths",
            "String concat in loops instead of StringBuilder",
            "Loading full collections when count/exists needed",
            "Missing pagination for large datasets",
            "Client-side LINQ evaluation",
            "Missing response compression",
            "Blocking calls in async context (.Result, .Wait())",
        ],
        "prefix": "PERF",
    },
    "security": {
        "system": (
            "You are an application security specialist following OWASP guidelines. "
            "You focus on real, exploitable vulnerabilities."
        ),
        "focus": [
            "Hardcoded secrets/API keys/connection strings",
            "SQL injection (string concatenation in queries)",
            "Missing input validation/sanitization",
            "Overly permissive CORS",
            "Missing auth on endpoints",
            "Insecure deserialization",
            "Missing HTTPS enforcement",
            "Sensitive data in logs",
            "Missing security headers (CSP, HSTS)",
            "Outdated packages with known CVEs",
            "JWT validation issues",
        ],
        "prefix": "SEC",
    },
}


class SpecialistAgent(BaseAgent):
    AGENT_NAME = "specialist"
    AGENT_VERSION = "2.0"

    def __init__(self, specialty: str, **kwargs):
        super().__init__(**kwargs)
        if specialty not in CONFIGS:
            raise ValueError(f"Unknown specialty: {specialty}")
        self.specialty = specialty
        self.config = CONFIGS[specialty]
        self.AGENT_NAME = f"specialist-{specialty}"

    def analyze(self, files: list, stack: dict, user_query: str = None) -> list[dict]:
        self._log(f"{self.specialty} analysis...")

        relevant = self._select_relevant(files)
        self._log(f"Selected {len(relevant)} relevant files")
        if not relevant:
            return []

        focus_list = "\n".join(f"- {f}" for f in self.config["focus"])
        stack_str = ", ".join(l["name"] for l in stack.get("languages", []))
        fw_str = ", ".join(f["name"] for f in stack.get("frameworks", []))

        query_section = ""
        if user_query:
            query_section = f'\n## USER CONCERN\n"{user_query}"\n'

        prompt = f"""Analyze for {self.specialty} issues.

## Stack: {stack_str} / {fw_str}
{query_section}
## Focus Areas
{focus_list}

## Source Files
{self._format_files(relevant, max_total=60000)}

Return JSON array of findings:
[{{
  "id": "{self.config['prefix']}-001",
  "severity": "critical|warning|info",
  "category": "{self.specialty}",
  "title": "Short description",
  "description": "Detailed explanation",
  "affected_files": ["path"],
  "evidence": "Code proof",
  "recommendation": "Fix",
  "effort": "trivial|small|medium|large|epic",
  "agent": "specialist-{self.specialty}",
  "tags": []
}}]

Only report provable issues. Reference actual files and code."""

        result = self._chat_json("specialist", self.config["system"], prompt)

        if isinstance(result, dict) and "findings" in result:
            result = result["findings"]
        if not isinstance(result, list):
            result = [result]
        return result

    def _select_relevant(self, files: list) -> list:
        keywords_map = {
            "resilience": [
                "httpclient", "fetch(", "axios", "requests.", "aiohttp",
                "service", "gateway", "client", "api", "external",
                "retry", "polly", "circuit", "resilience", "health",
                "startup", "program", "appsettings", "httpwebrequest",
            ],
            "performance": [
                "repository", "query", "dbcontext", "database", "foreach",
                "select", "include", "tolist", "async", "await", "task",
                "cache", "redis", "controller", "linq", "iqueryable",
                ".result", ".wait()", "getawaiter",
            ],
            "security": [
                "password", "secret", "key", "token", "auth",
                "connection", "connectionstring", "controller",
                "authorize", "cors", "middleware", "sql", "query",
                "command", "input", "validate", "login", "jwt",
                "cookie", "session",
            ],
        }
        keywords = keywords_map.get(self.specialty, [])
        scored = []
        for f in files:
            if f.content is None:
                continue
            low = f.content.lower() + f.relative.lower()
            score = sum(1 for kw in keywords if kw in low)
            if score > 0:
                scored.append((score, f))
        scored.sort(key=lambda x: -x[0])
        return [f for _, f in scored[:100]]
