import 'package:freezed_annotation/freezed_annotation.dart';

import '../clan/clan_membership.dart';
import '../shared/ids.dart';

part 'user_profile.freezed.dart';

@freezed
abstract class UserProfile with _$UserProfile {
  const factory UserProfile({
    required UserId id,
    required String email,
    required String? fullName,
    required ClanId? clanId,
    required String? clanName,
    // Non-null only when the membership is approved.
    required ClanRole? role,
    required bool isApproved,
    required bool hasPendingMembership,
    required PersonId? personId,
  }) = _UserProfile;

  const UserProfile._();

  /// Routing rule from frontend-integration-guide.md §5.
  bool get needsPendingScreen => !isApproved && hasPendingMembership;

  /// Neither approved nor pending, attached to no clan → onboarding.
  bool get needsOnboarding =>
      !isApproved && !hasPendingMembership && clanId == null;
}
