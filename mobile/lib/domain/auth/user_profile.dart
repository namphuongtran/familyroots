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

  /// The one answer the router and the screen both read, so the two cannot
  /// disagree about which of § 7.2a's variants this profile belongs on.
  ///
  /// Total by construction: every profile maps to exactly one status. The two
  /// predicates above are the contract's own two sentences
  /// (`docs/contracts/frontend-integration-guide.md:306-308`), read in that
  /// order.
  MembershipStatus get membershipStatus {
    if (isApproved) return MembershipStatus.approved;
    if (needsPendingScreen) return MembershipStatus.pending;
    if (needsOnboarding) return MembershipStatus.onboarding;
    // The leftover combination is `!isApproved && !hasPendingMembership &&
    // clanId != null`, and the backend cannot emit it: `clan_id` names one
    // membership row and `is_approved` describes that same row
    // (`docs/contracts/rest-auth-api.md:132-133`), while
    // `has_pending_membership` is true whenever *any* row has
    // `is_approved = false` (`:124-125`). A named clan with no approval is such
    // a row. It is answered rather than asserted because the honest reading of
    // "attached to a clan, not approved" is still "waiting", and no screen
    // should be invented for a state the contract forbids.
    return MembershipStatus.pending;
  }
}

/// Which screen a signed-in user belongs on, per design spec § 7.2a
/// (`docs/superpowers/specs/2026-08-02-design-system-and-screens.md:925-927`).
///
/// [onboarding] and [pending] share one route on purpose: the spec calls the
/// no-membership case the "onboarding variant of this screen", not a fourth
/// screen. What differs is the copy, because only one of the two sentences is
/// true for any given user.
enum MembershipStatus { approved, pending, onboarding }
