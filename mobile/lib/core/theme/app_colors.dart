import 'package:flutter/material.dart';

class AppColors {
  // Primary (Botanical Green)
  static const Color primary = Color(0xFF37563B);
  static const Color primaryContainer = Color(0xFF4F6F52);
  static const Color onPrimary = Color(0xFFFFFFFF);
  static const Color onPrimaryContainer = Color(0xFFCCF0CC);
  static const Color primaryFixed = Color(0xFFC8ECC8);
  static const Color primaryFixedDim = Color(0xFFACD0AD);
  static const Color onPrimaryFixed = Color(0xFF03210B);
  static const Color onPrimaryFixedVariant = Color(0xFF2F4E33);

  // Secondary (Muted Rose)
  static const Color secondary = Color(0xFF6E5959);
  static const Color secondaryContainer = Color(0xFFF8DCDC);
  static const Color onSecondaryContainer = Color(0xFF745F5F);
  static const Color secondaryFixed = Color(0xFFF8DCDC);
  static const Color secondaryFixedDim = Color(0xFFDBC0C0);
  static const Color onSecondaryFixed = Color(0xFF261818);
  static const Color onSecondaryFixedVariant = Color(0xFF554242);

  // Tertiary
  static const Color tertiary = Color(0xFF62494A);

  // Surfaces (The Layering Principle)
  static const Color background = Color(0xFFFFF9EF); // Base surface
  static const Color surface = Color(0xFFFFF9EF); // Base
  static const Color surfaceContainerLow = Color(0xFFF9F3EA); // Secondary Content
  static const Color surfaceContainer = Color(0xFFF3EDE4); // Interactive Cards
  static const Color surfaceContainerHigh = Color(0xFFEDE7DE); // Footers
  static const Color surfaceContainerHighest = Color(0xFFE7E2D9); // Elevated Details
  static const Color surfaceContainerLowest = Color(0xFFFFFFFF); // Clean inputs

  // Typography
  static const Color onSurface = Color(0xFF1D1B16); // Replaces pure black
  static const Color onSurfaceVariant = Color(0xFF424841); // Recessional text
  static const Color textPrimary = onSurface;
  static const Color textSecondary = onSurfaceVariant;

  // Borders and Outline
  static const Color outlineVariant = Color(0xFFC2C8BF);
  static const Color border = outlineVariant; // "Ghost border" base color

  // Status
  static const Color success = Color(0xFF2E7D32);
  static const Color error = Color(0xFFBA1A1A); // from design system error
}

