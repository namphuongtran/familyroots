import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../../core/network/api_exception.dart';
import '../../../core/network/dio_provider.dart';
import '../../clan/clan.dart';
import '../../../domain/auth/user_profile.dart';
import '../data/auth_repository.dart';
import '../data/supabase_auth.dart';

part 'session_controller.g.dart';

/// Infrastructure binding — overridden in ProviderScope at bootstrap.
final authRepositoryProvider = Provider<AuthRepository>(
  (ref) => throw UnimplementedError('override in ProviderScope'),
);

/// Infrastructure binding, overridden in ProviderScope at bootstrap with the
/// same [SupabaseAuth] the Dio seams read the token from.
final supabaseAuthProvider = Provider<SupabaseAuth>(
  (ref) => throw UnimplementedError('override in ProviderScope'),
);

/// Signed-out is a state, not an error — hence UserProfile? rather than
/// throwing. keepAlive because the session outlives any one screen.
@Riverpod(keepAlive: true)
class SessionController extends _$SessionController {
  @override
  Future<UserProfile?> build() async {
    final auth = ref.read(supabaseAuthProvider);
    // A session ended elsewhere (revoked server-side, refresh token lost) must
    // reach the router, which only listens to this state.
    final sub = auth.signedOut.listen((_) async {
      await _forgetUser();
      state = const AsyncValue<UserProfile?>.data(null);
    });
    ref.onDispose(sub.cancel);

    // A session Supabase persisted across a relaunch. No session, no request.
    if (!auth.hasSession) return null;
    try {
      return await ref.read(authRepositoryProvider).me();
    } on ApiException {
      // The backend refused a session Supabase still holds, such as 403
      // account_deactivated: clear it, as signIn does, and show /login.
      await auth.signOut(everywhere: false);
      return null;
    }
  }

  /// Supabase's password sign-in, then GET /auth/me for the profile
  /// (ADR-064). The backend's `POST /auth/login` is not called: its tokens
  /// would have to be handed to the Supabase client, which is where every
  /// request reads its bearer token from.
  Future<void> signIn({required String email, required String password}) async {
    final auth = ref.read(supabaseAuthProvider);
    final repo = ref.read(authRepositoryProvider);
    state = const AsyncValue<UserProfile?>.loading();
    state = await AsyncValue.guard<UserProfile?>(() async {
      await auth.signInWithPassword(email: email, password: password);
      try {
        return await repo.me();
      } on Object {
        // Supabase said yes and the backend said no, such as 403
        // account_deactivated. The session must not outlive that answer in
        // secure storage, half signed in. This device's session only: the
        // failure may be a passing 5xx, and the person's other sessions did
        // nothing wrong.
        await auth.signOut(everywhere: false);
        rethrow;
      }
    });
  }

  /// Through Supabase, which also revokes the session server-side.
  ///
  /// [everywhere] is true for the person pressing "sign out", who gets every
  /// session revoked. A sign-out the person did not ask for, such as the refresh
  /// interceptor's, passes false and revokes only this device's session.
  Future<void> signOut({bool everywhere = true}) async {
    try {
      await ref.read(supabaseAuthProvider).signOut(everywhere: everywhere);
    } finally {
      // Even when revoking fails: the next person must not see this one's data.
      await _forgetUser();
    }
    state = const AsyncValue<UserProfile?>.data(null);
  }

  /// Everything the previous user left readable: the persisted clan choice
  /// (read first by the next request's X-Current-Clan-Id), the response cache,
  /// and the keepAlive clan providers.
  Future<void> _forgetUser() async {
    await ref.read(prefsStoreProvider).clearClanId();
    await ref.read(cacheStoreProvider).clear();
    ref
      ..invalidate(selectedClanProvider)
      ..invalidate(myClansProvider)
      ..invalidate(clanResolutionProvider);
  }
}
