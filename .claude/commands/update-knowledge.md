We just finished a work session. Before closing:

1. Ask me: "What did we build, change, or decide this session?"
2. Based on my answer, identify which knowledge files need updating:
   - New commands or scripts -> root CLAUDE.md
   - Domain model changes -> services/{name}/CLAUDE.md
   - New event or API -> docs/contracts/
   - New architectural decision -> docs/decisions/
   - Cross-service changes -> check docs/contracts/ for consistency
3. Show me exact diffs of every proposed change
4. Ask: "Approve, modify, or skip each change?"
5. Write only what I approve

End with: "Second brain updated. Next session will have full context."
