import 'package:flutter/material.dart';

import 'tokens.dart';

/// ThemeData is built FROM the tokens — never the other way round.
ThemeData buildAppTheme() {
  final t = ArborTokens.light();
  // `fromSeed` re-derives the seed into a Material tonal palette, so it does
  // NOT return the seed. Measured 2026-08-22 with the bronze seed #7A5C2E, it
  // produced `scheme.primary` #7E570F — a colour in no token file. Every value
  // the tokens own is therefore passed explicitly and overrides the derivation;
  // the seed only fills the tones no token names. Spec §2.8 requires this:
  // "ColorScheme is populated from the same values so Material widgets inherit
  // correctly."
  //
  // `surfaceContainerLow` joined the list in S-044 for the same reason, and it
  // was the one token the S-037 fix missed. Measured 2026-08-22 before the fix:
  // `scheme.surfaceContainerLow` was #F2F5EB, a green-tinted tone derived from
  // the leaf-green seed, while the token said #F5F1E6. `cardTheme` below reads
  // the token directly, so no shipped screen showed it, but every Material
  // widget that defaults to `colorScheme.surfaceContainerLow` (Drawer, and the
  // M3 menu and sheet surfaces) would have painted the derived tone.
  //
  // `outlineVariant` joined in S-048, and it is the same trap a third time.
  // Measured 2026-08-22 before that fix: `scheme.outlineVariant` was #C2C8BC,
  // another leaf-green tone, while the token said #CFC7B4. Six Flutter 3.44.8
  // `…DefaultsM3` classes read `colorScheme.outlineVariant` — `_DividerDefaults`
  // (`Divider`, `VerticalDivider`), `_OutlinedCardDefaults`, both `_TabsDefaults`,
  // `_ChipDefaults` and `_BannerDefaults`. No screen in `lib/` uses one today,
  // so nothing paints it today; that is a fact about the screens shipped, not
  // about the role being dead.
  final scheme = ColorScheme.fromSeed(
    seedColor: t.primary,
    primary: t.primary,
    onPrimary: t.onPrimary,
    surface: t.surface,
    onSurface: t.onSurface,
    surfaceContainerLow: t.surfaceContainerLow,
    error: t.error,
    outlineVariant: t.outlineVariant,
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
