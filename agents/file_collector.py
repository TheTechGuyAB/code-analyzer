"""
File collector — scans a codebase directory and collects metadata + content.
"""

import os
from pathlib import Path
from typing import Optional


SKIP_DIRS = {
    "node_modules", ".git", ".svn", ".hg", "bin", "obj", "dist", "build",
    ".next", ".nuxt", "__pycache__", ".pytest_cache", ".mypy_cache",
    "vendor", "packages", ".vs", ".idea", ".vscode", "coverage",
    "wwwroot/lib", "artifacts", ".terraform", ".serverless",
    "venv", ".venv", "env", ".env", "target", "TestResults",
    "migrations", "Migrations",  # Usually auto-generated
}

CODE_EXTENSIONS = {
    ".cs", ".csproj", ".sln", ".razor", ".cshtml",
    ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    ".py", ".pyx", ".pyi",
    ".html", ".htm", ".css", ".scss", ".sass", ".less", ".vue", ".svelte",
    ".json", ".yaml", ".yml", ".toml", ".xml", ".env.example",
    ".config", ".ini", ".cfg",
    ".dockerfile", ".sh", ".bash", ".ps1", ".psm1",
    ".php", ".blade.php",
    ".rb", ".erb", ".gemspec",
    ".go", ".mod", ".sum",
    ".rs",
    ".java", ".kt", ".kts", ".gradle",
    ".sql",
    ".md", ".rst", ".txt",
}

IMPORTANT_FILES = {
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
    "Makefile", "Rakefile", "Gemfile", "Pipfile", "pyproject.toml",
    "package.json", "tsconfig.json", "webpack.config.js", "vite.config.ts",
    "vite.config.js", "jest.config.js", "vitest.config.ts",
    "nuget.config", "global.json", "Directory.Build.props",
    "appsettings.json", "appsettings.Development.json",
    "Program.cs", "Startup.cs",
    "Jenkinsfile", ".gitlab-ci.yml",
    "nginx.conf", "web.config",
    "README.md", "CHANGELOG.md", "CLAUDE.md",
}

MAX_FILE_SIZE = 100_000


class FileInfo:
    def __init__(self, path: Path, relative: str, content: Optional[str], size: int, ext: str):
        self.path = path
        self.relative = relative
        self.content = content
        self.size = size
        self.ext = ext

    def to_dict(self):
        return {
            "path": self.relative,
            "size": self.size,
            "ext": self.ext,
            "has_content": self.content is not None,
        }


class FileCollector:
    def __init__(self, root: Path, max_files: int = 200):
        self.root = root
        self.max_files = max_files
        self.files: list[FileInfo] = []
        self.skipped_count = 0
        self.total_size = 0
        self.tree_summary: list[str] = []

    def collect(self) -> list[FileInfo]:
        all_candidates: list[tuple[Path, str]] = []

        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [
                d for d in dirnames
                if d not in SKIP_DIRS and not d.startswith(".")
            ]

            rel_dir = os.path.relpath(dirpath, self.root)
            if rel_dir == ".":
                rel_dir = ""

            for fname in filenames:
                full = Path(dirpath) / fname
                rel = os.path.join(rel_dir, fname) if rel_dir else fname
                ext = self._get_ext(fname)

                if fname in IMPORTANT_FILES or ext in CODE_EXTENSIONS:
                    all_candidates.append((full, rel))

        # Prioritize important files first
        all_candidates.sort(key=lambda x: (
            0 if x[0].name in IMPORTANT_FILES else 1,
            x[1],
        ))

        for full, rel in all_candidates[:self.max_files]:
            self._collect_file(full, rel)

        self.skipped_count = max(0, len(all_candidates) - self.max_files)
        self._build_tree()
        return self.files

    def _collect_file(self, full: Path, rel: str):
        ext = self._get_ext(full.name)
        try:
            size = full.stat().st_size
        except OSError:
            return
        content = None

        if size <= MAX_FILE_SIZE:
            try:
                content = full.read_text(encoding="utf-8", errors="replace")
            except Exception:
                pass

        self.files.append(FileInfo(
            path=full, relative=rel, content=content, size=size, ext=ext
        ))
        self.total_size += size

    def _get_ext(self, filename: str) -> str:
        name = filename.lower()
        if name.endswith(".blade.php"):
            return ".blade.php"
        return Path(name).suffix

    def _build_tree(self):
        dirs_seen = set()
        for f in self.files:
            parts = Path(f.relative).parts
            for i in range(len(parts) - 1):
                d = "/".join(parts[: i + 1])
                dirs_seen.add(d)
        self.tree_summary = sorted(dirs_seen)

    def get_stats(self) -> dict:
        ext_counts: dict[str, int] = {}
        for f in self.files:
            ext_counts[f.ext] = ext_counts.get(f.ext, 0) + 1
        return {
            "total_files": len(self.files),
            "skipped_files": self.skipped_count,
            "total_size_kb": round(self.total_size / 1024, 1),
            "extensions": ext_counts,
            "directories": len(self.tree_summary),
        }
