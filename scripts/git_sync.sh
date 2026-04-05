#!/bin/bash
# scripts/git_sync.sh
# Usage: ./scripts/git_sync.sh "Your commit message"
# Commits all changes and pushes to the current branch.

if [ -z "$1" ]; then
    echo "Error: Commit message is required."
    echo "Usage: $0 \"Your commit message\""
    exit 1
fi

COMMIT_MESSAGE=$1

echo "Adding all changes..."
git add -A

echo "Committing with message: '$COMMIT_MESSAGE'..."
git commit -m "$COMMIT_MESSAGE"

echo "Pushing to current branch..."
git push origin HEAD

echo "Done! Changes have been synced."
