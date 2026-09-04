import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
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

  test('the card ground and the danger red are spec 2.1 values', () {
    final t = ArborTokens.light();
    // `surface-container-low`. Replaces #F5F1E6, which was sourced by no spec
    // section and no ADR, only by the M0 plan that wrote it.
    expect(t.surfaceContainerLow, const Color(0xFFF4EFE4));
    // The spec calls this role `danger`; Flutter calls it `error`. The value is
    // the spec's and it is web's `destructive` exactly. Replaces #8C1D18, a
    // Material default that no document in this repository sourced.
    expect(t.error, const Color(0xFFA32218));
  });

  test('the outline-variant role is spec 2.1 value', () {
    final t = ArborTokens.light();
    // Replaces #CFC7B4, sourced only by the M0 plan that wrote it. No widget in
    // `lib/` reads this token, but `ColorScheme.outlineVariant` is real and the
    // next test pins that the app paints this value there rather than a tone
    // `fromSeed` derived. The no-line rule keeps the 15%-opacity condition on
    // the widget that draws a line, not on the value itself.
    expect(t.outlineVariant, const Color(0xFFB3A98F));
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
    // Both were unpinned before the surfaceContainerLow fix. `error` was already overridden and
    // survived; `surfaceContainerLow` was not, and `fromSeed` derived #F2F5EB
    // from the leaf-green seed while the token said #F5F1E6.
    expect(scheme.error, t.error);
    expect(scheme.surfaceContainerLow, t.surfaceContainerLow);
    // the outlineVariant fix: the same trap a third time. Unpinned, `fromSeed` derived #C2C8BC
    // from the leaf-green seed while the token said #CFC7B4. Six Material
    // `…DefaultsM3` classes read this field, so an unsourced value here is a
    // colour the app would paint the day a `Divider` or a `Chip` lands.
    expect(scheme.outlineVariant, t.outlineVariant);
  });

  test('the card ground is the token, and it steps off the page', () {
    final t = ArborTokens.light();
    expect(buildAppTheme().cardTheme.color, t.surfaceContainerLow);
    // The no-line rule: a card is separated by a background step, not a
    // border, so the two must not be the same colour.
    expect(t.surfaceContainerLow, isNot(t.surface));
    // Ambient depth, not a rigid drop shadow. Moved here from the divider test
    // by the divider fix, which is now about pixels and only about dividers.
    expect(buildAppTheme().cardTheme.elevation, 0);
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

  testWidgets('the no-line rule: a real Divider paints no pixel', (
    tester,
  ) async {
    // the divider fix replaced `expect(theme.dividerTheme.thickness, 0)` with this.
    // Thickness zero is not absence: Flutter draws a thickness-0 divider as a
    // hairline of exactly one device pixel (`material/divider.dart:86-87`),
    // and before this test the app painted one. Measured 2026-08-22 over the
    // page ground `#FBF8F1` at device pixel ratio 3.0, two raster rows came
    // back `#D7D1C0` and `#D7D0C0`. A test that pins the field cannot see
    // that, so this one rasterises the widget and reads the pixels instead.
    final t = ArborTokens.light();

    // Two grounds. `surface` is what the app actually paints on, and it is
    // where a faint hairline hides best; the dark one leaves a blend nowhere
    // to hide. On it the same line measured `#61645F` against `#102030`.
    for (final ground in <Color>[t.surface, const Color(0xFF102030)]) {
      for (final axis in Axis.values) {
        final key = GlobalKey();
        const before = SizedBox.square(dimension: 4);
        const after = SizedBox.square(dimension: 5);
        await tester.pumpWidget(
          MaterialApp(
            theme: buildAppTheme(),
            home: Center(
              child: RepaintBoundary(
                key: key,
                // Nothing else paints inside the boundary, so every pixel that
                // is not the ground came from the divider.
                child: ColoredBox(
                  color: ground,
                  child: SizedBox(
                    width: 9,
                    height: 9,
                    child: axis == Axis.horizontal
                        ? const Column(
                            children: <Widget>[before, Divider(), after],
                          )
                        : const Row(
                            children: <Widget>[
                              before,
                              VerticalDivider(),
                              after,
                            ],
                          ),
                  ),
                ),
              ),
            ),
          ),
        );
        await tester.pumpAndSettle();

        // A divider that draws nothing must also take no room, so an
        // accidental one is inert in layout too.
        expect(
          tester.getSize(
            find.byType(axis == Axis.horizontal ? Divider : VerticalDivider),
          ),
          axis == Axis.horizontal ? const Size(9, 0) : const Size(0, 9),
          reason: 'the divider should occupy no space on the $axis axis',
        );

        // A hairline is defined in device pixels, so rasterise at this host's
        // device pixel ratio rather than at 1.0.
        final boundary =
            key.currentContext!.findRenderObject()! as RenderRepaintBoundary;
        final ui.Image image = boundary.toImageSync(
          pixelRatio: tester.view.devicePixelRatio,
        );
        final data = await tester.runAsync(
          () => image.toByteData(format: ui.ImageByteFormat.rawRgba),
        );
        image.dispose();

        final bytes = data!.buffer.asUint8List();
        final painted = <String>{};
        for (var i = 0; i < bytes.length; i += 4) {
          // rawRgba is R,G,B,A; rebuild it as 0xAARRGGBB to compare.
          final argb =
              (bytes[i + 3] << 24) |
              (bytes[i] << 16) |
              (bytes[i + 1] << 8) |
              bytes[i + 2];
          painted.add(
            '#${argb.toRadixString(16).toUpperCase().padLeft(8, '0')}',
          );
        }

        final expected =
            '#${ground.toARGB32().toRadixString(16).toUpperCase().padLeft(8, '0')}';
        expect(
          painted,
          <String>{expected},
          reason:
              'A $axis divider painted a pixel over $expected. The no-line '
              'rule forbids the line, and `thickness: 0` does not suppress '
              'it — only `DividerThemeData.color` does.',
        );
      }
    }
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
