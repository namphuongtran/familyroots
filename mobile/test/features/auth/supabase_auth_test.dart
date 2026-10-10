// What `SupabaseAuth` lets out. Like `ApiClient` for Dio, nothing above it may
// see the SDK's own exception, so each GoTrue failure is read here as the
// `AppException` it becomes.
import 'package:flutter_test/flutter_test.dart';

import 'package:family_roots_mobile/core/network/api_exception.dart';
import 'package:family_roots_mobile/features/auth/data/supabase_auth.dart';

import '../../support/fake_gotrue.dart';

void main() {
  test('a wrong password becomes SupabaseAuthException with GoTrue\'s code '
      'and the address', () async {
    final auth = SupabaseAuth(
      FakeGoTrue(refusal: GoTrueRefusal.invalidCredentials).client,
    );

    await expectLater(
      auth.signInWithPassword(email: 'minh@example.com', password: 'wrong'),
      throwsA(
        isA<SupabaseAuthException>()
            .having((e) => e.code, 'code', 'invalid_credentials')
            .having((e) => e.status, 'status', 400)
            .having((e) => e.email, 'email', 'minh@example.com'),
      ),
    );
    expect(auth.accessToken, isNull);
  });

  test(
    'an unconfirmed address keeps its code, which routes to verification',
    () async {
      final auth = SupabaseAuth(
        FakeGoTrue(refusal: GoTrueRefusal.emailNotConfirmed).client,
      );

      try {
        await auth.signInWithPassword(email: 'minh@example.com', password: 'x');
        fail('expected SupabaseAuthException');
      } on SupabaseAuthException catch (e) {
        expect(e.code, 'email_not_confirmed');
        expect(
          policyActionFor(e.code!, status: e.status),
          PolicyAction.resendVerification,
        );
      }
    },
  );

  test('no answer at all is a NetworkException, not a refusal', () async {
    final auth = SupabaseAuth(FakeGoTrue(offline: true).client);

    await expectLater(
      auth.signInWithPassword(email: 'minh@example.com', password: 'x'),
      throwsA(isA<NetworkException>()),
    );
  });

  test('a sign-in leaves the issued token for the Dio seam to read', () async {
    final auth = SupabaseAuth(FakeGoTrue().client);

    await auth.signInWithPassword(email: 'minh@example.com', password: 'x');

    expect(auth.accessToken, FakeGoTrue.accessToken);
  });

  test('a refresh with no session is an AppException, not gotrue\'s', () async {
    final auth = SupabaseAuth(FakeGoTrue().client);

    await expectLater(auth.refresh(), throwsA(isA<AppException>()));
  });

  test(
    'a refused refresh is a SupabaseAuthException with GoTrue\'s code',
    () async {
      final auth = SupabaseAuth(FakeGoTrue().client);
      await auth.signInWithPassword(email: 'minh@example.com', password: 'x');

      await expectLater(
        auth.refresh(),
        throwsA(
          isA<SupabaseAuthException>()
              .having((e) => e.code, 'code', 'refresh_token_not_found')
              .having((e) => e.email, 'email', isNull),
        ),
      );
    },
  );

  test('sign-out revokes every session of the user', () async {
    final goTrue = FakeGoTrue();
    final auth = SupabaseAuth(goTrue.client);
    await auth.signInWithPassword(email: 'minh@example.com', password: 'x');

    await auth.signOut();

    expect(auth.accessToken, isNull);
    final revoke = goTrue.received.last;
    expect(revoke.url.path, endsWith('/logout'));
    expect(
      revoke.url.queryParameters['scope'],
      'global',
      reason:
          'the backend\'s /auth/logout, which mobile called before #204, '
          'revoked every session, and the web\'s supabase-js signOut() does too',
    );
  });

  test('sign-out with the network gone still ends the session and never '
      'throws', () async {
    final goTrue = FakeGoTrue();
    final auth = SupabaseAuth(goTrue.client);
    await auth.signInWithPassword(email: 'minh@example.com', password: 'x');
    // Signed in, so gotrue does send the revoke, and it is that request that
    // gets no answer.
    goTrue.offline = true;

    await auth.signOut();

    expect(goTrue.received.last.url.path, endsWith('/logout'));
    expect(auth.accessToken, isNull);
  });
}
