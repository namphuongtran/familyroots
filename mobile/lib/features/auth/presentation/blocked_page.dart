import 'package:flutter/material.dart';

import '../../../core/l10n/generated/app_localizations.dart';
import 'message_page.dart';

/// Which terminal block the user hit. Both are dead ends within the app —
/// sign-out is the only exit, which MessagePage always offers.
enum BlockedReason {
  /// `403 account_deactivated`.
  account,

  /// `403 clan_suspended`.
  clanSuspended,
}

class BlockedPage extends StatelessWidget {
  const BlockedPage({super.key, required this.reason});

  final BlockedReason reason;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    return MessagePage(
      title: switch (reason) {
        BlockedReason.account => l10n.accountBlockedTitle,
        BlockedReason.clanSuspended => l10n.clanSuspendedTitle,
      },
    );
  }
}
