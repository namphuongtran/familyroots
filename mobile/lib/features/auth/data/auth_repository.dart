import '../../../core/network/api_client.dart';
import '../../../domain/auth/user_profile.dart';
import 'auth_dto.dart';

class AuthRepository {
  AuthRepository(this._api);
  final ApiClient _api;

  /// Joined on approved memberships only, and with a real
  /// has_pending_membership. Sign-in itself is Supabase's (`SupabaseAuth`).
  Future<UserProfile> me() =>
      _api.getOne<UserProfile>('/auth/me', parse: userProfileFromJson);

  /// Always 200 with the same message (non-enumerating).
  Future<String> resendVerification(String email) => _api.post<String>(
    '/auth/resend-verification',
    body: <String, Object?>{'email': email},
    parse: (j) => (j! as Map<String, Object?>)['message']! as String,
  );
}
