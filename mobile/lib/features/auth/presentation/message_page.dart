import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/l10n/generated/app_localizations.dart';
import '../../../core/theme/tokens.dart';
import '../application/session_controller.dart';

/// The shared shape of every blocked/waiting state: a title, an optional body,
/// an optional action, and always a way out via sign-out.
///
/// [body] is nullable because the ARB gives explanatory copy for the pending
/// and verify states but only a title for the blocked ones. Inventing product
/// copy here is the design system's job, not this task's.
class MessagePage extends ConsumerWidget {
  const MessagePage({
    super.key,
    required this.title,
    this.body,
    this.action,
    this.actionLabel,
  });

  final String title;
  final String? body;
  final Future<void> Function()? action;
  final String? actionLabel;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context);
    final t = context.tokens;
    return Scaffold(
      appBar: AppBar(title: Text(title)),
      body: Padding(
        padding: EdgeInsets.all(t.spaceLg),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            if (body != null) Text(body!),
            SizedBox(height: t.spaceLg),
            if (action != null && actionLabel != null)
              FilledButton(onPressed: action, child: Text(actionLabel!)),
            SizedBox(height: t.spaceMd),
            TextButton(
              onPressed: () =>
                  ref.read(sessionControllerProvider.notifier).signOut(),
              child: Text(l10n.signOutAction),
            ),
          ],
        ),
      ),
    );
  }
}
