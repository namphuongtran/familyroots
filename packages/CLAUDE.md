# Packages Architecture Guidelines

This directory contains standalone Dart/Flutter packages that are decoupled from the main app. 

## Rationale
Extracting features into `packages/` enforces a strict separation of concerns (SoC). Code here cannot depend on the main app (`mobile/`). This forces developers to write clean, reusable interfaces and allows us to test packages completely in isolation.

## Guidelines
1. **No App-level Dependencies**: A package here (like `family_roots_core`) should only depend on basic Flutter/Dart SDKs or explicitly declared third-party libraries. It must never import from `family_roots_mobile`.
2. **Clear Public API**: Use the `lib/package_name.dart` file (e.g., `lib/family_roots_core.dart`) as a barrel file to export the public API of the package. Hide internal implementation details.
3. **Theming & Core Data**: Shared UI tokens (`AppColors`, `AppTypography`) and base entity models should live here so they can be reused if we build a companion app or a web version.

## Creation
To create a new package:
```bash
cd packages
flutter create --template=package new_package_name
```
