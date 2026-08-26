import 'package:flutter/material.dart';

import '../../../core/l10n/generated/app_localizations.dart';
import '../../../domain/auth/user_profile.dart';
import 'message_page.dart';

/// Spec § 7.2a, both variants of it
/// (`docs/superpowers/specs/2026-08-02-design-system-and-screens.md:925-927`).
/// The screen a signed-in user without an approved membership reaches, and the
/// copy depends on *why* they have none:
///
/// * [MembershipStatus.pending] — they asked to join and an admin has not
///   answered yet. This is the sentence that used to be shown to everybody.
/// * [MembershipStatus.onboarding] — they belong to no clan and asked to join
///   none, so "your request is waiting" is false for them. The spec pairs this
///   variant with the join/create control from § 7.1b. **Mobile has no register
///   screen to carry that control**, so the copy says the step is missing
///   instead of drawing a button that goes nowhere. When that screen lands,
///   `onboardingUnavailableBody` is the string to delete.
///
/// The decision is read from the profile `GET /auth/me` returned, through
/// [UserProfile.membershipStatus] — the same getter the router's guard reads,
/// so the screen cannot contradict the guard that sent the user here.
///
/// No copy promises a notification, because no notification exists for any
/// queue event. `docs/SEEDS.md` carries that in its `Owed` register: "A
/// notifications API. None exists, and the design spec refuses to draw a bell
/// for one."
class PendingApprovalPage extends StatelessWidget {
  const PendingApprovalPage({super.key, required this.status});

  final MembershipStatus status;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    return switch (status) {
      MembershipStatus.onboarding => MessagePage(
        title: l10n.onboardingTitle,
        body: l10n.onboardingUnavailableBody,
      ),
      // `approved` is not a destination — the redirect only sends a
      // non-approved user here — but it is reachable for the frame between a
      // refetch approving the user and the router acting on it, so it renders
      // rather than throwing.
      MembershipStatus.pending || MembershipStatus.approved => MessagePage(
        title: l10n.pendingApprovalTitle,
        body: l10n.pendingApprovalBody,
      ),
    };
  }
}
