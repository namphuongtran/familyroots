import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:family_roots_mobile/core/theme/app_theme.dart';
import 'package:family_roots_mobile/core/theme/tokens.dart';

import '../../support/load_app_fonts.dart';

void main() {
  setUpAll(loadAppFonts);

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
