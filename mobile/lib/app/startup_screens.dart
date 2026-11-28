import 'package:flutter/material.dart';

import '../core/l10n/generated/app_localizations.dart';
import '../core/theme/app_theme.dart';

/// Shown when a startup step threw. Prefs are not open yet, so the locale is
/// the documented default, vi.
class StartupFailureApp extends StatelessWidget {
  const StartupFailureApp({super.key});

  @override
  Widget build(BuildContext context) => _StartupShell(
    message: (l10n) => (l10n.startupFailureTitle, l10n.startupFailureBody),
  );
}

/// Shown instead of calling `Supabase.initialize` when a required
/// `--dart-define` is empty. Names each missing define.
class MissingConfigApp extends StatelessWidget {
  const MissingConfigApp({super.key, required this.missing});

  final List<String> missing;

  @override
  Widget build(BuildContext context) => _StartupShell(
    message: (l10n) =>
        (l10n.missingConfigTitle, l10n.missingConfigBody(missing.join(', '))),
  );
}

class _StartupShell extends StatelessWidget {
  const _StartupShell({required this.message});

  final (String, String) Function(AppLocalizations l10n) message;

  @override
  Widget build(BuildContext context) => MaterialApp(
    theme: buildAppTheme(),
    localizationsDelegates: AppLocalizations.localizationsDelegates,
    supportedLocales: AppLocalizations.supportedLocales,
    locale: const Locale('vi'),
    home: Builder(
      builder: (context) {
        final (title, body) = message(AppLocalizations.of(context));
        return Scaffold(
          body: SafeArea(
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title, style: Theme.of(context).textTheme.titleLarge),
                  const SizedBox(height: 12),
                  Text(body),
                ],
              ),
            ),
          ),
        );
      },
    ),
  );
}
