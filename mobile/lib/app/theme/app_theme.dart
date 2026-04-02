import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../../core/theme/app_colors.dart';

class AppTheme {
  AppTheme._();

  static ThemeData get light {
    final baseTextTheme = GoogleFonts.manropeTextTheme();
    final displayFont = GoogleFonts.plusJakartaSansTextTheme();

    return ThemeData(
      colorScheme: const ColorScheme.light(
        primary: AppColors.primary,
        primaryContainer: AppColors.primaryContainer,
        secondary: AppColors.secondary,
        secondaryContainer: AppColors.secondaryContainer,
        surface: AppColors.surface,
        error: AppColors.error,
        onPrimary: AppColors.onPrimary,
        onSecondary: Colors.white,
        onSurface: AppColors.onSurface,
        onSurfaceVariant: AppColors.onSurfaceVariant,
      ),
      scaffoldBackgroundColor: AppColors.background,
      fontFamily: GoogleFonts.manrope().fontFamily,
      useMaterial3: true,
      textTheme: baseTextTheme.copyWith(
        displayLarge: displayFont.displayLarge?.copyWith(color: AppColors.textPrimary, fontWeight: FontWeight.bold),
        displayMedium: displayFont.displayMedium?.copyWith(color: AppColors.textPrimary, fontWeight: FontWeight.bold),
        displaySmall: displayFont.displaySmall?.copyWith(color: AppColors.textPrimary, fontWeight: FontWeight.bold),
        headlineLarge: displayFont.headlineLarge?.copyWith(color: AppColors.textPrimary, fontWeight: FontWeight.bold),
        headlineMedium: displayFont.headlineMedium?.copyWith(color: AppColors.textPrimary, fontWeight: FontWeight.bold),
        headlineSmall: displayFont.headlineSmall?.copyWith(color: AppColors.textPrimary, fontWeight: FontWeight.w600),
        titleLarge: displayFont.titleLarge?.copyWith(color: AppColors.textPrimary, fontWeight: FontWeight.w600),
        titleMedium: displayFont.titleMedium?.copyWith(color: AppColors.textPrimary, fontWeight: FontWeight.w600),
        
        bodyLarge: baseTextTheme.bodyLarge?.copyWith(color: AppColors.textPrimary),
        bodyMedium: baseTextTheme.bodyMedium?.copyWith(color: AppColors.textPrimary),
        labelLarge: baseTextTheme.labelLarge?.copyWith(color: AppColors.primary, fontWeight: FontWeight.w600),
      ),
      appBarTheme: AppBarTheme(
        backgroundColor: AppColors.background,
        foregroundColor: AppColors.textPrimary,
        centerTitle: true,
        elevation: 0,
        titleTextStyle: displayFont.titleLarge?.copyWith(
          color: AppColors.textPrimary,
          fontSize: 20,
          fontWeight: FontWeight.w600,
        ) ?? const TextStyle(color: AppColors.textPrimary, fontSize: 20, fontWeight: FontWeight.w600),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: AppColors.primary,
          foregroundColor: AppColors.onPrimary,
          elevation: 0,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(9999), // "full" roundedness
          ),
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
          textStyle: GoogleFonts.manrope(
            fontSize: 16,
            fontWeight: FontWeight.w600,
          ),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: AppColors.primary,
          side: BorderSide(color: AppColors.outlineVariant.withAlpha(38)), // 15% opacity ghost border
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(9999),
          ),
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
          textStyle: GoogleFonts.manrope(
            fontSize: 16,
            fontWeight: FontWeight.w600,
          ),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: AppColors.surfaceContainerLowest, 
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: BorderSide.none, 
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: BorderSide.none,
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: BorderSide(color: AppColors.primary.withAlpha(76), width: 2), 
        ),
        errorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: const BorderSide(color: AppColors.error),
        ),
        labelStyle: const TextStyle(color: AppColors.textSecondary),
        hintStyle: const TextStyle(color: AppColors.textSecondary),
      ),
      cardTheme: const CardThemeData(
        color: AppColors.surfaceContainer,
        elevation: 0,
        margin: EdgeInsets.zero,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.all(Radius.circular(32)), // 'lg' corner
          side: BorderSide.none, 
        ),
      ),
    );
  }

  static ThemeData get dark {
    // Basic dark mode stub for now. 
    return light.copyWith(
      brightness: Brightness.dark,
      scaffoldBackgroundColor: const Color(0xFF1D1B16),
      colorScheme: const ColorScheme.dark(
        primary: AppColors.primaryFixedDim,
        secondary: AppColors.secondaryContainer,
        surface: Color(0xFF32302A),
      ),
    );
  }
}
