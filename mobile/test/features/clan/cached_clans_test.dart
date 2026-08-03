import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

import 'package:family_roots_mobile/core/network/api_client.dart';
import 'package:family_roots_mobile/core/network/api_exception.dart';
import 'package:family_roots_mobile/core/storage/cache_store.dart';
import 'package:family_roots_mobile/features/clan/application/cached_clans.dart';
import 'package:family_roots_mobile/features/clan/data/clan_repository.dart';

import '../../support/sequence_adapter.dart';

ClanRepository _repo(List<Canned> canned) => ClanRepository(
  ApiClient(
    Dio(BaseOptions(baseUrl: 'https://api.test/api/v1'))
      ..httpClientAdapter = SequenceAdapter(canned),
  ),
);

/// A transport that always fails, to simulate being offline.
class _OfflineAdapter implements HttpClientAdapter {
  @override
  Future<ResponseBody> fetch(
    RequestOptions o,
    Stream<dynamic>? s,
    Future<void>? c,
  ) => throw DioException(
    requestOptions: o,
    type: DioExceptionType.connectionError,
  );

  @override
  void close({bool force = false}) {}
}

ClanRepository _offline() => ClanRepository(
  ApiClient(
    Dio(BaseOptions(baseUrl: 'https://api.test/api/v1'))
      ..httpClientAdapter = _OfflineAdapter(),
  ),
);

const _clansOk = Canned(200, <String, Object?>{
  'data': <Object?>[
    <String, Object?>{
      'clan_id': 'c1',
      'clan_name': 'Họ Nguyễn',
      'clan_slug': 'ho-nguyen',
      'role': 'admin',
      'joined_at': '2026-01-15T08:30:00Z',
    },
  ],
});

void main() {
  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  late SqfliteCacheStore cache;

  setUp(() async {
    // inMemoryDatabasePath is SHARED across opens in one test process.
    await databaseFactory.deleteDatabase(inMemoryDatabasePath);
    final db = await databaseFactory.openDatabase(
      inMemoryDatabasePath,
      options: OpenDatabaseOptions(
        version: 1,
        onCreate: (d, _) => d.execute(SqfliteCacheStore.createTableSql),
      ),
    );
    cache = SqfliteCacheStore(db);
  });

  test('a network read is fresh and populates the cache', () async {
    final r = await CachedClanReader(
      _repo(<Canned>[_clansOk]),
      cache,
    ).myClans();

    expect(r.isStale, isFalse);
    expect(r.asOf, isNull);
    expect(r.value.single.clanName, 'Họ Nguyễn');
    expect(await cache.get(CachedClanReader.cacheKey), isNotNull);
  });

  test('offline serves the cached payload flagged stale', () async {
    await CachedClanReader(_repo(<Canned>[_clansOk]), cache).myClans();

    final r = await CachedClanReader(_offline(), cache).myClans();
    expect(r.isStale, isTrue);
    expect(r.asOf, isNotNull);
    expect(r.value.single.clanName, 'Họ Nguyễn');
    expect(r.value.single.joinedAt, DateTime.utc(2026, 1, 15, 8, 30));
  });

  test('offline with an empty cache still fails', () async {
    await expectLater(
      CachedClanReader(_offline(), cache).myClans(),
      throwsA(isA<NetworkException>()),
    );
  });

  test(
    'an ApiException propagates — a 403 is an answer, not an outage',
    () async {
      await CachedClanReader(_repo(<Canned>[_clansOk]), cache).myClans();

      final forbidden = _repo(<Canned>[
        const Canned(403, <String, Object?>{
          'error': <String, Object?>{
            'code': 'account_deactivated',
            'message': 'Tài khoản đã bị khoá',
            'detail': <String, Object?>{},
          },
        }),
      ]);
      await expectLater(
        CachedClanReader(forbidden, cache).myClans(),
        throwsA(isA<ApiException>()),
      );
    },
  );
}
