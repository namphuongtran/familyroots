#!/usr/bin/env bash
set -euo pipefail

# scripts/git_sync.sh
# Usage: ./scripts/git_sync.sh "type(scope): message"
# Stages all changes, creates a commit, and pushes to the current branch.

if [ $# -lt 1 ]; then
    echo "Error: commit message is required."
    echo "Usage: $0 \"type(scope): message\""
    exit 1
fi

commit_message=$1
current_branch=$(git branch --show-current)

if [ -z "$current_branch" ]; then
    echo "Error: unable to determine the current branch."
    exit 1
fi

if [ -z "$(git status --porcelain)" ]; then
    echo "Nothing to commit."
    exit 0
fi

echo "Staging all changes..."
git add -A

echo "Creating commit on '$current_branch'..."
git commit -m "$commit_message"

echo "Pushing to origin/$current_branch..."
git push origin "$current_branch"

echo "Done."
