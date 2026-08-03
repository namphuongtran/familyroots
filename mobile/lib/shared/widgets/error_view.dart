import 'package:flutter/material.dart';

import '../../core/l10n/generated/app_localizations.dart';
import '../../core/network/api_exception.dart';
import '../../core/theme/tokens.dart';

/// The one place an AppException becomes user-facing text.
///
/// `ApiException.message` is already localised server-side from
/// Accept-Language and is shown verbatim — never parsed, never re-translated.
/// The ARB fallbacks exist only for failures that never reached the server.
class ErrorView extends StatelessWidget {
  const ErrorView({super.key, required this.error, this.onRetry});

  final Object error;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final t = context.tokens;

    final (String text, String? traceId) = switch (error) {
      // Already localised server-side — display it, never parse it.
      ApiException(:final message, :final traceId) => (message, traceId),
      NetworkException() => (l10n.errorOffline, null),
      TimeoutException() => (l10n.errorTimeout, null),
      MalformedResponseException() => (l10n.errorUnexpected, null),
      _ => (l10n.errorUnexpected, null),
    };

    return Container(
      padding: EdgeInsets.all(t.spaceMd),
      decoration: BoxDecoration(
        color: t.surfaceContainerLow,
        borderRadius: BorderRadius.circular(t.radiusNode),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(text, style: TextStyle(color: t.error)),
          if (traceId != null) ...<Widget>[
            SizedBox(height: t.spaceXs),
            Text(
              l10n.errorTraceId(traceId),
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ],
          if (onRetry != null) ...<Widget>[
            SizedBox(height: t.spaceSm),
            FilledButton(onPressed: onRetry, child: Text(l10n.retryAction)),
          ],
        ],
      ),
    );
  }
}
