import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:family_roots_mobile/app/bootstrap.dart';

import '../support/load_app_fonts.dart';

Future<void> _inline(FutureOr<void> Function() appRunner, String dsn) async =>
    appRunner();

void main() {
  setUpAll(loadAppFonts);

  group('missingDefines', () {
    test('an empty SUPABASE_URL reports exactly SUPABASE_URL', () {
      expect(
        missingDefines(supabaseUrl: '', supabasePublishableKey: 'k'),
        <String>['SUPABASE_URL'],
      );
    });

    test('both empty reports both, a full set reports nothing', () {
      expect(
        missingDefines(supabaseUrl: '', supabasePublishableKey: ''),
        <String>['SUPABASE_URL', 'SUPABASE_PUBLISHABLE_KEY'],
      );
      expect(
        missingDefines(supabaseUrl: 'u', supabasePublishableKey: 'k'),
        isEmpty,
      );
    });
  });

  testWidgets('a throwing Supabase step is reported and shows the failure', (
    tester,
  ) async {
    final reported = <Object>[];
    await bootstrap(
      supabaseUrl: 'https://x.test',
      supabasePublishableKey: 'k',
      sentryDsn: '',
      runWithSentry: _inline,
      initSupabase: (_, _) async => throw StateError('keychain'),
      reportError: (e, _) => reported.add(e),
      appBuilder: () async => const SizedBox(),
    );
    await tester.pumpAndSettle();

    expect(find.text('Không thể khởi động ứng dụng'), findsOneWidget);
    expect(reported.single, isA<StateError>());
  });

  testWidgets('a throwing appBuilder (prefs/cache open) is reported too', (
    tester,
  ) async {
    final reported = <Object>[];
    await bootstrap(
      supabaseUrl: 'u',
      supabasePublishableKey: 'k',
      sentryDsn: '',
      runWithSentry: _inline,
      initSupabase: (_, _) async {},
      reportError: (e, _) => reported.add(e),
      appBuilder: () async => throw StateError('sqflite'),
    );
    await tester.pumpAndSettle();

    expect(find.text('Không thể khởi động ứng dụng'), findsOneWidget);
    expect(reported, hasLength(1));
  });

  testWidgets('empty URL skips Supabase and names the missing define', (
    tester,
  ) async {
    var supabaseCalled = false;
    await bootstrap(
      supabaseUrl: '',
      supabasePublishableKey: 'k',
      sentryDsn: '',
      runWithSentry: _inline,
      initSupabase: (_, _) async => supabaseCalled = true,
      reportError: (_, _) {},
      appBuilder: () async => const SizedBox(),
    );
    await tester.pumpAndSettle();

    expect(supabaseCalled, isFalse);
    expect(find.textContaining('SUPABASE_URL'), findsOneWidget);
    expect(find.textContaining('SUPABASE_PUBLISHABLE_KEY'), findsNothing);
  });
}
