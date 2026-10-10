import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:family_roots_mobile/app/router/app_router.dart';
import 'package:family_roots_mobile/core/network/dio_provider.dart';
import 'package:family_roots_mobile/core/network/token_refresher.dart';
import 'package:family_roots_mobile/core/storage/cache_store.dart';
import 'package:family_roots_mobile/core/storage/prefs_store.dart';
import 'package:family_roots_mobile/features/auth/auth.dart';
import 'package:family_roots_mobile/features/clan/clan.dart';

import 'fake_gotrue.dart';
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
/// The Supabase auth client is real: a `GoTrueClient` whose HTTP transport is
/// [goTrue]'s fake. Sign-in, the access token every request carries, the
/// refresh and sign-out all go through the one [SupabaseAuth] built on it, as
/// `main.dart` builds its one on `Supabase.instance.client.auth`.
///
/// What this does NOT cover: `Supabase.initialize` and Sentry, which need
/// platform channels and real credentials, and the secure storage
/// `supabase_flutter` persists the session to. Those remain M0 Task 20's job.
///
/// Returns a container, not an override list: Riverpod 3 does not export the
/// `Override` type, so the list cannot be named in a signature.
Future<ProviderContainer> mainContainer({
  SequenceAdapter? adapter,
  FakeGoTrue? goTrue,
}) async {
  SharedPreferences.setMockInitialValues(<String, Object>{});
  final prefs = await PrefsStore.open();
  final auth = SupabaseAuth((goTrue ?? FakeGoTrue()).client);

  return ProviderContainer(
    overrides: [
      apiBaseUrlProvider.overrideWithValue('https://api.test/api/v1'),
      prefsStoreProvider.overrideWithValue(prefs),
      cacheStoreProvider.overrideWithValue(FakeCacheStore()),
      authRouteStateProvider.overrideWithValue(AuthRouteState()),

      // The Dio seams and sign-in, exactly as main.dart supplies them.
      accessTokenProvider.overrideWithValue(() => auth.accessToken),
      currentClanIdProvider.overrideWithValue(prefs.readClanId),
      currentLocaleProvider.overrideWithValue(() => prefs.readLocale() ?? 'vi'),
      tokenRefresherProvider.overrideWithValue(TokenRefresher(auth.refresh)),
      supabaseAuthProvider.overrideWithValue(auth),
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

      // Only when a test wants to control or count requests. The Dio is the
      // one main.dart gets, all five interceptors in place; only the transport
      // underneath is swapped. It used to be a bare Dio with no interceptors,
      // so no test that passed an adapter could see a missing bearer token.
      if (adapter != null)
        dioProvider.overrideWith(
          (ref) => buildDio(ref)..httpClientAdapter = adapter,
        ),
    ],
  );
}
