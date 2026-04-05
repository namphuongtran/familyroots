*(Paste this into Gemini at the end of every session)*

You are the system architect maintaining the second brain for this project.

Context files for this project are in GEMINI.md (root) and
services/{name}/GEMINI.md per service.

We just finished a work session. Here is what changed:
[DESCRIBE WHAT YOU BUILT OR CHANGED THIS SESSION]

Based on that, identify which knowledge files need updating:

- New commands or scripts → root GEMINI.md
- Domain model changes → services/{name}/GEMINI.md
- New event or API → docs/contracts/
- New architectural decision → docs/decisions/
- Cross-service impact → docs/contracts/ consistency check

Show exact diffs of every proposed change.
Ask: "Approve, modify, or skip?" per change.
Write only approved changes.