"""Walk a repository or deployment directory and yield scannable text files.

Noise control lives here, before any detector runs:
- inside a git work tree, only files git would track are read (``.gitignore`` is honoured);
- build output, dependency and cache directories are skipped even when committed;
- minified or generated bundles are skipped (they repeat source that is scanned elsewhere);
- a file containing the marker ``privacy-review: ignore-file`` is skipped, and a finding on a
  line containing ``privacy-review: ignore`` is suppressed (see detectors).
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", ".venv", "venv", "env", "__pycache__", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", "dist", "build", ".next", ".nuxt", ".svelte-kit", "target", "vendor", ".terraform", ".tox",
    "coverage", ".idea", ".vscode", "bower_components", ".gradle", "Pods", ".cache",
    # build and deploy output
    ".vercel", ".output", "out", ".netlify", ".turbo", ".parcel-cache", ".serverless", ".aws-sam", ".expo",
    ".angular", ".docusaurus", "storybook-static", "site-packages", "_build", ".wrangler", ".firebase", "cdk.out",
}
TEXT_EXT = {
    ".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".vue", ".svelte", ".astro", ".html", ".htm", ".php", ".rb",
    ".go", ".java", ".kt", ".kts", ".swift", ".m", ".cs", ".rs", ".scala", ".sql", ".prisma", ".graphql", ".gql",
    ".tf", ".tfvars", ".hcl", ".yaml", ".yml", ".json", ".toml", ".ini", ".cfg", ".conf", ".properties",
    ".xml", ".plist", ".gradle", ".md", ".mdx", ".txt", ".rst", ".adoc", ".csv", ".ipynb", ".sh", ".bash", ".ps1", ".liquid",
    ".hbs", ".handlebars", ".ejs", ".njk", ".jinja", ".j2", ".twig", ".erb", ".mustache", ".dockerfile", ".env", ".mjml",
}
NAMED = {"dockerfile", "makefile", "procfile", ".env", "gemfile", "podfile", "jenkinsfile"}
# Documents the scanner cannot read as text. They are listed (not parsed) so a review can say they were not examined;
# the agent can read them and submit what they say as observations.
UNREAD_DOC_EXT = {".pdf", ".docx", ".doc", ".odt", ".rtf", ".pptx", ".ppt", ".odp", ".xlsx", ".xls", ".vsdx", ".pages", ".key"}
DUMP_EXT = {".sql", ".csv", ".parquet", ".dump", ".bak", ".sqlite", ".db", ".jsonl", ".xlsx"}
GENERATED_SUFFIXES = (".min.js", ".min.css", ".bundle.js", ".chunk.js", ".map", "-lock.json", ".lock")
MAX_BYTES = 1_000_000
IGNORE_FILE = "privacy-review: ignore-file"


@dataclass
class SourceFile:
    path: Path
    rel: str
    text: str

    @property
    def lower_rel(self) -> str:
        return self.rel.lower()

    @property
    def is_test(self) -> bool:
        r = "/" + self.lower_rel
        return any(t in r for t in ("/test", "/tests/", "/spec/", "/__tests__/", "/fixtures/", "/mocks/", "_test.",
                                     ".test.", ".spec.", "/testdata/", "/e2e/", "/cypress/"))

    @property
    def is_fixture(self) -> bool:
        r = "/" + self.lower_rel
        return any(t in r for t in ("/fixtures/", "/fixture/", "/seed", "/seeds/", "/testdata/", "/sample", "/mock",
                                     "/demo", "/factories/", "faker"))

    @property
    def is_prose(self) -> bool:
        return self.path.suffix.lower() in {".md", ".mdx", ".txt", ".rst", ".adoc"}

    @property
    def is_doc(self) -> bool:
        return self.path.suffix.lower() in {".md", ".mdx", ".txt", ".rst", ".adoc", ".html", ".htm"}


@dataclass
class WalkResult:
    files: list[SourceFile]
    skipped_large: list[str]
    binary_dumps: list[str]
    total_seen: int
    truncated: bool
    gitignore_honoured: bool = False
    skipped_generated: list[str] = field(default_factory=list)
    ignored_by_marker: list[str] = field(default_factory=list)
    unread_documents: list[str] = field(default_factory=list)


def _looks_generated(name: str, text: str) -> bool:
    if name.endswith(GENERATED_SUFFIXES):
        return True
    if len(text) < 5000:
        return False
    lines = text.count("\n") + 1
    return len(text) / lines > 400  # minified: very long average line


def _git_listing(root: Path) -> list[str] | None:
    """Files git would track under root (tracked plus untracked-not-ignored), or None if not a git tree."""
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
    res = WalkResult([], [], [], 0, False, gitignore_honoured=listing is not None)
    for rel in listing if listing is not None else _os_listing(root):
        parts = rel.split("/")
        if any(p in SKIP_DIRS or p.endswith(".egg-info") for p in parts[:-1]):
            continue
        if any(rel == e or rel.startswith(e + "/") for e in excludes):
            continue
        p = root / rel
        name = parts[-1]
        res.total_seen += 1
        ext = p.suffix.lower()
        if ext in UNREAD_DOC_EXT and ext not in DUMP_EXT:
            res.unread_documents.append(rel)
            continue
        if ext in DUMP_EXT - TEXT_EXT:
            res.binary_dumps.append(rel)
            continue
        if ext not in TEXT_EXT and name.lower() not in NAMED and not name.lower().startswith(".env"):
            continue
        try:
            size = p.stat().st_size
        except OSError:
            continue
        if size > MAX_BYTES:
            res.skipped_large.append(rel)
            if ext in DUMP_EXT:
                res.binary_dumps.append(rel)
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if _looks_generated(name.lower(), text):
            res.skipped_generated.append(rel)
            continue
        if IGNORE_FILE in text:
            res.ignored_by_marker.append(rel)
            continue
        res.files.append(SourceFile(p, rel, text))
        if len(res.files) >= max_files:
            res.truncated = True
            break
    return res
