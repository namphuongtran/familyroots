# ADR-003: REST-First Cross-Client Contract Strategy

## Status
Accepted

## Context
Both web and mobile clients need stable and evolvable contracts.
The backend currently exposes rich REST endpoints with include/profile/fields query semantics.

## Decision
Standardize on REST-first contracts for current phase:
- backend FastAPI routes are canonical contract surface
- web/mobile clients consume versioned REST patterns
- contract docs are maintained in docs/contracts
- evaluate GraphQL only as additive surface, not replacement

## Consequences
Easier:
- one clear source of truth for current clients
- simpler debugging and CI verification
- less parallel complexity during active product iteration

Harder:
- over-fetch/under-fetch tradeoffs for some views
- future GraphQL adoption requires careful compatibility planning
