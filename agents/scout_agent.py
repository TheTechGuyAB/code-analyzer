"""
Scout Agent — Fast stack detection using cheap/fast models.
Phase: scan (uses fast models like Groq Llama or Gemini Flash)
"""

from agents.base_agent import BaseAgent


class ScoutAgent(BaseAgent):
    AGENT_NAME = "scout"
    AGENT_VERSION = "2.0"

    def analyze(self, files: list, stats: dict, tree: list[str]) -> dict:
        self._log("Stack detection (fast model)...")

        config_files = [
            f for f in files
            if f.relative.lower().split("/")[-1] in {
                "package.json", "tsconfig.json", "pyproject.toml", "pipfile",
                "gemfile", "cargo.toml", "go.mod", "pom.xml", "build.gradle",
                "docker-compose.yml", "docker-compose.yaml", "dockerfile",
                "global.json", "directory.build.props",
                "appsettings.json", "nuget.config", "program.cs", "startup.cs",
                "webpack.config.js", "vite.config.ts", "vite.config.js",
                "next.config.js", "nuxt.config.ts", "angular.json",
                "requirements.txt", "setup.py", "setup.cfg",
            } or f.ext in {".csproj", ".sln", ".fsproj"}
        ]

        prompt = f"""Analyze this codebase and identify the complete tech stack.

## File stats
Total files: {stats['total_files']} ({stats['total_size_kb']} KB)
Extensions: {', '.join(f'{ext}: {n}' for ext, n in sorted(stats['extensions'].items(), key=lambda x: -x[1]))}

## Directories
{chr(10).join(tree[:60])}

## Config files
{self._format_files(config_files, max_total=25000)}

Return JSON:
{{
  "languages": [{{"name": "C#", "version": "12", "percentage": 65}}],
  "frameworks": [{{"name": "ASP.NET Core", "version": "8.0", "category": "backend"}}],
  "package_managers": ["NuGet"],
  "databases": ["SQL Server"],
  "infrastructure": {{
    "containerized": true,
    "ci_cd": "GitHub Actions",
    "cloud_provider": "Azure",
    "hosting": null
  }}
}}

Categories: frontend, backend, testing, build, orm, cms, other.
Only report what you can detect. Be precise about versions."""

        system = (
            "You are a tech stack detection agent. Analyze config files and project "
            "structure to identify languages, frameworks, databases, infrastructure. "
            "Be precise. Only report what is evidenced."
        )

        return self._chat_json("scan", system, prompt)
