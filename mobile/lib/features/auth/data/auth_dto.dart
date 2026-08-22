import '../../../domain/auth/user_profile.dart';
import '../../../domain/clan/clan_membership.dart';
import '../../../domain/shared/ids.dart';

/// The only place that knows the backend's wire shape for auth, so a new
/// backend field changes exactly one file.
///
/// `preferred_locale` is deliberately not mapped: it always returns "vi"
/// regardless of what was saved (spec R3). The app owns locale in PrefsStore.
UserProfile userProfileFromJson(Object? json) {
  final m = json! as Map<String, Object?>;
  final clanId = m['clan_id'];
  final personId = m['person_id'];
  return UserProfile(
    id: UserId(m['id']! as String),
    email: m['email']! as String,
    // Kept nullable deliberately. The backend declares `full_name: str`
    // (non-nullable), so this is tolerance rather than a contract reading — a
    // client that crashes on an unexpected null is worse than one that renders
    // a blank name.
    fullName: m['full_name'] as String?,
    clanId: clanId is String ? ClanId(clanId) : null,
    clanName: m['clan_name'] as String?,
    role: m['role'] == null ? null : ClanRole.fromWire(m['role']),
    isApproved: m['is_approved'] as bool? ?? false,
    hasPendingMembership: m['has_pending_membership'] as bool? ?? false,
    personId: personId is String ? PersonId(personId) : null,
  );
}

class LoginResult {
  const LoginResult({
    required this.accessToken,
    required this.refreshToken,
    required this.expiresIn,
    required this.user,
  });

  final String accessToken;
  final String refreshToken;
  final int expiresIn;

  /// `has_pending_membership` HERE IS ALWAYS FALSE — the login handler never
  /// computes it. Call GET /auth/me and route on that value instead.
  final UserProfile user;
}

LoginResult loginResultFromJson(Object? json) {
  final m = json! as Map<String, Object?>;
  return LoginResult(
    accessToken: m['access_token']! as String,
    refreshToken: m['refresh_token']! as String,
    expiresIn: m['expires_in'] as int? ?? 3600,
    user: userProfileFromJson(m['user']),
  );
}
