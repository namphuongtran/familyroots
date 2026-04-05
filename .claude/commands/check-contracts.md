I am about to change a cross-service API or event.

Changed contract: {name}
Type: {Kafka event / REST API / gRPC}
Change: {what is changing}

Check:
1. docs/contracts/{name}.md for current schema and consumers
2. All CLAUDE.md files of consuming services
3. Is this change backward compatible?
   - If YES: proceed, note the change for update-knowledge
   - If NO: flag breaking change and propose versioning strategy

Output:
- Impact analysis: which services break and how
- Migration plan: how to roll this out safely
- Contract doc update: exact diff to docs/contracts/{name}.md
