// The resend button on /verify-email. Reads the screen: the backend's message
// on success, ErrorView's text on failure, and the requests the transport saw.
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:family_roots_mobile/core/l10n/generated/app_localizations.dart';
import 'package:family_roots_mobile/core/theme/app_theme.dart';
import 'package:family_roots_mobile/features/auth/auth.dart';

import '../../support/load_app_fonts.dart';
import '../../support/main_container.dart';
import '../../support/sequence_adapter.dart';

const _label = 'Gửi lại email xác thực';

Future<SequenceAdapter> _pump(WidgetTester tester, Canned canned) async {
  final adapter = SequenceAdapter(<Canned>[canned]);
  late ProviderContainer c;
  await tester.runAsync(() async => c = await mainContainer(adapter: adapter));
  addTearDown(c.dispose);
  await tester.pumpWidget(
    UncontrolledProviderScope(
      container: c,
      child: MaterialApp(
        theme: buildAppTheme(),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        locale: const Locale('vi'),
        home: const VerifyEmailPage(email: 'a@b.c'),
      ),
    ),
  );
  return adapter;
}

/// The press and the request both run in the real zone: a dio request begun
/// inside a widget test's fake-async zone never reaches the adapter.
Future<void> _press(WidgetTester tester, {int times = 1}) => tester
    .runAsync(() async {
      for (var i = 0; i < times; i++) {
        await tester.tap(find.text(_label), warnIfMissed: false);
      }
      await Future<void>.delayed(const Duration(milliseconds: 50));
    })
    .then((_) {});

void main() {
  setUpAll(loadAppFonts);

  testWidgets('shows the backend message after a resend', (tester) async {
    final a = await _pump(
      tester,
      const Canned(200, <String, Object?>{
        'data': <String, Object?>{'message': 'Đã gửi lại email'},
      }),
    );
    await _press(tester);
    await tester.pump();
    expect(find.text('Đã gửi lại email'), findsOneWidget);
    expect(a.callCount, 1);
  });

  testWidgets('shows ErrorView text on a 429 and nothing escapes', (
    tester,
  ) async {
    await _pump(
      tester,
      const Canned(429, <String, Object?>{
        'error': <String, Object?>{
          'code': 'rate_limited',
          'message': 'Quá nhiều yêu cầu',
          'detail': <String, Object?>{'retry_after': 42},
        },
      }),
    );
    await _press(tester);
    await tester.pump();
    expect(find.text('Quá nhiều yêu cầu'), findsOneWidget);
  });

  testWidgets('two presses before the response send one request', (
    tester,
  ) async {
    final a = await _pump(
      tester,
      const Canned(200, <String, Object?>{
        'data': <String, Object?>{'message': 'ok'},
      }),
    );
    await _press(tester, times: 2);
    await tester.pump();
    expect(a.callCount, 1);
  });
}
