import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:sentry_flutter/sentry_flutter.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import '../core/storage/secure_session_store.dart';
import 'startup_screens.dart';

/// Names of the required `--dart-define` keys that are empty. An empty
/// `SENTRY_DSN` is allowed (a local run has none), so it is not checked.
List<String> missingDefines({
  required String supabaseUrl,
  required String supabasePublishableKey,
}) => [
  if (supabaseUrl.isEmpty) 'SUPABASE_URL',
  if (supabasePublishableKey.isEmpty) 'SUPABASE_PUBLISHABLE_KEY',
];

/// Runs [appRunner] inside `SentryFlutter.init`.
typedef SentryRunner =
    Future<void> Function(FutureOr<void> Function() appRunner);

Future<void> _runWithSentry(String dsn, FutureOr<void> Function() appRunner) {
  return SentryFlutter.init((SentryFlutterOptions options) {
    options.dsn = dsn;
    options.tracesSampleRate = 0.2;
    options.sendDefaultPii = false;
  }, appRunner: appRunner);
}

Future<void> _initSupabase(String url, String key) => Supabase.initialize(
  url: url,
  // `anonKey` is deprecated in supabase_flutter 2.16.0.
  publishableKey: key,
  authOptions: FlutterAuthClientOptions(
    // Tokens in the Keychain/Keystore, never SharedPreferences.
    localStorage: SecureSessionStore(),
    pkceAsyncStorage: SecurePkceStore(),
    authFlowType: AuthFlowType.pkce,
  ),
);

/// Sentry first; then, inside its `appRunner`, the config check, Supabase, and
/// [prepare] (which opens the prefs store and cache and returns the app
/// builder). A throw from any of those is reported and ends in a localised
/// failure screen, never a blank one. When a required define is empty,
/// `Supabase.initialize` is not called and a screen names what is missing.
///
/// The keyword parameters after [prepare] exist so a test can replace the
/// steps that need platform channels.
Future<void> bootstrap({
  required String supabaseUrl,
  required String supabasePublishableKey,
  required String sentryDsn,
  required Future<Widget Function()> Function() prepare,
  SentryRunner? runWithSentry,
  void Function(Object error, StackTrace stack)? reportError,
  Future<void> Function()? initSupabase,
  void Function(Widget app)? run,
}) async {
  WidgetsFlutterBinding.ensureInitialized();

  final runner =
      runWithSentry ?? (appRunner) => _runWithSentry(sentryDsn, appRunner);
  final report =
      reportError ??
      (Object e, StackTrace s) {
        unawaited(Sentry.captureException(e, stackTrace: s));
      };
  final init =
      initSupabase ?? () => _initSupabase(supabaseUrl, supabasePublishableKey);
  final show = run ?? runApp;

  await runner(() async {
    try {
      final missing = missingDefines(
        supabaseUrl: supabaseUrl,
        supabasePublishableKey: supabasePublishableKey,
      );
      if (missing.isNotEmpty) {
        show(StartupFailureApp.missingConfig(missing));
        return;
      }
      await init();
      final appBuilder = await prepare();
      show(appBuilder());
    } catch (e, s) {
      report(e, s);
      show(const StartupFailureApp.failed());
    }
  });
}
