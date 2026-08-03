import 'package:flutter/widgets.dart';
import 'package:sentry_flutter/sentry_flutter.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import '../core/storage/secure_session_store.dart';

/// Sentry, Supabase and the secure stores, in that order. Everything after
/// this point can assume they exist.
Future<void> bootstrap({
  required String supabaseUrl,
  required String supabasePublishableKey,
  required String sentryDsn,
  required Widget Function() appBuilder,
}) async {
  WidgetsFlutterBinding.ensureInitialized();

  await Supabase.initialize(
    url: supabaseUrl,
    // `anonKey` is deprecated in supabase_flutter 2.16.0.
    publishableKey: supabasePublishableKey,
    authOptions: FlutterAuthClientOptions(
      // Tokens in the Keychain/Keystore, never SharedPreferences.
      localStorage: SecureSessionStore(),
      pkceAsyncStorage: SecurePkceStore(),
      authFlowType: AuthFlowType.pkce,
    ),
  );

  await SentryFlutter.init((SentryFlutterOptions options) {
    options.dsn = sentryDsn;
    options.tracesSampleRate = 0.2;
    options.sendDefaultPii = false;
  }, appRunner: () => runApp(appBuilder()));
}
