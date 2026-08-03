import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../../domain/auth/user_profile.dart';
import '../data/auth_repository.dart';

part 'session_controller.g.dart';

/// Infrastructure binding — overridden in ProviderScope at bootstrap.
final authRepositoryProvider = Provider<AuthRepository>(
  (ref) => throw UnimplementedError('override in ProviderScope'),
);

/// Signed-out is a state, not an error — hence UserProfile? rather than
/// throwing. keepAlive because the session outlives any one screen.
@Riverpod(keepAlive: true)
class SessionController extends _$SessionController {
  @override
  Future<UserProfile?> build() async => null;

  /// login → GET /auth/me, because the login response's
  /// has_pending_membership is always false (documented backend gap).
  Future<void> signIn({required String email, required String password}) async {
    state = const AsyncValue<UserProfile?>.loading();
    state = await AsyncValue.guard<UserProfile?>(() async {
      final repo = ref.read(authRepositoryProvider);
      await repo.login(email: email, password: password);
      return repo.me();
    });
  }

  Future<void> signOut() async {
    final repo = ref.read(authRepositoryProvider);
    try {
      await repo.logout();
    } on Object {
      // Logout is best-effort server-side; clear local state regardless.
    }
    state = const AsyncValue<UserProfile?>.data(null);
  }
}
