import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../storage/cache_store.dart';
import 'api_client.dart';
import 'interceptors/auth_interceptor.dart';
import 'interceptors/clan_interceptor.dart';
import 'interceptors/locale_interceptor.dart';
import 'interceptors/refresh_interceptor.dart';
import 'interceptors/trace_interceptor.dart';
import 'token_refresher.dart';

/// Overridden at bootstrap with the real base URL.
final apiBaseUrlProvider = Provider<String>(
  (ref) => throw UnimplementedError('override in ProviderScope'),
);

/// Reads: current access token, current clan id, current locale, sign-out.
///
/// These are closures, not values, because each must read *live* state at
/// request time — the token rotates, the clan changes, the locale changes.
final accessTokenProvider = Provider<String? Function()>(
  (ref) => throw UnimplementedError('override in ProviderScope'),
);
final currentClanIdProvider = Provider<String? Function()>(
  (ref) => throw UnimplementedError('override in ProviderScope'),
);
final currentLocaleProvider = Provider<String Function()>(
  (ref) => throw UnimplementedError('override in ProviderScope'),
);
final tokenRefresherProvider = Provider<TokenRefresher>(
  (ref) => throw UnimplementedError('override in ProviderScope'),
);
final onSignOutProvider = Provider<void Function()>(
  (ref) => throw UnimplementedError('override in ProviderScope'),
);
final cacheStoreProvider = Provider<CacheStore>(
  (ref) => throw UnimplementedError('override in ProviderScope'),
);

/// The single Dio instance, with the five interceptors in the mandated order.
/// Refresh goes last so the header interceptors have already run on the retry.
final dioProvider = Provider<Dio>((ref) {
  final dio = Dio(
    BaseOptions(
      baseUrl: ref.watch(apiBaseUrlProvider),
      connectTimeout: const Duration(seconds: 15),
      receiveTimeout: const Duration(seconds: 30),
    ),
  );

  dio.interceptors.addAll(<Interceptor>[
    AuthInterceptor(ref.watch(accessTokenProvider)),
    ClanInterceptor(ref.watch(currentClanIdProvider)),
    LocaleInterceptor(ref.watch(currentLocaleProvider)),
    TraceInterceptor(),
    RefreshInterceptor(
      refresher: ref.watch(tokenRefresherProvider),
      retryDio: dio,
      onSignOut: ref.watch(onSignOutProvider),
    ),
  ]);

  return dio;
});

final apiClientProvider = Provider<ApiClient>(
  (ref) => ApiClient(ref.watch(dioProvider)),
);
