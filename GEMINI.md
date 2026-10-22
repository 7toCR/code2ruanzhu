# Gemini Project Context

This repository is a Markdown-first project that publishes the ruanzhu-docs agent skill for preparing Chinese software copyright (软著) registration materials from source code.

## How To Work Here

- Use `skills/ruanzhu-docs/SKILL.md` as the main workflow reference.
- Load files under `skills/ruanzhu-docs/references/` only when the task requires the specific rule set.
- Preserve source-code fidelity: every parameter in a design document must be traceable to the code; never invent features, applicant information, dates, publication details, or screenshots.
- Do not commit users' source code, generated materials, personal or company data, API keys, tokens, local usernames, or local absolute paths.
- Keep Markdown UTF-8 and maintain the repository's Simplified Chinese terminology.
