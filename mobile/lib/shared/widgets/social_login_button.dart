import 'package:flutter/material.dart';
import '../../core/theme/app_colors.dart';

enum SocialProvider { google, apple }

class SocialLoginButton extends StatelessWidget {
  final SocialProvider provider;
  final VoidCallback onPressed;

  const SocialLoginButton({
    super.key,
    required this.provider,
    required this.onPressed,
  });

  @override
  Widget build(BuildContext context) {
    final bool isGoogle = provider == SocialProvider.google;
    final String text = isGoogle ? 'Continue with Google' : 'Continue with Apple';
    final Color bgColor = isGoogle ? AppColors.surfaceContainerLowest : AppColors.onSurface;
    final Color fgColor = isGoogle ? AppColors.onSurface : AppColors.onPrimary;
    final IconData icon = isGoogle ? Icons.g_mobiledata : Icons.apple; // Fallback to material icons

    return ElevatedButton(
      style: ElevatedButton.styleFrom(
        backgroundColor: bgColor,
        foregroundColor: fgColor,
        elevation: 0, // No shadow by default
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(24), // 'md' roundedness
        ),
        side: isGoogle ? const BorderSide(color: AppColors.outlineVariant) : BorderSide.none,
      ),
      onPressed: onPressed,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(icon, size: 28),
          const SizedBox(width: 12),
          Flexible(
            child: Text(
              text,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
            ),
          ),
        ],
      ),
    );
  }
}
