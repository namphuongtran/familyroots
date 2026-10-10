// Issue #204: sign-in used to call `POST /auth/login` and throw its tokens
// away, while every request read its bearer token from the Supabase client,
// which nothing had signed in. So the first authenticated request went out
// with no `Authorization` header.
//
// **Every reading here is a request on the wire or a screen, never a setter.**
// The Supabase auth client is a real `GoTrueClient` over a faked HTTP
// transport (`FakeGoTrue`), and the Dio is the real one with all five
// interceptors (`mainContainer`). So a header read below was put there by the
// interceptor, from the session the real client made out of the fake's answer.
// That is `.claude/rules/testing.md`, "A test pins an outcome, not a setting".
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:family_roots_mobile/app/app.dart';
import 'package:family_roots_mobile/app/router/routes.dart';
import 'package:family_roots_mobile/core/network/api_exception.dart';
import 'package:family_roots_mobile/features/auth/auth.dart';

import '../support/fake_gotrue.dart';
import '../support/load_app_fonts.dart';
import '../support/main_container.dart';
import '../support/sequence_adapter.dart';

/// `GET /auth/me`, the profile directly under `data`
/// (`docs/contracts/rest-auth-api.md`, `GET /me`).
const _me = <String, Object?>{
  'data': <String, Object?>{
    'id': 'u1',
    'email': 'minh@example.com',
    'full_name': 'Nguyễn Văn Minh',
    'clan_id': 'c1',
    'clan_name': 'Họ Lê',
    'role': 'admin',
    'is_approved': true,
    'has_pending_membership': false,
    'person_id': null,
    'preferred_locale': 'vi',
  },
};

/// What `get_current_user` answers for a deactivated account
/// (`backend/app/core/security.py`), after Supabase has already said yes.
const _deactivated = <String, Object?>{
  'error': <String, Object?>{
    'code': 'account_deactivated',
    'message': 'Tài khoản đã bị vô hiệu hoá',
    'detail': <String, Object?>{},
  },
};

/// Copied from `lib/core/l10n/app_vi.arb`, which copies the backend's
/// `auth.invalid_credentials` (`backend/app/i18n/vi.json`), so the person reads
/// what they read when the backend did the sign-in. Hard-coded rather than read
/// through `AppLocalizations`, which would assert nothing about which string
/// the screen chose.
const _viInvalidCredentials = 'Email hoặc mật khẩu không đúng';

Future<void> _signIn(ProviderContainer c) => c
    .read(sessionControllerProvider.notifier)
    .signIn(email: 'minh@example.com', password: 'secret');

String? _authorization(SequenceAdapter adapter, int index) =>
    adapter.received[index].headers['Authorization'] as String?;

