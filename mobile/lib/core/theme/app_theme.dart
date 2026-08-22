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
    //
    // `thickness: 0` does not suppress the line, and this theme claimed that it
    // did from `0785036` (2026-08-03) until S-049. Flutter states the opposite at
    // `material/divider.dart:86-87`: "A divider with a [thickness] of 0.0 is
    // always drawn as a line with a height of exactly one device pixel."
    // Measured 2026-08-22 by S-049, rasterising a real `Divider` over the page
    // ground `#FBF8F1` at this host's device pixel ratio of 3.0: two raster
    // rows changed, to `#D7D1C0` and `#D7D0C0` — one device pixel of ink,
    // antialiased across the two rows the hairline straddles. That is 1.44:1
    // against the ground, faint but painted.
    //
    // `color` is what actually suppresses it. Without one, the line takes
    // `colorScheme.outlineVariant`, so the theme was choosing the colour of a
    // line it believed it had suppressed. `Colors.transparent` is not a colour
    // choice and so does not belong in `tokens.dart`: it is the absence of
    // paint, and a token for it would name a colour nothing renders.
    //
    // `thickness: 0` and `space: 0` stay so an accidental `Divider` is inert in
    // layout as well as in paint. Deleting this theme was the other branch and
    // it loses: `_DividerDefaultsM3` (`material/divider.dart:359-370`) would
    // then give thickness `1.0`, space `16`, and `outlineVariant` at full
    // opacity, so honesty would be bought by making the forbidden line larger.
    //
    // A high-contrast mode turns the line back on here, and only here: the rule
    // allows `outline_variant` at 15% opacity in that mode, which is this same
    // `DividerThemeData` with `color: t.outlineVariant.withValues(alpha: 0.15)`
    // and `thickness: 1`. Building that mode is out of S-049's scope.
    //
    // `test/core/theme/theme_test.dart` asserts the pixels, not this field.
    dividerTheme: const DividerThemeData(
      color: Colors.transparent,
      thickness: 0,
      space: 0,
    ),
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
