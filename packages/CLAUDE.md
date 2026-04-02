# FamilyRoots Packages

## Overview
This directory contains shared Dart packages used by both the `mobile` and `web` apps. The key principle is: **shared logic lives here, platform-specific UI lives in the respective app directories.**

## Packages

### `family_roots_core`
Pure Dart package (no Flutter dependency). Contains:

- **`entities/`** — Domain models (`MemberModel`, `FamilyEvent`, `Relationship`) with `fromJson`/`toJson` methods for easy API integration.
- **`repositories/`** — Abstract repository interfaces (`MemberRepository`, `EventRepository`) that define the data contract.
- **`mocks/`** — Mock implementations (`MockMemberRepository`, `MockEventRepository`) with realistic Vietnamese family data. Used during UI development before the backend API is ready.

### Adding New Packages
When adding a new shared package:
1. Create it under `packages/` with `dart create -t package`.
2. Add the repository interface in `lib/repositories/`.
3. Add the mock implementation in `lib/mocks/`.
4. Export everything from the barrel file `lib/<package_name>.dart`.
5. Add `path` dependency in the consuming app's `pubspec.yaml`.

### Switching from Mock to Real API
To switch from mock data to a real backend:
1. Create `ApiMemberRepository` (or similar) that implements the same interface.
2. In the dependency injection setup, swap `MockMemberRepository` → `ApiMemberRepository`.
3. No UI code changes required — the repository interface is the contract.
