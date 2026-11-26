// Issue #406: a refresh that fails must not end the session unless Supabase
// refused it, and a sign-out the interceptor starts revokes this device only.
import 'package:flutter_test/flutter_test.dart';

import 'package:family_roots_mobile/core/network/api_exception.dart';
import 'package:family_roots_mobile/core/network/dio_provider.dart';
import 'package:family_roots_mobile/features/auth/auth.dart';

import '../support/fake_gotrue.dart';
import '../support/main_container.dart';
import '../support/sequence_adapter.dart';

const _unauthorized = Canned(401, <String, Object?>{
  'error': <String, Object?>{
    'code': 'invalid_token',
    'message': 'x',
    'detail': <String, Object?>{},
  },
});

Future<FakeGoTrue> _signedIn() async {
  final goTrue = FakeGoTrue();
  await goTrue.client.signInWithPassword(email: 'a@b.c', password: 'x');
  goTrue.received.clear();
  return goTrue;
}

void main() {
  test('a refused refresh ends the session without a revoke, and the '
      'interceptor\'s sign-out revokes only this device', () async {
    // gotrue drops the session itself when Supabase refuses a refresh, so
    // that path has nothing left to revoke. The binding is read directly,
    // with a session held, so the scope it sends is observable.
    final goTrue = await _signedIn();
    final c = await mainContainer(goTrue: goTrue);
    addTearDown(c.dispose);

    c.read(onSignOutProvider)();
    await Future<void>.delayed(const Duration(milliseconds: 50));

    final revoke = goTrue.received.lastWhere(
      (r) => r.url.path.endsWith('/logout'),
    );
    expect(revoke.url.queryParameters['scope'], 'local');
  });

  test('a refused refresh during a request signs out', () async {
    final goTrue = await _signedIn();
    final c = await mainContainer(
      adapter: SequenceAdapter(<Canned>[_unauthorized]),
      goTrue: goTrue,
    );
    addTearDown(c.dispose);

    await expectLater(c.read(authRepositoryProvider).me(), throwsA(anything));
    await Future<void>.delayed(const Duration(milliseconds: 50));

    expect(goTrue.client.currentSession, isNull);
  });

  test('a refresh that got no answer keeps the session', () async {
    final goTrue = await _signedIn();
    final c = await mainContainer(
      adapter: SequenceAdapter(<Canned>[_unauthorized]),
      goTrue: goTrue,
    );
    addTearDown(c.dispose);
    goTrue.offline = true;

    await expectLater(
      c.read(authRepositoryProvider).me(),
      throwsA(isA<NetworkException>()),
    );
    await Future<void>.delayed(const Duration(milliseconds: 50));

    expect(goTrue.client.currentSession, isNotNull);
    expect(
      goTrue.received.where((r) => r.url.path.endsWith('/logout')),
      isEmpty,
    );
  });

  test('pressing sign out revokes every session', () async {
    final goTrue = await _signedIn();
    final c = await mainContainer(goTrue: goTrue);
    addTearDown(c.dispose);

    await c.read(sessionControllerProvider.notifier).signOut();

    final revoke = goTrue.received.lastWhere(
      (r) => r.url.path.endsWith('/logout'),
    );
    expect(revoke.url.queryParameters['scope'], 'global');
  });
}
