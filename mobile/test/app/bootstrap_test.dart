import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:family_roots_mobile/app/bootstrap.dart';

/// `Supabase.initialize` and `SentryFlutter.init` need platform channels, so
/// both are parameters here. What these tests read is the outcome: which
/// screen is up, what the reporter received, and which steps ran.
void main() {
  group('missingDefines', () {
    test('an empty SUPABASE_URL is reported alone', () {
      expect(missingDefines(supabaseUrl: '', supabasePublishableKey: 'key'), [
        'SUPABASE_URL',
      ]);
    });

    test('both empty are named, in order', () {
      expect(missingDefines(supabaseUrl: '', supabasePublishableKey: ''), [
        'SUPABASE_URL',
        'SUPABASE_PUBLISHABLE_KEY',
      ]);
    });

    test('a full set reports nothing', () {
      expect(
        missingDefines(
          supabaseUrl: 'https://x.test',
          supabasePublishableKey: 'k',
        ),
        isEmpty,
      );
    });
  });

  group('bootstrap', () {
    late List<Object> reported;
    late List<String> ran;
    late Widget? shown;

    setUp(() {
      reported = [];
      ran = [];
      shown = null;
    });

    Future<void> boot({
      String url = 'https://x.test',
      String key = 'k',
      Future<void> Function()? initSupabase,
      Future<Widget Function()> Function()? prepare,
    }) {
      return bootstrap(
        supabaseUrl: url,
        supabasePublishableKey: key,
        sentryDsn: '',
        // Stands in for SentryFlutter.init: only the appRunner is guarded.
        runWithSentry: (appRunner) async {
          ran.add('sentry');
          await appRunner();
        },
        reportError: (e, s) => reported.add(e),
        initSupabase:
            initSupabase ??
            () async {
              ran.add('supabase');
            },
        prepare:
            prepare ??
            () async {
              ran.add('prepare');
              return () => const Text('app', textDirection: TextDirection.ltr);
            },
        run: (w) => shown = w,
      );
    }

    testWidgets(
      'a throwing Supabase step reaches the reporter and ends in a frame',
      (tester) async {
        final boom = StateError('keychain');
        await boot(initSupabase: () async => throw boom);
        expect(reported, [boom]);
        await tester.pumpWidget(shown!);
        await tester.pumpAndSettle();
        expect(find.text('Không thể khởi động ứng dụng'), findsOneWidget);
      },
    );

    testWidgets('a throwing prepare step (prefs, cache) is reported too', (
      tester,
    ) async {
      final boom = StateError('sqflite');
      await boot(prepare: () async => throw boom);
      expect(reported, [boom]);
      await tester.pumpWidget(shown!);
      await tester.pumpAndSettle();
      expect(find.text('Không thể khởi động ứng dụng'), findsOneWidget);
    });

    testWidgets('an empty URL skips Supabase and names the define', (
      tester,
    ) async {
      await boot(url: '');
      expect(ran, ['sentry']);
      expect(reported, isEmpty);
      await tester.pumpWidget(shown!);
      await tester.pumpAndSettle();
      expect(find.textContaining('SUPABASE_URL'), findsOneWidget);
      expect(find.textContaining('SUPABASE_PUBLISHABLE_KEY'), findsNothing);
    });

    testWidgets('a healthy start runs sentry, then supabase, then the app', (
      tester,
    ) async {
      await boot();
      expect(ran, ['sentry', 'supabase', 'prepare']);
      expect(reported, isEmpty);
      await tester.pumpWidget(shown!);
      expect(find.text('app'), findsOneWidget);
    });
  });
}
