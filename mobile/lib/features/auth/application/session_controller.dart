import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

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
  Future<UserProfile?> build() async => null;

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
  Future<void> signOut() async {
    await ref.read(supabaseAuthProvider).signOut();
    state = const AsyncValue<UserProfile?>.data(null);
  }
}
