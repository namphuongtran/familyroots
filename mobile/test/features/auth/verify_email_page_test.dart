// #407: the resend button must show the backend's message, show ErrorView's text
// on failure, and send one request for two quick presses.
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:family_roots_mobile/core/l10n/generated/app_localizations.dart';
import 'package:family_roots_mobile/core/network/api_client.dart';
import 'package:family_roots_mobile/core/theme/app_theme.dart';
import 'package:family_roots_mobile/features/auth/auth.dart';

import '../../support/sequence_adapter.dart';

const _sent = 'Nếu địa chỉ này tồn tại, chúng tôi đã gửi email xác minh.';
const _limited = 'Bạn thử quá nhiều lần, hãy đợi một lát.';

Future<SequenceAdapter> _pump(WidgetTester tester, Canned canned) async {
  final adapter = SequenceAdapter(<Canned>[canned]);
  final dio = Dio(BaseOptions(baseUrl: 'https://api.test/api/v1'))
    ..httpClientAdapter = adapter;
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        authRepositoryProvider.overrideWithValue(
          AuthRepository(ApiClient(dio)),
        ),
      ],
      child: MaterialApp(
        locale: const Locale('vi'),
        theme: buildAppTheme(),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: const VerifyEmailPage(email: 'minh@example.com'),
      ),
    ),
  );
  return adapter;
}

void main() {
  testWidgets('a 200 shows the backend message', (tester) async {
    final adapter = await _pump(
      tester,
      const Canned(200, <String, Object?>{
        'data': <String, Object?>{'message': _sent},
      }),
    );
    await tester.runAsync(() async {
      await tester.tap(find.byType(FilledButton));
      await Future<void>.delayed(const Duration(milliseconds: 50));
    });
    await tester.pump();
    expect(find.text(_sent), findsOneWidget);
    expect(adapter.callCount, 1);
  });

  testWidgets('a 429 shows the ErrorView text and nothing escapes', (
    tester,
  ) async {
    await _pump(
      tester,
      const Canned(429, <String, Object?>{
        'error': <String, Object?>{
          'code': 'rate_limited',
          'message': _limited,
          'detail': <String, Object?>{},
        },
      }),
    );
    await tester.runAsync(() async {
      await tester.tap(find.byType(FilledButton));
      await Future<void>.delayed(const Duration(milliseconds: 50));
    });
    await tester.pump();
    expect(find.text(_limited), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('two quick presses send one request', (tester) async {
    final adapter = await _pump(
      tester,
      const Canned(200, <String, Object?>{
        'data': <String, Object?>{'message': _sent},
      }),
    );
    await tester.runAsync(() async {
      await tester.tap(find.byType(FilledButton));
      await tester.pump();
      await tester.tap(find.byType(FilledButton), warnIfMissed: false);
      await Future<void>.delayed(const Duration(milliseconds: 50));
    });
    await tester.pump();
    expect(adapter.callCount, 1);
  });
}
