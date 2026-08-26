import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:family_roots_mobile/app/router/app_router.dart';
import 'package:family_roots_mobile/core/network/dio_provider.dart';
import 'package:family_roots_mobile/core/network/token_refresher.dart';
import 'package:family_roots_mobile/core/storage/cache_store.dart';
import 'package:family_roots_mobile/core/storage/prefs_store.dart';
import 'package:family_roots_mobile/features/auth/auth.dart';
import 'package:family_roots_mobile/features/clan/clan.dart';

import 'sequence_adapter.dart';

/// The cache is an in-memory fake rather than `SqfliteCacheStore`, and that is
/// load-bearing: `testWidgets` runs its body inside a **fake-async zone**, and
/// sqflite's FFI I/O never completes there — opening a real database inside a
/// widget test hangs forever rather than failing. Plain `test()` bodies are
/// unaffected, which is why the sqflite suites work.
class FakeCacheStore implements CacheStore {
  final Map<String, CachedPayload> _entries = <String, CachedPayload>{};

  @override
  Future<void> clear() async => _entries.clear();

  @override
  Future<CachedPayload?> get(String key) async => _entries[key];

  @override
  Future<void> put(String key, Object? body) async =>
      _entries[key] = CachedPayload(body, DateTime(2026, 8, 3));

  @override
  Future<void> remove(String key) async => _entries.remove(key);
}

/// Exactly the override set `main.dart` supplies, so a missing override fails
/// in a test instead of on a device.
///
/// What this does NOT cover: Supabase and Sentry initialisation, which need
/// platform channels and real credentials. Those remain M0 Task 20's job.
///
/// Returns a container, not an override list: Riverpod 3 does not export the
/// `Override` type, so the list cannot be named in a signature.
Future<ProviderContainer> mainContainer({SequenceAdapter? adapter}) async {
  SharedPreferences.setMockInitialValues(<String, Object>{});
  final prefs = await PrefsStore.open();

  return ProviderContainer(
    overrides: [
      apiBaseUrlProvider.overrideWithValue('https://api.test/api/v1'),
      prefsStoreProvider.overrideWithValue(prefs),
      cacheStoreProvider.overrideWithValue(FakeCacheStore()),
      authRouteStateProvider.overrideWithValue(AuthRouteState()),

      // Closures, exactly as main.dart supplies them. They are never invoked
      // during graph construction, so no Supabase instance is required.
      accessTokenProvider.overrideWithValue(() => null),
      currentClanIdProvider.overrideWithValue(prefs.readClanId),
      currentLocaleProvider.overrideWithValue(() => prefs.readLocale() ?? 'vi'),
      tokenRefresherProvider.overrideWithValue(
        TokenRefresher(() async => null),
      ),
      onSignOutProvider.overrideWith(
        (ref) =>
            () => ref.read(sessionControllerProvider.notifier).signOut(),
      ),

      authRepositoryProvider.overrideWith(
        (ref) => AuthRepository(ref.watch(apiClientProvider)),
      ),
      clanRepositoryProvider.overrideWith(
        (ref) => ClanRepository(ref.watch(apiClientProvider)),
      ),

      // Only when a test wants to control or count requests. Everything above
      // stays as main.dart has it; this swaps the transport underneath.
      if (adapter != null)
        dioProvider.overrideWith(
          (ref) =>
              Dio(BaseOptions(baseUrl: ref.watch(apiBaseUrlProvider)))
                ..httpClientAdapter = adapter,
        ),
    ],
  );
}
