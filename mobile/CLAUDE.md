# FamilyRoots Mobile UI Development Guidelines

This document outlines the strict guidelines for developing user interfaces in the FamilyRoots Flutter mobile application. These rules were established after our initial prototyping phase to ensure that the mobile app matches the design vision.

## 1. UI-First Development Workflow

All new features and screens must follow this 4-step process:

1. **Design First:** All new features must be designed, reviewed, and approved via the Stitch design system (Project ID: `15513208985178358792`).
2. **Review Design Specs:** Before writing code, thoroughly review the layout, spacing tokens, typography, and color palette from the design. Pay special attention to the "Do's and Don'ts" of our specific design system.
3. **Mock Data Implementation:** Build the UI in Flutter using static mock data to achieve pixel-perfect fidelity with the design. Do not connect to the backend API during this phase to avoid being blocked by backend state constraints and to quickly iterate on the visual layout.
4. **Backend Integration:** Replace the mock data with real API calls *only after* the UI is perfectly aligned with the design and approved.

## 2. Shared Packages Architecture

Our application follows a modular approach. Core styles, assets, and base models live inside the local `packages/` directory instead of `mobile/lib/`.
- **Why?** This enforces strict boundary isolation and lets us independently test business logic and component catalogs.
- **Reference**: Please review exactly how to develop and extract code to packages via [Packages Guidelines](../packages/CLAUDE.md).

## 3. The "Arbor Heritage" Design System Mandates

Our active design system requires a specific organic, premium editorial feel. Adhere strictly to the following rules:

### A. The "No-Line" Rule
- **Mandate:** Do not use 1px solid borders to define sections or separation (unless absolutely necessary for accessibility like high-contrast mode, where you use `outline_variant` at 15% opacity).
- **Alternative:** Layout boundaries must be achieved through subtle background color shifts (e.g., placing `surface-container-low` on top of `surface`).

### B. Typography
- **Headings & Display:** Use **Plus Jakarta Sans** for storytelling, major milestones, person names, and branch titles.
- **Body & Labels:** Use **Manrope** for legible data display and general text.
- Never use the default device system font unless specified. Currently powered by `google_fonts`.

### C. Organic Asymmetry & Elevation
- **Roundedness:** Nodes, buttons, and family tree canvas items must use soft, highly rounded corners (e.g., `9999px` for primary buttons, `2rem` for nodes). Avoid sharp corners (no `sm` or `none` radiuses).
- **Shadows:** Standard rigid drop shadows are forbidden. Instead, use ambient depth (e.g., 32px blur at 6% opacity) if elevation is needed.
- **The Glass Rule:** Floating cards or nav bars should use the `surface` color at 80% opacity with a `20px` backdrop-blur to let content peek through.

### D. General Restrictions
- **No Pure Black:** Never use `#000000`. Use the `on_surface` token (`#1d1b16`) for primary text.
- **No Rigid Grids:** Do not force components into a strict standard grid unless required by table data. Allow elements to 'breathe' in organic asymmetrical alignments.

## 4. Developer & Testing Guidelines

Before submitting PRs or finalizing features, you **must run tests** to ensure no regressions were introduced.

### Running Unit & Widget Tests
You can run tests from the `/mobile` directory:
```bash
flutter test
```

### Static Analysis
Ensure code fits Dart formatting rules and doesn't introduce lints:
```bash
dart analyze .
```

### Build Constraints
Always run code generation if you change BLoC States, Freezed models, or Localizations:
```bash
flutter pub run build_runner build --delete-conflicting-outputs
```

### Platform-Specific Testing
**iOS (Simulator):**
```bash
# List available simulators
xcrun simctl list devices available
# Boot a simulator (e.g. iPhone 16)
xcrun simctl boot "iPhone 16"
# Run on iOS
flutter run -d "iPhone 16"
# Run tests on iOS simulator
flutter test --device-id=<simulator_id>
```

**Android (Emulator):**
```bash
# List available AVDs
flutter emulators
# Launch an emulator
flutter emulators --launch <emulator_id>
# Run on Android
flutter run -d <device_id>
```

## 5. Localization (l10n) Rules

All user-facing text **MUST** use `AppLocalizations`, never hardcoded strings.

### Adding New Strings
1. Add the key + English text to `lib/shared/l10n/app_en.arb`.
2. Add the key + Vietnamese text to `lib/shared/l10n/app_vi.arb`.
3. Add the abstract getter/method to `app_localizations.dart`.
4. Implement the getter/method in both `app_localizations_en.dart` and `app_localizations_vi.dart`.
5. Use in widget: `final l10n = AppLocalizations.of(context); Text(l10n.myKey)`

### Parameterized Strings
Use method parameters for dynamic text:
```dart
// In ARB: "greeting": "Hello, {name}"
// In localizations: String greeting(String name);
// Usage: l10n.greeting('Minh')
```

### Plurals
Use `intl.Intl.pluralLogic` for count-based strings.

## 6. Architecture & Data Layer

### Repository Pattern
- **Interface** lives in `packages/family_roots_core/lib/repositories/`.
- **Mock implementation** lives in `packages/family_roots_core/lib/mocks/`.
- **Real API implementation** will live in `mobile/lib/features/<feature>/data/`.

### Switching Mock → Real API
```dart
// In DI setup (get_it/injectable), change:
// getIt.registerLazySingleton<MemberRepository>(() => MockMemberRepository());
// to:
// getIt.registerLazySingleton<MemberRepository>(() => ApiMemberRepository(dio));
```
No widget code changes required — the UI depends on the abstract interface only.
