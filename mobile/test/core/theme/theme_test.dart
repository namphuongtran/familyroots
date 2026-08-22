import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as p;

import 'package:family_roots_mobile/core/theme/app_theme.dart';
import 'package:family_roots_mobile/core/theme/tokens.dart';

import '../../support/load_app_fonts.dart';

/// Any `Color(0x...)` literal, however it is spelled.
final _colorLiteral = RegExp(r'Color\(\s*0x[0-9a-fA-F]{6,8}');

void main() {
  setUpAll(loadAppFonts);

  test('ADR-041: the tokens carry the leaf green on the one warm ground', () {
    final t = ArborTokens.light();
    // Decision 1. The bronze #7A5C2E it replaced collided with `secondary`.
    expect(t.primary, const Color(0xFF3E5C38));
    expect(t.onPrimary, const Color(0xFFFFFFFF));
    // Decision 3. One value under one name, shared with web.
    expect(t.surface, const Color(0xFFFBF8F1));
  });

  test('S-044: the card ground and the danger red are spec 2.1 values', () {
    final t = ArborTokens.light();
    // `surface-container-low`. Replaces #F5F1E6, which was sourced by no spec
    // section and no ADR, only by the M0 plan that wrote it.
    expect(t.surfaceContainerLow, const Color(0xFFF4EFE4));
    // The spec calls this role `danger`; Flutter calls it `error`. The value is
    // the spec's and it is web's `destructive` exactly. Replaces #8C1D18, a
    // Material default that no document in this repository sourced.
    expect(t.error, const Color(0xFFA32218));
  });

  test('the painted primary is the token, not a re-derived tone', () {
    // `ColorScheme.fromSeed` returns a tonal palette, not the seed. Without an
    // explicit override the app paints a green that is in no token file.
    final t = ArborTokens.light();
    final scheme = buildAppTheme().colorScheme;
    expect(scheme.primary, t.primary);
    expect(scheme.onPrimary, t.onPrimary);
    expect(scheme.surface, t.surface);
    expect(scheme.onSurface, t.onSurface);
    // Both were unpinned before S-044. `error` was already overridden and
    // survived; `surfaceContainerLow` was not, and `fromSeed` derived #F2F5EB
    // from the leaf-green seed while the token said #F5F1E6.
    expect(scheme.error, t.error);
    expect(scheme.surfaceContainerLow, t.surfaceContainerLow);
  });

  test('the card ground is the token, and it steps off the page', () {
    final t = ArborTokens.light();
    expect(buildAppTheme().cardTheme.color, t.surfaceContainerLow);
    // The no-line rule: a card is separated by a background step, not a
    // border, so the two must not be the same colour.
    expect(t.surfaceContainerLow, isNot(t.surface));
  });

  test('no colour literal lives outside tokens.dart', () {
    final libDir = Directory('lib');
    expect(libDir.existsSync(), isTrue, reason: 'run from the package root');

    final offenders = <String>[];
    for (final entity in libDir.listSync(recursive: true)) {
      if (entity is! File || !entity.path.endsWith('.dart')) continue;
      final rel = p.relative(entity.path, from: 'lib');
      if (rel == p.join('core', 'theme', 'tokens.dart')) continue;
      if (_colorLiteral.hasMatch(entity.readAsStringSync())) {
        offenders.add(rel);
      }
    }

    expect(
      offenders,
      isEmpty,
      reason:
          'A colour may only be declared in core/theme/tokens.dart. '
          'Reach it with `context.tokens`.',
    );
  });

  testWidgets('tokens honour the Arbor Heritage mandates', (tester) async {
    late ArborTokens t;
    await tester.pumpWidget(
      MaterialApp(
        theme: buildAppTheme(),
        home: Builder(
          builder: (context) {
            t = context.tokens;
            return const SizedBox();
          },
        ),
      ),
    );
    await tester.pumpAndSettle();

    // Never #000000.
    expect(t.onSurface, isNot(const Color(0xFF000000)));
    expect(t.onSurface, const Color(0xFF1D1B16));
    // 9999px for primary buttons, 2rem for nodes. Never sm or none.
    expect(t.radiusPill, 9999);
    expect(t.radiusNode, 32);
    // Glass: surface at 80% opacity with 20px backdrop blur.
    expect(t.glassOpacity, 0.8);
    expect(t.glassBlur, 20);
    // Ambient depth, not rigid drop shadows.
    expect(t.ambientBlur, 32);
    expect(t.ambientOpacity, 0.06);
  });

  testWidgets('the no-line rule: dividers have no thickness', (tester) async {
    final theme = buildAppTheme();
    expect(theme.dividerTheme.thickness, 0);
    expect(theme.cardTheme.elevation, 0);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('body text is Manrope, headings Plus Jakarta Sans', (
    tester,
  ) async {
    final theme = buildAppTheme();
    expect(theme.textTheme.headlineLarge?.fontFamily, 'PlusJakartaSans');
    expect(theme.textTheme.titleLarge?.fontFamily, 'PlusJakartaSans');
    // The family default covers body/labels.
    expect(theme.textTheme.bodyMedium?.fontFamily ?? 'Manrope', 'Manrope');
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('the bundled variable font applies its weight axis', (
    tester,
  ) async {
    Future<Size> measure(FontWeight w) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Center(
            child: Text(
              'Gia phả dòng họ',
              style: TextStyle(
                fontFamily: 'PlusJakartaSans',
                fontSize: 32,
                fontWeight: w,
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      return tester.getSize(find.byType(Text));
    }

    final regular = await measure(FontWeight.w400);
    final bold = await measure(FontWeight.w700);
    // The placeholder test font is weight-insensitive; the real one is not.
    expect(bold.width, isNot(regular.width));
  });
}
