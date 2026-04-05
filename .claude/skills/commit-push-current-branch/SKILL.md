---
name: commit-push-current-branch
description: "Use when you need to commit and push all current changes on the active branch in this repository."
---

# Commit and Push Current Branch

Use this skill when the goal is to capture the current working tree in a single commit and push it to the branch that is already checked out.

## Workflow
1. Run `git status --short --branch` to confirm the current branch and pending changes.
2. Review the diff if needed to make sure unrelated files are not being staged accidentally.
3. Stage all intended changes with `git add -A`.
4. Create one commit that reflects the current work.
5. Push the current branch to its upstream remote.
6. Verify the push succeeded and report the commit hash and branch name.

## Guidance
- Prefer one commit for one completed implementation pass unless the user asked for multiple commits.
- Do not rewrite history unless explicitly requested.
- Do not discard or revert unrelated changes.
- If the branch has no upstream yet, set it on first push.
- Keep the commit message short, concrete, and outcome-focused.

## Suggested Commit Message Pattern
`feat: add second brain knowledge base`

## Suggested Push Command
`git push -u origin HEAD`
