# Changelog

## 0.2.0 (unreleased)

The server is now a privacy review first, and a threshold assessment second.

- **New main tool, `review_project`.** It reads code, documents and recorded observations, and returns
  findings at three levels (critical: resembles a final decision that went against the entity; high:
  reads as an APP contravention at face value; caution: not enough information). It also returns open
  questions with the evidence that would settle each, a coverage report, and threshold readiness. It
  needs no answers.
- **New tools:** `interrogate` and `list_observation_kinds`.
- **Documents are read.** Markdown, text and HTML passages that bear on privacy are flagged for reading.
  PDFs and Office files are listed as unread instead of being skipped silently.
- **Observations.** Facts recorded from any material, with their source, answer threshold questions
  and can match decided-case patterns.
- **Threshold assessment fixes.** SaaS SDKs found in code no longer recommend a PIA on their own, and
  no longer count twice (third party and overseas). Questions are no longer reported as "not
  detected" when no code was examined. A new answer, `indicated`, covers questions documents mention
  but nobody has confirmed.
- **Prompts** answer from the evidence first and ask the user only what is left, instead of working
  through every threshold question.
- New CLI commands `review` (with `--fail-on` for CI) and `kinds`. `threshold` accepts `--doc` and
  `--observations`.
- **Renamed** from `privacy-impact-threshold-au` to `au-privacy-review`. The package, module, command,
  environment variables (`AU_PRIVACY_REVIEW_ROOTS`, `AU_PRIVACY_REVIEW_LIVE`) and the ignore markers
  (`privacy-review: ignore`) all changed.
- Documentation reorganised into `docs/`, with `RESEARCH.md` describing what the knowledge base contains
  and how it was made. The research working files are no longer in this folder.
- **Docker image and MCP Registry entry.** The image mounts the project at `/work` and limits the server to
  it. `server.json` lists the image only; the package is not published to PyPI.
- `review_project` accepts `project_name`.

## 0.1.0

First version: a threshold assessment from a code scan and the team's answers to 17 questions.
