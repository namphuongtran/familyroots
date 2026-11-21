// Issue #368: a relaunch with a persisted Supabase session used to land on
// /login, because the controller's initial state was always null.
//
// Every reading is a screen. The stored session is one a real `GoTrueClient`
// holds before the app is built (what `supabase_flutter` restores at launch).
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gotrue/gotrue.dart';

import 'package:family_roots_mobile/app/app.dart';
import 'package:family_roots_mobile/app/router/routes.dart';
import 'package:family_roots_mobile/features/auth/auth.dart';

import '../support/fake_gotrue.dart';
import '../support/load_app_fonts.dart';
import '../support/main_container.dart';
import '../support/sequence_adapter.dart';

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

const _deactivated = <String, Object?>{
  'error': <String, Object?>{
    'code': 'account_deactivated',
    'message': 'Tài khoản đã bị vô hiệu hoá',
    'detail': <String, Object?>{},
  },
};

const _clans = <String, Object?>{
  'data': <Object?>[],
  'meta': <String, Object?>{'cursor': null, 'has_more': false, 'limit': 50},
};

Future<ProviderContainer> _launch(
  WidgetTester tester,
  SequenceAdapter adapter,
  FakeGoTrue goTrue,
) async {
  // The session a previous launch left behind.
  await tester.runAsync(
    () => goTrue.client.signInWithPassword(
      email: 'minh@example.com',
      password: 'x',
    ),
  );
  final c = await mainContainer(adapter: adapter, goTrue: goTrue);
  addTearDown(c.dispose);
  // Started under runAsync: a request begun inside the fake-async zone hangs
  // (mobile/CLAUDE.md, test-host trap 2). The app then finds it resolved.
  await tester.runAsync(() => c.read(sessionControllerProvider.future));
  await tester.pumpWidget(
    UncontrolledProviderScope(container: c, child: const FamilyRootsApp()),
  );
  await tester.pumpAndSettle();
  return c;
}

void main() {
  setUpAll(loadAppFonts);

  testWidgets('a persisted session opens the signed-in route, not /login', (
    tester,
  ) async {
    final adapter = SequenceAdapter(<Canned>[
      const Canned(200, _me),
      const Canned(200, _clans),
      const Canned(200, _clans),
    ]);
    await _launch(tester, adapter, FakeGoTrue());

    expect(adapter.received.first.path, '/auth/me');
    expect(find.byKey(RouteKeys.login), findsNothing);
    expect(find.byKey(RouteKeys.clans), findsOneWidget);
  });

  testWidgets('a Supabase sign-out event moves the app to /login', (
    tester,
  ) async {
    final adapter = SequenceAdapter(<Canned>[
      const Canned(200, _me),
      const Canned(200, _clans),
      const Canned(200, _clans),
    ]);
    final goTrue = FakeGoTrue();
    await _launch(tester, adapter, goTrue);
    expect(find.byKey(RouteKeys.clans), findsOneWidget);

    await tester.runAsync(
      () => goTrue.client.signOut(scope: SignOutScope.local),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(RouteKeys.login), findsOneWidget);
  });

  testWidgets('a refused /auth/me clears the stored session and shows /login', (
    tester,
  ) async {
    final adapter = SequenceAdapter(<Canned>[const Canned(403, _deactivated)]);
    final goTrue = FakeGoTrue();
    await _launch(tester, adapter, goTrue);

    expect(find.byKey(RouteKeys.login), findsOneWidget);
    expect(goTrue.client.currentSession, isNull);
  });
}
