import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:family_roots_mobile/app/router/app_router.dart';
import 'package:family_roots_mobile/app/router/routes.dart';
import 'package:family_roots_mobile/core/l10n/generated/app_localizations.dart';
import 'package:family_roots_mobile/core/network/api_client.dart';
import 'package:family_roots_mobile/core/storage/prefs_store.dart';
import 'package:family_roots_mobile/core/theme/app_theme.dart';
import 'package:family_roots_mobile/domain/auth/user_profile.dart';
import 'package:family_roots_mobile/features/clan/clan.dart';

import '../support/load_app_fonts.dart';
import '../support/sequence_adapter.dart';

/// Two approved memberships, so the picker has something to render.
const _twoClans = Canned(200, <String, Object?>{
  'data': <Object?>[
    <String, Object?>{
      'clan_id': 'c1',
      'clan_name': 'Họ Nguyễn Phúc',
      'clan_slug': 'ho-nguyen-phuc',
      'role': 'admin',
      'joined_at': null,
    },
    <String, Object?>{
      'clan_id': 'c2',
      'clan_name': 'Họ Trần',
      'clan_slug': 'ho-tran',
      'role': 'viewer',
      'joined_at': null,
    },
  ],
});

ClanRepository _repo() => ClanRepository(
  ApiClient(
    Dio(BaseOptions(baseUrl: 'https://api.test/api/v1'))
      ..httpClientAdapter = SequenceAdapter(<Canned>[_twoClans]),
  ),
);

/// The real app shell minus bootstrap: real pages, real theme, real l10n.
/// Routing is what is under test, so the transport is canned.
Future<Widget> _app(GoRouterLike router, {AuthRouteState? auth}) async {
  SharedPreferences.setMockInitialValues(<String, Object>{});
  final prefs = await PrefsStore.open();
  return ProviderScope(
    overrides: [
      clanRepositoryProvider.overrideWithValue(_repo()),
      prefsStoreProvider.overrideWithValue(prefs),
      if (auth != null) authRouteStateProvider.overrideWithValue(auth),
    ],
    child: MaterialApp.router(
      routerConfig: router,
      theme: buildAppTheme(),
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      locale: const Locale('vi'),
    ),
  );
}

typedef GoRouterLike = RouterConfig<Object>;

void main() {
  setUpAll(loadAppFonts);

  testWidgets('unauthenticated lands on /login', (tester) async {
    final auth = AuthRouteState()..signedIn = false;
    await tester.pumpWidget(await _app(buildRouter(auth)));
    await tester.pumpAndSettle();
    expect(find.byKey(RouteKeys.login), findsOneWidget);
  });

  testWidgets('signing in reroutes to /clans via refreshListenable', (
    tester,
  ) async {
    final auth = AuthRouteState()..signedIn = false;
    await tester.pumpWidget(await _app(buildRouter(auth)));
    await tester.pumpAndSettle();
    expect(find.byKey(RouteKeys.login), findsOneWidget);

    auth.set(signedIn: true);
    await tester.pumpAndSettle();
    expect(find.byKey(RouteKeys.clans), findsOneWidget);
  });

  testWidgets('an unverified email is held on /verify-email', (tester) async {
    final auth = AuthRouteState()
      ..signedIn = true
      ..emailVerified = false;
    final router = buildRouter(auth);
    await tester.pumpWidget(await _app(router));
    await tester.pumpAndSettle();
    expect(find.byKey(RouteKeys.verifyEmail), findsOneWidget);

    router.go(Routes.clans);
    await tester.pumpAndSettle();
    expect(find.byKey(RouteKeys.verifyEmail), findsOneWidget);
  });

  // Both non-approved states share this route by design (spec § 7.2a). Which
  // copy each one gets is asserted in membership_route_test.dart, from a real
  // profile, because that is the half this router flag cannot express.
  for (final status in <MembershipStatus>[
    MembershipStatus.pending,
    MembershipStatus.onboarding,
  ]) {
    testWidgets('membership $status goes to /pending', (tester) async {
      final auth = AuthRouteState()
        ..signedIn = true
        ..membership = status;
      await tester.pumpWidget(await _app(buildRouter(auth)));
      await tester.pumpAndSettle();
      expect(find.byKey(RouteKeys.pending), findsOneWidget);
    });
  }

  testWidgets('a multi-clan user is sent to the picker and must navigate '
      'explicitly afterwards', (tester) async {
    final auth = AuthRouteState()
      ..signedIn = true
      ..needsClanPick = true;
    final router = buildRouter(auth);
    await tester.pumpWidget(await _app(router));
    await tester.pumpAndSettle();
    expect(find.byKey(RouteKeys.clanPicker), findsOneWidget);

    // VERIFIED go_router 17 semantics: clearing a guard condition does NOT
    // pull the user forward. redirect returns null for /clan-picker, so the
    // router stays put until the picker navigates itself.
    auth.set(needsClanPick: false);
    await tester.pumpAndSettle();
    expect(find.byKey(RouteKeys.clanPicker), findsOneWidget);

    router.go(Routes.clans);
    await tester.pumpAndSettle();
    expect(find.byKey(RouteKeys.clans), findsOneWidget);
  });

  testWidgets('picking a clan clears the guard and navigates, in that order', (
    tester,
  ) async {
    final auth = AuthRouteState()
      ..signedIn = true
      ..needsClanPick = true;
    await tester.pumpWidget(await _app(buildRouter(auth), auth: auth));
    await tester.pumpAndSettle();
    expect(find.byKey(RouteKeys.clanPicker), findsOneWidget);

    // onSelect must do BOTH, in order: clear needsClanPick, then go(). Either
    // half alone leaves the user stranded on the picker — navigating first is
    // redirected back because the guard still holds, and clearing alone does
    // not move them because redirect returns null for the current location.
    await tester.tap(find.text('Họ Trần'));
    await tester.pumpAndSettle();

    expect(find.byKey(RouteKeys.clans), findsOneWidget);
    expect(auth.needsClanPick, isFalse);
  });
}
