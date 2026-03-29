import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../../../../core/theme/app_colors.dart';
import '../../../../shared/widgets/custom_text_field.dart';
import '../../../../shared/widgets/primary_button.dart';
import '../../../../shared/widgets/social_login_button.dart';

class LoginPage extends StatefulWidget {
  const LoginPage({super.key});

  @override
  State<LoginPage> createState() => _LoginPageState();
}

class _LoginPageState extends State<LoginPage> {
  bool _obscurePassword = true;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 40),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              // Placeholder for Logo
              const SizedBox(height: 40),
              Center(
                child: Container(
                  width: 100,
                  height: 100,
                  decoration: BoxDecoration(
                    color: AppColors.primary.withAlpha(26), // 0.1 * 255
                    shape: BoxShape.circle,
                  ),
                  child: const Icon(
                    Icons.account_tree,
                    size: 60,
                    color: AppColors.primary,
                  ),
                ),
              ),
              const SizedBox(height: 24),
              const Text(
                'Gia Phả Di Sản',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: 28,
                  fontWeight: FontWeight.bold,
                  color: AppColors.primary,
                ),
              ),
              const SizedBox(height: 8),
              const Text(
                'Lưu giữ cội nguồn - Kết nối tương lai',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: 16,
                  color: AppColors.textSecondary,
                ),
              ),
              const SizedBox(height: 48),

              // Login Form
              const CustomTextField(
                label: 'Email',
                hint: 'Nhập email của bạn',
                prefixIcon: Icons.email_outlined,
                keyboardType: TextInputType.emailAddress,
              ),
              const SizedBox(height: 20),
              CustomTextField(
                label: 'Mật khẩu',
                hint: 'Nhập mật khẩu',
                prefixIcon: Icons.lock_outline,
                isPassword: true,
                obscureText: _obscurePassword,
                onToggleObscure: () {
                  setState(() {
                    _obscurePassword = !_obscurePassword;
                  });
                },
              ),
              const SizedBox(height: 12),
              Align(
                alignment: Alignment.centerRight,
                child: TextButton(
                  onPressed: () {},
                  child: const Text('Quên mật khẩu?'),
                ),
              ),
              const SizedBox(height: 24),

              PrimaryButton(
                text: 'Đăng Nhập',
                onPressed: () {
                  context.go('/');
                },
              ),
              const SizedBox(height: 32),

              Row(
                children: [
                  const Expanded(child: Divider()),
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 16),
                    child: Text(
                      'Hoặc',
                      style: TextStyle(color: Colors.grey[600]),
                    ),
                  ),
                  const Expanded(child: Divider()),
                ],
              ),
              const SizedBox(height: 32),

              SocialLoginButton(
                provider: SocialProvider.google,
                onPressed: () {},
              ),
              const SizedBox(height: 16),
              SocialLoginButton(
                provider: SocialProvider.apple,
                onPressed: () {},
              ),
              
              const SizedBox(height: 48),
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  const Text('Chưa có tài khoản? ', style: TextStyle(color: AppColors.textSecondary)),
                  TextButton(
                    onPressed: () {},
                    child: const Text('Đăng ký ngay'),
                  ),
                ],
              )
            ],
          ),
        ),
      ),
    );
  }
}
