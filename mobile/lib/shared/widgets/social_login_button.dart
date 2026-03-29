import 'package:flutter/material.dart';

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
    final Color bgColor = isGoogle ? Colors.white : Colors.black;
    final Color fgColor = isGoogle ? Colors.black87 : Colors.white;
    final IconData icon = isGoogle ? Icons.g_mobiledata : Icons.apple; // Fallback to material icons

    return ElevatedButton(
      style: ElevatedButton.styleFrom(
        backgroundColor: bgColor,
        foregroundColor: fgColor,
        elevation: 1,
        side: isGoogle ? const BorderSide(color: Color(0xFFD6D6D6)) : BorderSide.none,
      ),
      onPressed: onPressed,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(icon, size: 28),
          const SizedBox(width: 12),
          Text(text, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
        ],
      ),
    );
  }
}
