import 'package:flutter/material.dart';

import '../../../core/l10n/generated/app_localizations.dart';
import 'message_page.dart';

/// Reached when GET /auth/me reports `is_approved: false` with
/// `has_pending_membership: true` — the login response's flag is always false
/// and must never be used for this decision.
///
/// No copy promises a notification, because no notification exists for any
/// queue event. `docs/SEEDS.md` carries that in its `Owed` register: "A
/// notifications API. None exists, and the design spec refuses to draw a bell
/// for one."
class PendingApprovalPage extends StatelessWidget {
  const PendingApprovalPage({super.key});

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    return MessagePage(
      title: l10n.pendingApprovalTitle,
      body: l10n.pendingApprovalBody,
    );
  }
}
