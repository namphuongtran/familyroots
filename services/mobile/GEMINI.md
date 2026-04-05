# mobile

## Responsibility
Provides the native app experience (Android, iOS, Tablet) for end-users (especially younger generations checking notifications and elders viewing trees). Fully automated deployment to app stores via CI.

## Stack
Flutter (Dart), BLoC (State Management), Dio/Retrofit (Networking), GetIt (DI), Hive (Local Storage)

## Domain Model
Maps backend contracts to Dart models.

## API Surface
Consumes the `backend` REST API.

## Event Contracts
Consumes FCM Push Notifications for death anniversaries and reminders.

## Data Ownership
Owns local device cache (Hive) and secure token storage.

## Key Commands
- run: `make mobile-run`
- test: `make mobile-test`
- analyze: `make mobile-analyze`

## Error Handling Pattern
Dio interceptors map API errors into BLoC states (e.g., `ErrorState` with user-friendly localized messages).

## Don't Do
- Do not place business logic in UI widgets; use BLoC.
- Do not violate Arbor Heritage design system mandates.