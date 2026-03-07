import 'package:flutter/material.dart';
import 'package:flutter_gen/gen_l10n/app_localizations.dart';
import 'router/web_router.dart';
import 'theme/app_theme.dart';

/// Root widget for the FamilyRoots web app.
class FamilyRootsWebApp extends StatelessWidget {
  const FamilyRootsWebApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp.router(
      title: 'FamilyRoots',
      theme: AppTheme.light,
      darkTheme: AppTheme.dark,
      themeMode: ThemeMode.system,
      routerConfig: webRouter,
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
