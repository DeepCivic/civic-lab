"""Walk a repository and yield scannable text files, plus the list of every path seen (for presence checks).

Noise control happens here, before any detector runs:
- inside a git work tree, only files git would track are read (``.gitignore`` is honoured);
- build output, dependency and cache directories are skipped even when committed;
- minified or generated bundles are skipped;
- a file containing ``ism-review: ignore-file`` is skipped; a line containing ``ism-review: ignore`` is suppressed.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", ".venv", "venv", "env", "__pycache__", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", "dist", "build", ".next", ".nuxt", ".svelte-kit", "target", "vendor", ".terraform", ".tox",
    "coverage", ".idea", ".vscode", "bower_components", ".gradle", "Pods", ".cache", ".vercel", ".output", "out",
    ".netlify", ".turbo", ".serverless", ".aws-sam", "site-packages", "_build", "cdk.out",
}
TEXT_EXT = {
    ".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".vue", ".svelte", ".astro", ".html", ".htm", ".php", ".rb",
    ".go", ".java", ".kt", ".swift", ".cs", ".rs", ".scala", ".sql", ".tf", ".tfvars", ".hcl", ".yaml", ".yml", ".json",
    ".toml", ".ini", ".cfg", ".conf", ".properties", ".xml", ".gradle", ".md", ".mdx", ".txt", ".rst", ".adoc", ".sh",
    ".bash", ".ps1", ".j2", ".jinja", ".env", ".dockerfile", ".lock", ".mod", ".sum", ".csv",
}
NAMED = {"dockerfile", "makefile", "procfile", "gemfile", "jenkinsfile", "pipfile", "caddyfile"}
UNREAD_DOC_EXT = {".pdf", ".docx", ".doc", ".odt", ".rtf", ".pptx", ".ppt", ".odp", ".xlsx", ".xls", ".vsdx"}
GENERATED_SUFFIXES = (".min.js", ".min.css", ".bundle.js", ".chunk.js", ".map")
LOCKFILE_NAMES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb", "bun.lock", "uv.lock", "poetry.lock", "pipfile.lock",
                  "pdm.lock", "cargo.lock", "go.sum", "gemfile.lock", "composer.lock", "gradle.lockfile", "packages.lock.json"}
MAX_BYTES = 1_000_000
IGNORE_FILE = "ism-review: ignore-file"


@dataclass
class SourceFile:
    rel: str
    text: str

    @property
    def lower_rel(self) -> str:
        return self.rel.lower()

    @property
    def name(self) -> str:
        return self.rel.rsplit("/", 1)[-1].lower()

    @property
    def ext(self) -> str:
        n = self.name
        return "." + n.rsplit(".", 1)[1] if "." in n else ""

    @property
    def is_test(self) -> bool:
        r = "/" + self.lower_rel
        return any(t in r for t in ("/test", "/tests/", "/spec/", "/__tests__/", "/fixtures/", "/mocks/", "_test.", ".test.", ".spec.",
                                     "/testdata/", "/e2e/", "/examples/", "/example/"))

    @property
    def is_prose(self) -> bool:
        return self.ext in {".md", ".mdx", ".txt", ".rst", ".adoc", ".html", ".htm"}

    @property
    def lines(self) -> list[str]:
        return self.text.splitlines()


@dataclass
class WalkResult:
    files: list[SourceFile]
    all_paths: list[str]
    skipped_large: list[str] = field(default_factory=list)
    unread_documents: list[str] = field(default_factory=list)
    skipped_generated: int = 0
    ignored_by_marker: list[str] = field(default_factory=list)
    total_seen: int = 0
    truncated: bool = False
    gitignore_honoured: bool = False


def _git_listing(root: Path) -> list[str] | None:
    try:
        r = subprocess.run(["git", "-C", str(root), "ls-files", "-co", "--exclude-standard", "-z"],
                           capture_output=True, timeout=60, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    return sorted(p for p in r.stdout.decode("utf-8", "replace").split("\0") if p)


def _os_listing(root: Path) -> list[str]:
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.endswith(".egg-info"))
        for name in sorted(filenames):
            out.append((Path(dirpath) / name).relative_to(root).as_posix())
    return out


def walk(root: Path, max_files: int = 20000, extra_excludes: list[str] | None = None, use_git: bool = True) -> WalkResult:
    root = root.resolve()
    excludes = [e.strip("/") for e in (extra_excludes or [])]
    listing = _git_listing(root) if use_git else None
    res = WalkResult([], [], gitignore_honoured=listing is not None)
    for rel in listing if listing is not None else _os_listing(root):
        parts = rel.split("/")
        if any(p in SKIP_DIRS or p.endswith(".egg-info") for p in parts[:-1]):
            continue
        if any(rel == e or rel.startswith(e + "/") for e in excludes):
            continue
        res.total_seen += 1
        res.all_paths.append(rel)
        name = parts[-1].lower()
        ext = ("." + name.rsplit(".", 1)[1]) if "." in name else ""
        if ext in UNREAD_DOC_EXT:
            res.unread_documents.append(rel)
            continue
        if ext not in TEXT_EXT and name not in NAMED and not name.startswith(".env") and not name.startswith("dockerfile"):
            continue
        p = root / rel
        try:
            size = p.stat().st_size
        except OSError:
            continue
        if size > MAX_BYTES:
            res.skipped_large.append(rel)
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if name.endswith(GENERATED_SUFFIXES) or (len(text) > 5000 and len(text) / (text.count("\n") + 1) > 400):
            res.skipped_generated += 1
            continue
        if IGNORE_FILE in text:
            res.ignored_by_marker.append(rel)
            continue
        res.files.append(SourceFile(rel, text))
        if len(res.files) >= max_files:
            res.truncated = True
            break
    return res
