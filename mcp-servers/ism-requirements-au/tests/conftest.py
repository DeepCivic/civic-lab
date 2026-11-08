"""Fixture repositories are written at test time. Secret-shaped strings are assembled from fragments so no credential-like
literal is committed to the repository."""

from pathlib import Path

import pytest

AWS_KEY = "AKIA" + "J5Q2W7E9R4T6Y8U1"
DB_PASSWORD = "Tr0ub4dor" + "Horse9Battery"
SHARED = "s3cr3t" + "Value" + "ABCDEF123456"


def write(root: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return root


@pytest.fixture(scope="session")
def bad_repo(tmp_path_factory) -> Path:
    return write(tmp_path_factory.mktemp("bad"), {
        "README.md": "# Citizen portal\nA web service for citizens.\n",
        "infra/main.tf": '''resource "aws_security_group" "web" {
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
resource "aws_s3_bucket" "files" {
  acl = "public-read"
}
resource "aws_cognito_user_pool" "pool" {
  mfa_configuration = "OFF"
}
''',
        "app/settings.py": f'''SESSION_COOKIE_SECURE = False
DATABASE_URL = "postgres://app:{DB_PASSWORD}@db.internal/portal"
aws_access_key_id = "{AWS_KEY}"
SSL_MIN = "TLSv1.0"
''',
        "app/views.py": '''import pickle
from flask import Flask, request
app = Flask(__name__)

@app.route("/q")
def q(cur):
    cur.execute(f"SELECT * FROM t WHERE n = '{request.args['q']}'")
    return pickle.loads(request.data)
''',
        "requirements.txt": "flask\nrequests>=2\n",
        "Dockerfile": "FROM python:latest\nRUN curl https://example.org/install.sh | sh\n",
        "docker-compose.yml": "services:\n  db:\n    image: postgres:16\n    environment:\n      POSTGRES_PASSWORD: postgres\n",
        ".github/workflows/ci.yml": "name: ci\non: push\njobs:\n  t:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@main\n      - run: pytest\n",
        "config/dev.env": f"API_TOKEN={SHARED}\n",
        "config/prod.env": f"API_TOKEN={SHARED}\n",
        "agent.py": "from langchain_community.tools import ShellTool\ntools = [ShellTool()]\n",
        "docs/system-security-plan.pdf": "not really a pdf",
    })


@pytest.fixture(scope="session")
def clean_repo(tmp_path_factory) -> Path:
    return write(tmp_path_factory.mktemp("clean"), {
        "README.md": "# Records library\nA command-line tool.\n",
        "docs/system-security-plan.md": "# System security plan\nPurpose, boundary, management.\n",
        "docs/incident-response-plan.md": "# Cyber security incident response plan\n",
        "docs/continuous-monitoring-plan.md": "# Continuous monitoring plan\n",
        "docs/security-risk-management-plan.md": "# Security risk management plan\n",
        "docs/ssp-annex.md": "# SSP annex: controls matrix\n",
        "pyproject.toml": '[project]\nname = "x"\ndependencies = ["requests==2.32.3"]\n',
        "uv.lock": "version = 1\n",
        "requirements.txt": "requests==2.32.3\n",
        "Dockerfile": "FROM python:3.13-slim@sha256:" + "0" * 64 + "\nCOPY . /app\n",
        "otel.yaml": "exporters:\n  otlp: {}\n",
        ".github/dependabot.yml": "version: 2\n",
        ".github/workflows/ci.yml": "name: ci\non: push\njobs:\n  t:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n"
                                    "      - run: pip-audit\n      - run: cyclonedx-py environment -o sbom.cdx.json\n",
    })