void main() {
  setUpAll(loadAppFonts);

  test('the GET /auth/me that sign-in sends carries the token Supabase '
      'issued', () async {
    final goTrue = FakeGoTrue();
    final adapter = SequenceAdapter(<Canned>[const Canned(200, _me)]);
    final c = await mainContainer(adapter: adapter, goTrue: goTrue);
    addTearDown(c.dispose);

    await _signIn(c);

    expect(adapter.received.map((r) => r.path).toList(), <String>['/auth/me']);
    expect(
      _authorization(adapter, 0),
      'Bearer ${FakeGoTrue.accessToken}',
      reason:
          'the backend reads the caller from this header; without it '
          '/auth/me answers 401 missing_token',
    );
    expect(c.read(sessionControllerProvider).requireValue?.email, isNotNull);
    expect(goTrue.tokenGrants, <String?>['password']);
  });

  test('after sign-out, the next request carries no Authorization '
      'header', () async {
    final goTrue = FakeGoTrue();
    final adapter = SequenceAdapter(<Canned>[
      const Canned(200, _me),
      const Canned(200, _me),
    ]);
    final c = await mainContainer(adapter: adapter, goTrue: goTrue);
    addTearDown(c.dispose);

    await _signIn(c);
    expect(_authorization(adapter, 0), 'Bearer ${FakeGoTrue.accessToken}');

    await c.read(sessionControllerProvider.notifier).signOut();
    await c.read(authRepositoryProvider).me();

    expect(adapter.received, hasLength(2));
    expect(
      _authorization(adapter, 1),
      isNull,
      reason: 'a signed-out client must not keep sending the old token',
    );
    expect(c.read(sessionControllerProvider).requireValue, isNull);
  });

  test('a sign-in the backend refuses leaves no Supabase session '
      'behind', () async {
    final goTrue = FakeGoTrue();
    final adapter = SequenceAdapter(<Canned>[const Canned(403, _deactivated)]);
    final c = await mainContainer(adapter: adapter, goTrue: goTrue);
    addTearDown(c.dispose);

    await _signIn(c);

    final state = c.read(sessionControllerProvider);
    expect((state.error! as ApiException).code, 'account_deactivated');

    // The outcome that matters: nothing the app sends next carries the token
    // of a sign-in the backend turned down.
    await expectLater(
      c.read(authRepositoryProvider).me(),
      throwsA(isA<ApiException>()),
    );
    expect(_authorization(adapter, 0), 'Bearer ${FakeGoTrue.accessToken}');
    expect(_authorization(adapter, 1), isNull);
    expect(
      goTrue.client.currentSession,
      isNull,
      reason:
          'supabase_flutter persists whatever session the client holds to '
          'secure storage, so a held session outlives the refusal',
    );
    // Revoked server-side too, but only this session. The failure may be a
    // passing 5xx, and it must not sign the person out of the web as well.
    final revoke = goTrue.received.last;
    expect(revoke.url.path, endsWith('/logout'));
    expect(revoke.url.queryParameters['scope'], 'local');
  });

  testWidgets('a wrong password shows the localised message on the login '
      'screen, never the raw refusal', (tester) async {
    final adapter = SequenceAdapter(<Canned>[const Canned(200, _me)]);
    final c = await mainContainer(
      adapter: adapter,
      goTrue: FakeGoTrue(refusal: GoTrueRefusal.invalidCredentials),
    );
    addTearDown(c.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(container: c, child: const FamilyRootsApp()),
    );
    await tester.pumpAndSettle();

    // `runAsync`: an awaited request inside a widget test's fake-async zone
    // hangs instead of failing (mobile/CLAUDE.md, test-host trap 2).
    await tester.runAsync(() => _signIn(c));
    await tester.pumpAndSettle();

    expect(find.byKey(RouteKeys.login), findsOneWidget);
    expect(find.text(_viInvalidCredentials), findsOneWidget);
    expect(find.textContaining('Invalid login credentials'), findsNothing);
    expect(find.textContaining('AuthApiException'), findsNothing);
    expect(adapter.callCount, 0, reason: 'a refused sign-in asks no backend');
  });

  testWidgets('an unconfirmed address lands on /verify-email with the address '
      'in hand, and signing out leaves it for /login', (tester) async {
    final adapter = SequenceAdapter(<Canned>[
      const Canned(200, <String, Object?>{
        'data': <String, Object?>{'message': 'Đã gửi'},
      }),
    ]);
    final c = await mainContainer(
      adapter: adapter,
      goTrue: FakeGoTrue(refusal: GoTrueRefusal.emailNotConfirmed),
    );
    addTearDown(c.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(container: c, child: const FamilyRootsApp()),
    );
    await tester.pumpAndSettle();

    await tester.runAsync(() => _signIn(c));
    await tester.pumpAndSettle();

    expect(find.byKey(RouteKeys.verifyEmail), findsOneWidget);
    expect(find.byKey(RouteKeys.login), findsNothing);

    // The address reached the screen: resend is offered only when it is known,
    // and pressing it asks the backend for exactly that address.
    await tester.runAsync(() async {
      await tester.tap(find.text('Gửi lại email xác thực'));
      await Future<void>.delayed(const Duration(milliseconds: 50));
    });
    expect(adapter.received.single.path, '/auth/resend-verification');
    expect(adapter.received.single.data, <String, Object?>{
      'email': 'minh@example.com',
    });

    await tester.runAsync(() async {
      await tester.tap(find.text('Đăng xuất'));
      await Future<void>.delayed(const Duration(milliseconds: 50));
    });
    await tester.pumpAndSettle();
    expect(find.byKey(RouteKeys.login), findsOneWidget);
  });
}
