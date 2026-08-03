import '../../../core/network/api_client.dart';
import '../../../domain/auth/user_profile.dart';
import 'auth_dto.dart';

class AuthRepository {
  AuthRepository(this._api);
  final ApiClient _api;

  Future<LoginResult> login({
    required String email,
    required String password,
  }) => _api.post<LoginResult>(
    '/auth/login',
    body: <String, Object?>{'email': email, 'password': password},
    parse: loginResultFromJson,
  );

  /// Joined on approved memberships only, and with a real
  /// has_pending_membership — unlike the login response.
  Future<UserProfile> me() =>
      _api.getOne<UserProfile>('/auth/me', parse: userProfileFromJson);

  /// Always 200 with the same message (non-enumerating).
  Future<String> resendVerification(String email) => _api.post<String>(
    '/auth/resend-verification',
    body: <String, Object?>{'email': email},
    parse: (j) => (j! as Map<String, Object?>)['message']! as String,
  );

  /// Best-effort server-side revoke. The access token stays valid until it
  /// expires, so clear all client state regardless.
  Future<void> logout() => _api.post<Object?>('/auth/logout', parse: (j) => j);
}
