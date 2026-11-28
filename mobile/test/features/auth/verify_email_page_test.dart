// The resend button on /verify-email: what the person sees after a press.
// Readings are the screen's text and the requests the adapter recorded.
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:family_roots_mobile/core/l10n/generated/app_localizations.dart';
import 'package:family_roots_mobile/core/theme/app_theme.dart';
import 'package:family_roots_mobile/features/auth/auth.dart';

import '../../support/load_app_fonts.dart';
import '../../support/main_container.dart';
import '../../support/sequence_adapter.dart';

/// Copied from `lib/core/l10n/app_vi.arb`: the button's label in `vi`.
const _resendLabel = 'Gửi lại email xác thực';

Future<void> _pump(WidgetTester tester, SequenceAdapter adapter) async {
  final container = await mainContainer(adapter: adapter);
  addTearDown(container.dispose);
  await tester.pumpWidget(
    UncontrolledProviderScope(
      container: container,
      child: MaterialApp(
        theme: buildAppTheme(),
        locale: const Locale('vi'),
        localizationsDelegates: const <LocalizationsDelegate<Object?>>[
          AppLocalizations.delegate,
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        supportedLocales: AppLocalizations.supportedLocales,
        home: const VerifyEmailPage(email: 'minh@example.com'),
      ),
    ),
  );
}

void main() {
  setUpAll(loadAppFonts);

  testWidgets('a 200 shows the backend message', (tester) async {
    final adapter = SequenceAdapter(<Canned>[
      const Canned(200, <String, Object?>{
        'data': <String, Object?>{'message': 'Đã gửi email xác minh.'},
      }),
    ]);
    await _pump(tester, adapter);

    await tester.tap(find.text(_resendLabel));
    await tester.runAsync(() => Future<void>.delayed(Duration.zero));
    await tester.pumpAndSettle();

    expect(find.text('Đã gửi email xác minh.'), findsOneWidget);
    expect(adapter.callCount, 1);
  });

  testWidgets('a 429 shows the error text and escapes nothing', (tester) async {
    final adapter = SequenceAdapter(<Canned>[
      const Canned(429, <String, Object?>{
        'error': <String, Object?>{
          'code': 'rate_limited',
          'message': 'Quá nhiều yêu cầu, thử lại sau.',
        },
      }),
    ]);
    await _pump(tester, adapter);

    await tester.tap(find.text(_resendLabel));
    await tester.runAsync(() => Future<void>.delayed(Duration.zero));
    await tester.pumpAndSettle();

    expect(find.text('Quá nhiều yêu cầu, thử lại sau.'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('two presses before the response send one request', (
    tester,
  ) async {
    final adapter = SequenceAdapter(<Canned>[
      const Canned(200, <String, Object?>{
        'data': <String, Object?>{'message': 'Đã gửi.'},
      }),
    ]);
    await _pump(tester, adapter);

    await tester.tap(find.text(_resendLabel));
    await tester.pump();
    await tester.tap(find.text(_resendLabel), warnIfMissed: false);
    await tester.runAsync(() => Future<void>.delayed(Duration.zero));
    await tester.pumpAndSettle();

    expect(adapter.callCount, 1);
  });
}
