import 'dart:ui';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../../../../core/theme/app_colors.dart';
import '../../../../shared/l10n/app_localizations.dart';
import '../../../../shared/widgets/custom_text_field.dart';
import '../../../../shared/widgets/primary_button.dart';

class RegisterPage extends StatefulWidget {
  const RegisterPage({super.key});

  @override
  State<RegisterPage> createState() => _RegisterPageState();
}

class _RegisterPageState extends State<RegisterPage> {
  bool _obscurePassword = true;
  bool _obscureConfirmPassword = true;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);

    return Scaffold(
      backgroundColor: AppColors.background,
      body: Stack(
        children: [
          // Organic shape backgrounds
          Positioned(
            top: -100,
            left: -50,
            child: Container(
              width: 300,
              height: 300,
              decoration: const BoxDecoration(
                color: AppColors.primaryFixedDim,
                shape: BoxShape.circle,
              ),
            ),
          ),
          Positioned(
            bottom: -50,
            right: -100,
            child: Container(
              width: 250,
              height: 250,
              decoration: BoxDecoration(
                color: AppColors.secondaryContainer.withAlpha(150),
                shape: BoxShape.circle,
              ),
            ),
          ),

          // Blur wrapper for organic shapes
          Positioned.fill(
            child: BackdropFilter(
              filter: ImageFilter.blur(sigmaX: 80, sigmaY: 80),
              child: const SizedBox(),
            ),
          ),

          SafeArea(
            child: CustomScrollView(
              slivers: [
                SliverFillRemaining(
                  hasScrollBody: false,
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 40),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        const SizedBox(height: 16),
                        Row(
                          children: [
                            IconButton(
                              onPressed: () => context.pop(),
                              icon: const Icon(Icons.arrow_back),
                              color: AppColors.textPrimary,
                            ),
                            const Spacer(),
                          ],
                        ),
                        const SizedBox(height: 16),

                        Text(
                          l10n.registerTitle,
                          textAlign: TextAlign.center,
                          style: Theme.of(context).textTheme.displaySmall?.copyWith(
                            color: AppColors.primary,
                          ),
                        ),
                        const SizedBox(height: 8),
                        Text(
                          l10n.registerSubtitle,
                          textAlign: TextAlign.center,
                          style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                            color: AppColors.textSecondary,
                          ),
                        ),
                        const SizedBox(height: 48),

                        // Glassmorphic Form Card
                        ClipRRect(
                          borderRadius: BorderRadius.circular(32),
                          child: BackdropFilter(
                            filter: ImageFilter.blur(sigmaX: 20, sigmaY: 20),
                            child: Container(
                              padding: const EdgeInsets.all(24),
                              decoration: BoxDecoration(
                                color: AppColors.surface.withAlpha(204),
                                borderRadius: BorderRadius.circular(32),
                              ),
                              child: Column(
                                children: [
                                  CustomTextField(
                                    label: l10n.fullNameLabel,
                                    hint: l10n.fullNameHint,
                                    prefixIcon: Icons.person_outline,
                                  ),
                                  const SizedBox(height: 20),
                                  CustomTextField(
                                    label: l10n.emailLabel,
                                    hint: l10n.emailHint,
                                    prefixIcon: Icons.email_outlined,
                                    keyboardType: TextInputType.emailAddress,
                                  ),
                                  const SizedBox(height: 20),
                                  CustomTextField(
                                    label: l10n.passwordLabel,
                                    hint: l10n.passwordHint,
                                    prefixIcon: Icons.lock_outline,
                                    isPassword: true,
                                    obscureText: _obscurePassword,
                                    onToggleObscure: () {
                                      setState(() {
                                        _obscurePassword = !_obscurePassword;
                                      });
                                    },
                                  ),
                                  const SizedBox(height: 20),
                                  CustomTextField(
                                    label: l10n.confirmPasswordLabel,
                                    hint: l10n.confirmPasswordHint,
                                    prefixIcon: Icons.lock_outline,
                                    isPassword: true,
                                    obscureText: _obscureConfirmPassword,
                                    onToggleObscure: () {
                                      setState(() {
                                        _obscureConfirmPassword = !_obscureConfirmPassword;
                                      });
                                    },
                                  ),
                                  const SizedBox(height: 24),
                                ],
                              ),
                            ),
                          ),
                        ),

                        const SizedBox(height: 32),

                        PrimaryButton(
                          text: l10n.registerButton,
                          onPressed: () {
                            context.go('/');
                          },
                        ),

                        const Spacer(),
                        const SizedBox(height: 24),
                        Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Text(l10n.hasAccountPrompt, style: const TextStyle(color: AppColors.textSecondary)),
                            TextButton(
                              onPressed: () {
                                context.pop();
                              },
                              style: TextButton.styleFrom(
                                foregroundColor: AppColors.primary,
                              ),
                              child: Text(l10n.loginLink),
                            ),
                          ],
                        )
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
