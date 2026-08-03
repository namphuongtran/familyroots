import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/l10n/generated/app_localizations.dart';
import '../../../core/theme/tokens.dart';
import '../../../shared/widgets/error_view.dart';
import '../application/session_controller.dart';

class LoginPage extends ConsumerStatefulWidget {
  const LoginPage({super.key});

  @override
  ConsumerState<LoginPage> createState() => _LoginPageState();
}

class _LoginPageState extends ConsumerState<LoginPage> {
  final _email = TextEditingController();
  final _password = TextEditingController();

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final t = context.tokens;
    final state = ref.watch(sessionControllerProvider);

    return Scaffold(
      body: SafeArea(
        child: SingleChildScrollView(
          padding: EdgeInsets.all(t.spaceLg),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              Text(
                l10n.loginTitle,
                style: Theme.of(context).textTheme.headlineMedium,
              ),
              SizedBox(height: t.spaceLg),
              TextField(
                controller: _email,
                keyboardType: TextInputType.emailAddress,
                autofillHints: const <String>[AutofillHints.email],
                decoration: InputDecoration(labelText: l10n.emailLabel),
              ),
              SizedBox(height: t.spaceMd),
              TextField(
                controller: _password,
                obscureText: true,
                autofillHints: const <String>[AutofillHints.password],
                decoration: InputDecoration(labelText: l10n.passwordLabel),
              ),
              SizedBox(height: t.spaceLg),
              if (state.hasError) ...<Widget>[
                ErrorView(error: state.error!),
                SizedBox(height: t.spaceMd),
              ],
              FilledButton(
                onPressed: state.isLoading
                    ? null
                    : () => ref
                          .read(sessionControllerProvider.notifier)
                          .signIn(
                            email: _email.text.trim(),
                            password: _password.text,
                          ),
                child: state.isLoading
                    ? const SizedBox.square(
                        dimension: 20,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : Text(l10n.loginButton),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
