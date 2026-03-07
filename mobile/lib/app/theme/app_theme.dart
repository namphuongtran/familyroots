import 'package:flutter/material.dart';
import 'colors.dart';
import 'typography.dart';

/// App theme configuration.
class AppTheme {
  AppTheme._();

  static ThemeData get light => ThemeData(
        useMaterial3: true,
        colorScheme: AppColors.lightScheme,
        textTheme: AppTypography.textTheme,
        // TODO: implement in Prompt 2 — custom component themes
      );

  static ThemeData get dark => ThemeData(
        useMaterial3: true,
        colorScheme: AppColors.darkScheme,
        textTheme: AppTypography.textTheme,
        // TODO: implement in Prompt 2 — custom component themes
      );
}
