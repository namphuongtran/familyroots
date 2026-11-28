import 'package:flutter/material.dart';

import '../core/l10n/generated/app_localizations.dart';
import '../core/theme/app_theme.dart';

/// What the person sees when startup cannot reach the real app. Built with its
/// own [MaterialApp] because no router or provider scope exists yet. Locale is
/// the documented default (vi): prefs may be the very thing that failed.
class StartupFailureApp extends StatelessWidget {
  const StartupFailureApp.failed({super.key}) : missingDefines = const [];
  const StartupFailureApp.missingConfig(this.missingDefines, {super.key});

  /// Empty means an unexpected startup error.
  final List<String> missingDefines;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      theme: buildAppTheme(),
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      locale: const Locale('vi'),
      home: Builder(
        builder: (context) {
          final l10n = AppLocalizations.of(context);
          final missing = missingDefines.isNotEmpty;
          return Scaffold(
            body: SafeArea(
              child: Center(
                child: Padding(
                  padding: const EdgeInsets.all(24),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        missing
                            ? l10n.startupMissingConfigTitle
                            : l10n.startupFailureTitle,
                        style: Theme.of(context).textTheme.headlineSmall,
                        textAlign: TextAlign.center,
                      ),
                      const SizedBox(height: 12),
                      Text(
                        missing
                            ? l10n.startupMissingConfigBody(
                                missingDefines.join(', '),
                              )
                            : l10n.startupFailureBody,
                        textAlign: TextAlign.center,
                      ),
                    ],
                  ),
                ),
              ),
            ),
          );
        },
      ),
    );
  }
}
