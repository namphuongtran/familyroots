import 'package:flutter/material.dart';
import '../shared/l10n/app_localizations.dart';
import 'router/app_router.dart';
import 'theme/app_theme.dart';

/// Root widget for the FamilyRoots mobile app.
class FamilyRootsApp extends StatelessWidget {
  const FamilyRootsApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp.router(
      title: 'FamilyRoots',
      theme: AppTheme.light,
      darkTheme: AppTheme.dark,
      themeMode: ThemeMode.system,
      routerConfig: appRouter,
      debugShowCheckedModeBanner: false,
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: const [
        Locale('vi'),
        Locale('en'),
        Locale('zh'),
        Locale('fr'),
      ],
      // TODO: implement in Prompt 2 — persist user language preference
      // locale: ref.watch(localeProvider),
    );
  }
}
