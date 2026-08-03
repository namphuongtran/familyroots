import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/l10n/generated/app_localizations.dart';
import '../application/session_controller.dart';
import 'message_page.dart';

/// M0 does not deep-link the verification email: spec §7 puts deep links out
/// of scope, so this screen offers POST /auth/resend-verification plus "open
/// your email" — both fully knowable without the owner action on R2.
class VerifyEmailPage extends ConsumerWidget {
  const VerifyEmailPage({super.key, this.email});

  /// Null when we do not know the address — a 403 `email_not_verified` at login
  /// means there is no session to read it from. Resend is then unavailable
  /// rather than sent to a guess; "open your email" still applies.
  final String? email;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context);
    final address = email;
    return MessagePage(
      title: l10n.verifyEmailTitle,
      body: l10n.verifyEmailBody,
      actionLabel: address == null ? null : l10n.resendVerificationAction,
      action: address == null
          ? null
          : () => ref.read(authRepositoryProvider).resendVerification(address),
    );
  }
}
