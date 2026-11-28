import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:sentry_flutter/sentry_flutter.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import '../core/storage/secure_session_store.dart';
import 'startup_screens.dart';

/// Names of the required `--dart-define`s that are empty. `SENTRY_DSN` is not
/// required: a local run has none.
List<String> missingDefines({
  required String supabaseUrl,
  required String supabasePublishableKey,
}) => [
  if (supabaseUrl.isEmpty) 'SUPABASE_URL',
  if (supabasePublishableKey.isEmpty) 'SUPABASE_PUBLISHABLE_KEY',
];

/// Runs [appRunner] inside Sentry's guard.
typedef SentryRunner =
    Future<void> Function(FutureOr<void> Function() appRunner, String dsn);

typedef ErrorReporter = FutureOr<void> Function(Object error, StackTrace stack);
typedef SupabaseStarter =
    Future<void> Function(String url, String publishableKey);

Future<void> _runWithSentry(FutureOr<void> Function() appRunner, String dsn) =>
    SentryFlutter.init((SentryFlutterOptions options) {
      options.dsn = dsn;
      options.tracesSampleRate = 0.2;
      options.sendDefaultPii = false;
    }, appRunner: appRunner);

Future<void> _reportToSentry(Object error, StackTrace stack) async {
  await Sentry.captureException(error, stackTrace: stack);
}

Future<void> _initSupabase(String url, String publishableKey) =>
    Supabase.initialize(
      url: url,
      // `anonKey` is deprecated in supabase_flutter 2.16.0.
      publishableKey: publishableKey,
      authOptions: FlutterAuthClientOptions(
        // Tokens in the Keychain/Keystore, never SharedPreferences.
        localStorage: SecureSessionStore(),
        pkceAsyncStorage: SecurePkceStore(),
        authFlowType: AuthFlowType.pkce,
      ),
    );

/// Sentry first. Everything else runs inside its `appRunner`: the config
/// check, then Supabase, then [appBuilder] (which opens the prefs store and
/// the cache). A throw from any of them is reported and ends in a
/// startup-failure screen rather than a blank one. An empty required define
/// skips Supabase and shows a screen naming each missing define.
///
/// [runWithSentry], [initSupabase] and [reportError] are parameters so a test
/// can replace the steps that need platform channels.
Future<void> bootstrap({
  required String supabaseUrl,
  required String supabasePublishableKey,
  required String sentryDsn,
  required Future<Widget> Function() appBuilder,
  SentryRunner runWithSentry = _runWithSentry,
  SupabaseStarter initSupabase = _initSupabase,
  ErrorReporter reportError = _reportToSentry,
}) async {
  WidgetsFlutterBinding.ensureInitialized();

  await runWithSentry(() async {
    try {
      final missing = missingDefines(
        supabaseUrl: supabaseUrl,
        supabasePublishableKey: supabasePublishableKey,
      );
      if (missing.isNotEmpty) {
        runApp(MissingConfigApp(missing: missing));
        return;
      }
      await initSupabase(supabaseUrl, supabasePublishableKey);
      runApp(await appBuilder());
    } catch (error, stack) {
      try {
        await reportError(error, stack);
      } catch (_) {
        // Reporting must not stop the failure screen from appearing.
      }
      runApp(const StartupFailureApp());
    }
  }, sentryDsn);
}
