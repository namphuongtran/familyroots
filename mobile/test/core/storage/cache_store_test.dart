import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

import 'package:family_roots_mobile/core/storage/cache_store.dart';

void main() {
  setUpAll(() {
    // sqflite has no implementation under `flutter test`; the FFI factory
    // provides a real SQLite without a device.
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  late SqfliteCacheStore store;

  setUp(() async {
    // `inMemoryDatabasePath` is SHARED across opens within one test process —
    // without this delete, data written by one test is visible to the next.
    await databaseFactory.deleteDatabase(inMemoryDatabasePath);
    final db = await databaseFactory.openDatabase(
      inMemoryDatabasePath,
      options: OpenDatabaseOptions(
        version: 1,
        onCreate: (d, _) => d.execute(SqfliteCacheStore.createTableSql),
      ),
    );
    store = SqfliteCacheStore(db);
  });

  test('round-trips a payload with a timestamp', () async {
    await store.put('GET /me/clans', <String, Object?>{
      'data': <Object?>[
        <String, Object?>{'clan_id': 'c1'},
      ],
    });

    final got = await store.get('GET /me/clans');
    expect(got, isNotNull);
    expect(got!.body, <String, Object?>{
      'data': <Object?>[
        <String, Object?>{'clan_id': 'c1'},
      ],
    });
    expect(DateTime.now().difference(got.storedAt).inSeconds, lessThan(5));
  });

  test('a miss is null, not an error', () async {
    expect(await store.get('never written'), isNull);
  });

  test('put replaces an existing key rather than duplicating it', () async {
    await store.put('k', <String, Object?>{'v': 1});
    await store.put('k', <String, Object?>{'v': 2});
    expect((await store.get('k'))!.body, <String, Object?>{'v': 2});
  });

  test('remove drops one key', () async {
    await store.put('a', 1);
    await store.put('b', 2);
    await store.remove('a');
    expect(await store.get('a'), isNull);
    expect((await store.get('b'))!.body, 2);
  });

  test('clear empties the cache — used on sign-out', () async {
    await store.put('a', 1);
    await store.put('b', 2);
    await store.clear();
    expect(await store.get('a'), isNull);
    expect(await store.get('b'), isNull);
  });

  test('stores lists as well as maps', () async {
    await store.put('list', <Object?>[1, 'two', null]);
    expect((await store.get('list'))!.body, <Object?>[1, 'two', null]);
  });
}
