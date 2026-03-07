# Packages — Shared Dart Code

This directory contains shared Dart packages used by both `mobile/` and `web/` Flutter apps.

## family_roots_core

Pure Dart package (no Flutter dependency) containing:

- **entities/** — Shared domain entities (Member, Clan, Event, etc.)
- **api/** — Shared API response/request models
- **utils/** — Shared utility functions (date formatting, validators)

### Why a separate package?

Any entity or utility that is identical in mobile and web apps lives here instead of being
duplicated. Both apps reference it via path dependency in their `pubspec.yaml`:

```yaml
dependencies:
  family_roots_core:
    path: ../packages/family_roots_core
```
