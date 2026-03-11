"""
GitHub integration — clone repos for analysis.

Supports:
- Public repos (no auth needed)
- Private repos (via GITHUB_TOKEN or SSH)
- Branch selection
- Shallow clones for speed
"""

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional


class GitHubSource:
    """Manages cloning and cleanup of GitHub repositories."""

    def __init__(self, repo: str, branch: str = None, token: str = None):
        """
        Args:
            repo: GitHub repo, accepts multiple formats:
                  - "owner/repo"
                  - "https://github.com/owner/repo"
                  - "https://github.com/owner/repo.git"
                  - "git@github.com:owner/repo.git"
            branch: Branch or tag to checkout (default: repo default)
            token: GitHub personal access token (or uses GITHUB_TOKEN env)
        """
        self.owner, self.name = self._parse_repo(repo)
        self.branch = branch
        self.token = token or os.environ.get("GITHUB_TOKEN")
        self.clone_dir: Optional[Path] = None

    def clone(self, target_dir: str = None) -> Path:
        """
        Clone the repository. Returns the path to the cloned repo.

        Uses shallow clone (depth=1) for speed.
        """
        if target_dir:
            self.clone_dir = Path(target_dir)
            self.clone_dir.mkdir(parents=True, exist_ok=True)
        else:
            self.clone_dir = Path(tempfile.mkdtemp(prefix="cba-"))

        clone_url = self._build_url()
        cmd = ["git", "clone", "--depth", "1"]

        if self.branch:
            cmd.extend(["--branch", self.branch])

        cmd.extend([clone_url, str(self.clone_dir)])

        print(f"  Cloning {self.owner}/{self.name}"
              f"{' @ ' + self.branch if self.branch else ''}...")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            )
            if result.returncode != 0:
                error = result.stderr.strip()
                if "could not read Username" in error or "Authentication failed" in error:
                    raise PermissionError(
                        f"Authentication failed for {self.owner}/{self.name}. "
                        f"Set GITHUB_TOKEN env var for private repos."
                    )
                if "not found" in error.lower() or "does not exist" in error.lower():
                    raise FileNotFoundError(
                        f"Repository {self.owner}/{self.name} not found. "
                        f"Check the repo name and your access permissions."
                    )
                if "Remote branch" in error and "not found" in error:
                    raise ValueError(
                        f"Branch '{self.branch}' not found in {self.owner}/{self.name}."
                    )
                raise RuntimeError(f"Git clone failed: {error}")

            print(f"  ✓ Cloned to {self.clone_dir}")
            return self.clone_dir

        except subprocess.TimeoutExpired:
            raise TimeoutError(
                f"Clone timed out after 120s. Repo might be too large — "
                f"try cloning manually first."
            )

    def cleanup(self):
        """Remove the cloned directory."""
        if self.clone_dir and self.clone_dir.exists():
            shutil.rmtree(self.clone_dir, ignore_errors=True)

    def get_info(self) -> dict:
        """Return info about the cloned repo."""
        info = {
            "owner": self.owner,
            "name": self.name,
            "full_name": f"{self.owner}/{self.name}",
            "branch": self.branch or "(default)",
            "url": f"https://github.com/{self.owner}/{self.name}",
        }

        if self.clone_dir and self.clone_dir.exists():
            # Get actual branch name
            try:
                result = subprocess.run(
                    ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                    capture_output=True, text=True,
                    cwd=self.clone_dir,
                )
                if result.returncode == 0:
                    info["branch"] = result.stdout.strip()
            except Exception:
                pass

            # Get latest commit
            try:
                result = subprocess.run(
                    ["git", "log", "-1", "--format=%H %s"],
                    capture_output=True, text=True,
                    cwd=self.clone_dir,
                )
                if result.returncode == 0:
                    parts = result.stdout.strip().split(" ", 1)
                    info["commit_sha"] = parts[0][:8]
                    info["commit_msg"] = parts[1] if len(parts) > 1 else ""
            except Exception:
                pass

        return info

    def _build_url(self) -> str:
        """Build the clone URL, injecting token if available."""
        if self.token:
            return f"https://{self.token}@github.com/{self.owner}/{self.name}.git"
        return f"https://github.com/{self.owner}/{self.name}.git"

    def _parse_repo(self, repo: str) -> tuple[str, str]:
        """Parse various repo formats into (owner, name)."""
        repo = repo.strip().rstrip("/")

        # git@github.com:owner/repo.git
        ssh_match = re.match(r"git@github\.com:(.+)/(.+?)(?:\.git)?$", repo)
        if ssh_match:
            return ssh_match.group(1), ssh_match.group(2)

        # https://github.com/owner/repo[.git]
        https_match = re.match(
            r"https?://github\.com/(.+)/(.+?)(?:\.git)?$", repo
        )
        if https_match:
            return https_match.group(1), https_match.group(2)

        # owner/repo
        simple_match = re.match(r"^([^/]+)/([^/]+)$", repo)
        if simple_match:
            return simple_match.group(1), simple_match.group(2)

        raise ValueError(
            f"Can't parse repo: '{repo}'. "
            f"Use 'owner/repo' or 'https://github.com/owner/repo'"
        )


def list_branches(repo: str, token: str = None) -> list[str]:
    """List available branches for a repo (requires git ls-remote)."""
    token = token or os.environ.get("GITHUB_TOKEN")
    if token:
        url = f"https://{token}@github.com/{repo}.git"
    else:
        url = f"https://github.com/{repo}.git"

    try:
        result = subprocess.run(
            ["git", "ls-remote", "--heads", url],
            capture_output=True, text=True, timeout=15,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
        if result.returncode != 0:
            return []

        branches = []
        for line in result.stdout.strip().split("\n"):
            if line and "refs/heads/" in line:
                branch = line.split("refs/heads/")[-1]
                branches.append(branch)
        return sorted(branches)

    except Exception:
        return []
