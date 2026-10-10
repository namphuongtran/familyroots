import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:family_roots_mobile/core/network/api_client.dart';
import 'package:family_roots_mobile/core/network/api_exception.dart';
import 'package:family_roots_mobile/domain/auth/user_profile.dart';
import 'package:family_roots_mobile/features/auth/application/session_controller.dart';
import 'package:family_roots_mobile/features/auth/data/auth_repository.dart';
import 'package:family_roots_mobile/features/auth/data/supabase_auth.dart';

import '../../support/fake_gotrue.dart';
import '../../support/sequence_adapter.dart';

/// The controller over fake transports. Whether the bearer token reaches the
/// backend is read through the real Dio in `test/app/sign_in_session_test.dart`;
/// this file pins what the controller does with each answer.
ProviderContainer _container(SequenceAdapter adapter, FakeGoTrue goTrue) {
  final c = ProviderContainer(
    overrides: [
      authRepositoryProvider.overrideWithValue(
        AuthRepository(
          ApiClient(
            Dio(BaseOptions(baseUrl: 'https://api.test/api/v1'))
              ..httpClientAdapter = adapter,
          ),
        ),
      ),
      supabaseAuthProvider.overrideWithValue(SupabaseAuth(goTrue.client)),
    ],
  );
  addTearDown(c.dispose);
  return c;
}

const _meApproved = Canned(200, <String, Object?>{
  'data': <String, Object?>{
    'id': 'u1',
    'email': 'a@b.c',
    'full_name': 'A',
    'clan_id': 'c1',
    'clan_name': 'Họ A',
    'role': 'admin',
    'is_approved': true,
    'has_pending_membership': false,
    'person_id': null,
    'preferred_locale': 'vi',
  },
});

void main() {
  test('starts signed out', () async {
    final c = _container(SequenceAdapter(<Canned>[]), FakeGoTrue());
    expect(await c.read(sessionControllerProvider.future), isNull);
  });

  test('signIn signs in through Supabase, then reads GET /auth/me', () async {
    final adapter = SequenceAdapter(<Canned>[_meApproved]);
    final goTrue = FakeGoTrue();
    final c = _container(adapter, goTrue);

    await c.read(sessionControllerProvider.future);
    await c
        .read(sessionControllerProvider.notifier)
        .signIn(email: 'a@b.c', password: 'x');

    final profile = c.read(sessionControllerProvider).requireValue;
    expect(profile, isA<UserProfile>());
    expect(profile!.email, 'a@b.c');
    expect(profile.isApproved, isTrue);
    expect(goTrue.tokenGrants, <String?>['password']);
    expect(adapter.received.map((r) => r.path), <String>['/auth/me']);
  });

  test('a refused sign-in lands in AsyncError carrying Supabase\'s code, and '
      'asks the backend nothing', () async {
    final adapter = SequenceAdapter(<Canned>[_meApproved]);
    final c = _container(
      adapter,
      FakeGoTrue(refusal: GoTrueRefusal.invalidCredentials),
    );

    await c.read(sessionControllerProvider.future);
    await c
        .read(sessionControllerProvider.notifier)
        .signIn(email: 'a@b.c', password: 'wrong');

    final state = c.read(sessionControllerProvider);
    expect(state.hasError, isTrue);
    expect(state.error, isA<SupabaseAuthException>());
    expect((state.error! as SupabaseAuthException).code, 'invalid_credentials');
    expect(adapter.callCount, 0);
  });

  test('signOut clears the profile even if Supabase\'s revoke fails', () async {
    final goTrue = FakeGoTrue(logoutStatus: 503);
    final c = _container(SequenceAdapter(<Canned>[_meApproved]), goTrue);

    await c.read(sessionControllerProvider.future);
    await c
        .read(sessionControllerProvider.notifier)
        .signIn(email: 'a@b.c', password: 'x');
    expect(c.read(sessionControllerProvider).requireValue, isNotNull);

    await c.read(sessionControllerProvider.notifier).signOut();
    expect(c.read(sessionControllerProvider).requireValue, isNull);
    expect(goTrue.client.currentSession, isNull);
    expect(
      goTrue.received.last.url.path,
      endsWith('/logout'),
      reason: 'the revoke was asked for, and its 503 changed nothing',
    );
  });
}
