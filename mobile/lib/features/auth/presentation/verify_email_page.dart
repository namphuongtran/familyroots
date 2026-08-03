import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/l10n/generated/app_localizations.dart';
import '../application/session_controller.dart';
import 'message_page.dart';

/// M0 does not deep-link the verification email: spec §7 puts deep links out
/// of scope, so this screen offers POST /auth/resend-verification plus "open
/// your email" — both fully knowable without the owner action on R2.
class VerifyEmailPage extends ConsumerWidget {
  const VerifyEmailPage({super.key, required this.email});

  final String email;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context);
    return MessagePage(
      title: l10n.verifyEmailTitle,
      body: l10n.verifyEmailBody,
      actionLabel: l10n.resendVerificationAction,
      action: () => ref.read(authRepositoryProvider).resendVerification(email),
    );
  }
}
