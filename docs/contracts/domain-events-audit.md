# Contract: domain-events-audit

## Type
Internal Domain Event Stream

## Owner
backend

## Consumers
- backend audit log handler
- notification and downstream handlers (where wired)

## Schema
Current transport:
- in-process event dispatch inside backend Unit of Work commit path

Current event families include:
- person created/updated/deleted style events
- marriage and parent-child lifecycle events
- document lifecycle events
- event lifecycle events
- branch lifecycle events

Audit payload shape (conceptual):
- event type
- aggregate id
- actor metadata
- timestamp
- event-specific payload

## Versioning & Compatibility Rules
- Additive event fields are preferred.
- Renaming/removing event fields requires compatibility shim in handlers.
- Moving to external broker must preserve semantic event names or include translation layer.

## Notes
This contract is currently process-local and not durable across crashes. Evaluate broker-backed durability for critical workflows. <!-- TODO: verify this -->
