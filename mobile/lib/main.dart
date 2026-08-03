import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import 'app/app.dart';
import 'app/bootstrap.dart';
import 'app/router/app_router.dart';
import 'core/network/dio_provider.dart';
import 'core/network/token_refresher.dart';
import 'core/storage/cache_store.dart';
import 'core/storage/prefs_store.dart';
import 'features/auth/auth.dart';
import 'features/clan/clan.dart';

/// Supplied by `--dart-define`; never committed.
const _supabaseUrl = String.fromEnvironment('SUPABASE_URL');
const _supabaseKey = String.fromEnvironment('SUPABASE_PUBLISHABLE_KEY');
const _sentryDsn = String.fromEnvironment('SENTRY_DSN');

/// `10.0.2.2` is the Android emulator's alias for the host's localhost. On a
/// physical device pass the machine's LAN address:
/// `flutter run --dart-define=API_BASE_URL=http://192.168.1.x:8000/api/v1 …`
const _apiBaseUrl = String.fromEnvironment(
  'API_BASE_URL',
  defaultValue: 'http://10.0.2.2:8000/api/v1',
);

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final prefs = await PrefsStore.open();
  final cache = await SqfliteCacheStore.open();
  final authRouteState = AuthRouteState();

  await bootstrap(
    supabaseUrl: _supabaseUrl,
    supabasePublishableKey: _supabaseKey,
    sentryDsn: _sentryDsn,
    appBuilder: () => ProviderScope(
      overrides: [
        apiBaseUrlProvider.overrideWithValue(_apiBaseUrl),
        prefsStoreProvider.overrideWithValue(prefs),
        cacheStoreProvider.overrideWithValue(cache),
        authRouteStateProvider.overrideWithValue(authRouteState),

        // The Dio seams. Each reads live state at request time, which is why
        // they are closures rather than values.
        accessTokenProvider.overrideWithValue(
          () => Supabase.instance.client.auth.currentSession?.accessToken,
        ),
        currentClanIdProvider.overrideWithValue(prefs.readClanId),
        currentLocaleProvider.overrideWithValue(
          () => prefs.readLocale() ?? 'vi',
        ),
        tokenRefresherProvider.overrideWithValue(
          TokenRefresher(() async {
            final res = await Supabase.instance.client.auth.refreshSession();
            return res.session?.accessToken;
          }),
        ),
        // Needs the container, so it cannot be a plain value.
        onSignOutProvider.overrideWith(
          (ref) =>
              () => ref.read(sessionControllerProvider.notifier).signOut(),
        ),

        // Repositories are built from apiClientProvider, which is built from
        // dioProvider. Overriding the base URL above is enough to redirect the
        // whole stack.
        authRepositoryProvider.overrideWith(
          (ref) => AuthRepository(ref.watch(apiClientProvider)),
        ),
        clanRepositoryProvider.overrideWith(
          (ref) => ClanRepository(ref.watch(apiClientProvider)),
        ),
      ],
      child: const FamilyRootsApp(),
    ),
  );
}
