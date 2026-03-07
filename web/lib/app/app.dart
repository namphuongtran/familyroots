import 'package:flutter/material.dart';
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
    );
  }
}
