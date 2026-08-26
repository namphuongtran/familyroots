import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:family_roots_mobile/app/app.dart';
import 'package:family_roots_mobile/app/router/routes.dart';
import 'package:family_roots_mobile/core/network/api_client.dart';
import 'package:family_roots_mobile/core/network/dio_provider.dart';
import 'package:family_roots_mobile/core/storage/cache_store.dart';
import 'package:family_roots_mobile/features/auth/auth.dart';
import 'package:family_roots_mobile/features/clan/clan.dart';

import '../support/load_app_fonts.dart';
import '../support/main_container.dart';
import '../support/sequence_adapter.dart';

/// The plan marks Task 18 as N9 — "this wiring was never assembled and run …
/// expect the first `flutter run` to surface an unoverridden provider". These
/// tests assemble exactly the override set `main.dart` supplies and read the
/// whole graph, so a missing override fails here instead of on a device.
///
/// The override set itself lives in `test/support/main_container.dart`, shared
/// with `membership_route_test.dart`, which drives the same assembled app.
void main() {
  setUpAll(loadAppFonts);

  test('every provider main.dart depends on resolves', () async {
    final c = await mainContainer();
    addTearDown(c.dispose);

    // Reading these is what would throw UnimplementedError for a provider
    // main.dart forgot to override.
    expect(c.read(dioProvider), isA<Dio>());
    expect(c.read(apiClientProvider), isA<ApiClient>());
    expect(c.read(authRepositoryProvider), isA<AuthRepository>());
    expect(c.read(clanRepositoryProvider), isA<ClanRepository>());
    expect(c.read(cacheStoreProvider), isA<CacheStore>());
    expect(c.read(onSignOutProvider), isA<void Function()>());
    expect(c.read(selectedClanProvider), isNull);
  });

  test(
    'the single Dio carries the five interceptors in the mandated order',
    () async {
      final c = await mainContainer();
      addTearDown(c.dispose);

      final dio = c.read(dioProvider);
      expect(dio.options.baseUrl, 'https://api.test/api/v1');
      expect(
        dio.interceptors.map((i) => i.runtimeType.toString()),
        containsAllInOrder(<String>[
          'AuthInterceptor',
          'ClanInterceptor',
          'LocaleInterceptor',
          'TraceInterceptor',
          // Refresh must be LAST so the header interceptors have already run on
          // the retried request.
          'RefreshInterceptor',
        ]),
      );
    },
  );

  testWidgets('the app shell builds and lands on /login when signed out', (
    tester,
  ) async {
    final c = await mainContainer();
    addTearDown(c.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(container: c, child: const FamilyRootsApp()),
    );
    await tester.pumpAndSettle();

    // Proves MaterialApp.router, the theme, l10n and the guard chain all
    // assemble together — the composition the plan never ran.
    expect(find.byKey(RouteKeys.login), findsOneWidget);
    expect(find.text('Đăng nhập'), findsWidgets);
  });

  testWidgets('launching signed out issues no HTTP request', (tester) async {
    // Regression pin. Watching clanResolutionProvider from the app shell
    // instead of clanPickRequiredProvider fired GET /me/clans at launch: an
    // unauthenticated request that 401s, after which the refresh interceptor
    // finds no session and signs the user out — caused by opening the app.
    final adapter = SequenceAdapter(<Canned>[
      const Canned(200, <String, Object?>{'data': <Object?>[]}),
    ]);
    final c = await mainContainer(adapter: adapter);
    addTearDown(c.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(container: c, child: const FamilyRootsApp()),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(RouteKeys.login), findsOneWidget);
    expect(
      adapter.callCount,
      0,
      reason: 'the login screen must not depend on any network call',
    );
  });
}
