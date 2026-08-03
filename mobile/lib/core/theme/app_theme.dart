import 'package:flutter/material.dart';

import 'tokens.dart';

/// ThemeData is built FROM the tokens — never the other way round.
ThemeData buildAppTheme() {
  final t = ArborTokens.light();
  final scheme = ColorScheme.fromSeed(
    seedColor: t.primary,
    surface: t.surface,
    onSurface: t.onSurface,
    error: t.error,
  );

  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    scaffoldBackgroundColor: t.surface,
    extensions: <ThemeExtension<dynamic>>[t],
    // Bundled, never fetched at runtime; never falls back to the system font.
    fontFamily: 'Manrope',
    textTheme: const TextTheme(
      displayLarge: TextStyle(fontFamily: 'PlusJakartaSans'),
      displayMedium: TextStyle(fontFamily: 'PlusJakartaSans'),
      displaySmall: TextStyle(fontFamily: 'PlusJakartaSans'),
      headlineLarge: TextStyle(fontFamily: 'PlusJakartaSans'),
      headlineMedium: TextStyle(fontFamily: 'PlusJakartaSans'),
      headlineSmall: TextStyle(fontFamily: 'PlusJakartaSans'),
      titleLarge: TextStyle(fontFamily: 'PlusJakartaSans'),
    ),
    // The no-line rule: boundaries come from background shifts, not borders.
    dividerTheme: const DividerThemeData(thickness: 0, space: 0),
    cardTheme: CardThemeData(
      elevation: 0,
      color: t.surfaceContainerLow,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(t.radiusNode),
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(t.radiusPill),
        ),
        padding: EdgeInsets.symmetric(
          horizontal: t.spaceLg,
          vertical: t.spaceMd,
        ),
      ),
    ),
  );
}
