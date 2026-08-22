import 'package:flutter/material.dart';

/// Arbor Heritage design tokens. Violating a mandate should take effort, so
/// every colour, radius, spacing and elevation lives here and nowhere else.
@immutable
class ArborTokens extends ThemeExtension<ArborTokens> {
  const ArborTokens({
    required this.surface,
    required this.surfaceContainerLow,
    required this.onSurface,
    required this.primary,
    required this.onPrimary,
    required this.error,
    required this.outlineVariant,
    required this.radiusPill,
    required this.radiusNode,
    required this.spaceXs,
    required this.spaceSm,
    required this.spaceMd,
    required this.spaceLg,
    required this.ambientBlur,
    required this.ambientOpacity,
    required this.glassOpacity,
    required this.glassBlur,
  });

  /// Primary text is `on_surface` #1d1b16 — never #000000.
  ///
  /// `primary`, `onPrimary` and `surface` are ADR-041's values, taken exactly.
  /// See `docs/decisions/041-primary-green-heritage-family-single-background.md`
  /// decision 1 for the leaf green and decision 3 for the one warm ground.
  ///
  /// `surfaceContainerLow` and `error` are spec § 2.1's values, taken exactly,
  /// by seed S-044. `error` is the spec's `danger` under Flutter's name for the
  /// role; only the spelling is this repository's, the value is the spec's.
  /// It is the same hex as web's `destructive`. `mobile/CLAUDE.md` records why
  /// that makes the `heritage` rule stricter rather than looser.
  factory ArborTokens.light() => const ArborTokens(
    surface: Color(0xFFFBF8F1),
    surfaceContainerLow: Color(0xFFF4EFE4),
    onSurface: Color(0xFF1D1B16),
    primary: Color(0xFF3E5C38),
    onPrimary: Color(0xFFFFFFFF),
    error: Color(0xFFA32218),
    // Off-spec, found 2026-08-22: § 2.1 names `outline-variant` #B3A98F.
    // Nothing in `lib/` reads this token, so no screen shows the difference,
    // and moving it was outside S-044's stated end state. Left as found and
    // reported rather than changed unpinned.
    outlineVariant: Color(0xFFCFC7B4),
    // 9999px for primary buttons, 2rem (32px) for nodes. Never sm or none.
    radiusPill: 9999,
    radiusNode: 32,
    spaceXs: 4,
    spaceSm: 8,
    spaceMd: 16,
    spaceLg: 24,
    // Ambient depth, not rigid drop shadows.
    ambientBlur: 32,
    ambientOpacity: 0.06,
    // Glass: surface at 80% opacity with 20px backdrop blur.
    glassOpacity: 0.8,
    glassBlur: 20,
  );

  final Color surface;
  final Color surfaceContainerLow;
  final Color onSurface;
  final Color primary;
  final Color onPrimary;
  final Color error;
  final Color outlineVariant;
  final double radiusPill;
  final double radiusNode;
  final double spaceXs;
  final double spaceSm;
  final double spaceMd;
  final double spaceLg;
  final double ambientBlur;
  final double ambientOpacity;
  final double glassOpacity;
  final double glassBlur;

  @override
  ArborTokens copyWith({Color? surface, Color? onSurface, Color? primary}) =>
      ArborTokens(
        surface: surface ?? this.surface,
        surfaceContainerLow: surfaceContainerLow,
        onSurface: onSurface ?? this.onSurface,
        primary: primary ?? this.primary,
        onPrimary: onPrimary,
        error: error,
        outlineVariant: outlineVariant,
        radiusPill: radiusPill,
        radiusNode: radiusNode,
        spaceXs: spaceXs,
        spaceSm: spaceSm,
        spaceMd: spaceMd,
        spaceLg: spaceLg,
        ambientBlur: ambientBlur,
        ambientOpacity: ambientOpacity,
        glassOpacity: glassOpacity,
        glassBlur: glassBlur,
      );

  @override
  ArborTokens lerp(ThemeExtension<ArborTokens>? other, double t) {
    if (other is! ArborTokens) return this;
    return ArborTokens(
      surface: Color.lerp(surface, other.surface, t)!,
      surfaceContainerLow: Color.lerp(
        surfaceContainerLow,
        other.surfaceContainerLow,
        t,
      )!,
      onSurface: Color.lerp(onSurface, other.onSurface, t)!,
      primary: Color.lerp(primary, other.primary, t)!,
      onPrimary: Color.lerp(onPrimary, other.onPrimary, t)!,
      error: Color.lerp(error, other.error, t)!,
      outlineVariant: Color.lerp(outlineVariant, other.outlineVariant, t)!,
      radiusPill: radiusPill,
      radiusNode: radiusNode,
      spaceXs: spaceXs,
      spaceSm: spaceSm,
      spaceMd: spaceMd,
      spaceLg: spaceLg,
      ambientBlur: ambientBlur,
      ambientOpacity: ambientOpacity,
      glassOpacity: glassOpacity,
      glassBlur: glassBlur,
    );
  }
}

extension ArborContext on BuildContext {
  ArborTokens get tokens => Theme.of(this).extension<ArborTokens>()!;
}
