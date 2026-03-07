import 'package:flutter/material.dart';
import 'colors.dart';
import 'typography.dart';

/// Web-optimized app theme — wider layouts, desktop-first.
class AppTheme {
  AppTheme._();

  static ThemeData get light => ThemeData(
        useMaterial3: true,
        colorScheme: AppColors.lightScheme,
        textTheme: AppTypography.textTheme,
        // TODO: implement in Prompt 2 — web-specific component themes
      );

  static ThemeData get dark => ThemeData(
        useMaterial3: true,
        colorScheme: AppColors.darkScheme,
        textTheme: AppTypography.textTheme,
        // TODO: implement in Prompt 2 — web-specific component themes
      );
}
