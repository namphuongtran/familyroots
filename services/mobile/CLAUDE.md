# mobile

## Responsibility
Owns native mobile UX for onboarding, member browsing, family tree exploration, and notification interactions.
It does not own canonical business rules, backend data integrity, or infra provisioning.

## Stack
- Flutter + Dart 3
- flutter_bloc for state management
- dio + retrofit for HTTP
- supabase_flutter for auth
- firebase_messaging for push
- go_router for navigation
- get_it/injectable for dependency injection
- hive for local storage

## Domain Model
Feature modules align with backend contexts:
- auth, members, family_tree, events, documents, notifications
- shared package family_roots_core provides reusable entities and repositories

## API Surface
Consumes backend REST endpoints under /api/v1 with bearer auth.
Primary integrations:
- auth/session endpoints
- persons and relationship endpoints
- tree endpoints
- documents/events endpoints

## Event Contracts
Consumes:
- Push notifications via FCM payloads
- Backend REST contracts for reads/writes

Publishes:
- User-triggered mutations to backend via HTTP
- Device token registration updates

## Data Ownership
Owns mobile UI state, offline cache (where configured), and device-level preferences.
No canonical server data ownership.

## Key Commands
- Dev run: cd mobile && flutter run
- Test: cd mobile && flutter test
- Analyze: cd mobile && dart analyze .
- Codegen: cd mobile && flutter pub run build_runner build --delete-conflicting-outputs

## Error Handling Pattern
- Network and auth failures map into feature-level failure classes for BLoC states.
- UI-first workflow uses mock repositories first, then swaps DI bindings for real API implementations.

## Don't Do
- Do not bypass localization; no hardcoded user-facing strings.
- Do not break Arbor Heritage design system constraints (no-line rule, typography constraints).
- Do not couple widgets directly to concrete data sources.

## Known Issues / Landmines
- Multiple modules remain scaffolded with Prompt 2 TODO markers. <!-- TODO: verify this -->
- Base API URL and environment loading are partially hardcoded in current scaffolding. <!-- TODO: verify this -->
