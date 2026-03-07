# Web — FamilyRoots

Flutter Web app for browser access and admin panel.

## Architecture

Same Clean Architecture + BLoC pattern as mobile, with web-specific additions:

```
lib/
├── main.dart              # Entry point (web-specific)
├── app/                   # App config (web router, wider theme)
├── core/                  # DI, networking, error handling, constants
├── features/              # Feature-first modules
│   ├── auth/              # Authentication
│   ├── family_tree/       # Tree viewer (wider canvas for desktop)
│   ├── members/           # Member profiles
│   ├── documents/         # Photo/document management
│   ├── events/            # Anniversaries and events
│   └── admin/             # Admin panel (role-gated)
│       └── presentation/
│           └── pages/
│               ├── dashboard_page.dart
│               ├── user_approval_page.dart
│               ├── clan_settings_page.dart
│               └── audit_log_page.dart
└── shared/                # Web-specific widgets (sidebars, data tables)
```

## Key Differences from Mobile

| Concern          | Mobile                     | Web                              |
|-----------------|---------------------------|----------------------------------|
| Entry point     | `mobile/lib/main.dart`    | `web/lib/main.dart`             |
| Router          | Mobile-optimized routes   | Web routes + `/admin/*`          |
| Layouts         | Compact, touch-first      | Wide, mouse-first, sidebar nav   |
| Admin panel     | Not included              | Included (role-gated)            |
| Build target    | `flutter build apk/ipa`   | `flutter build web`             |
| Deploy          | Google Play / App Store   | Vercel                          |

## Setup

```bash
# Get dependencies
flutter pub get

# Run code generation
dart run build_runner build --delete-conflicting-outputs

# Copy environment file
cp .env.example .env

# Run in browser
flutter run -d chrome
```

## Commands

```bash
flutter pub get          # Get dependencies
flutter analyze          # Lint
flutter test             # Run tests
flutter run -d chrome    # Run in browser
flutter build web        # Build for production
```
