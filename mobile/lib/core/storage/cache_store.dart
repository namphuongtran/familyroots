import 'dart:convert';

import 'package:sqflite/sqflite.dart';

class CachedPayload {
  const CachedPayload(this.body, this.storedAt);

  /// The decoded payload — already unwrapped from the envelope.
  final Object? body;
  final DateTime storedAt;
}

/// Read cache only (ADR-034 consequence 7): every successful network read is
/// written here so it can be re-served when the network fails. Writes always
/// require connectivity — there is no write queue and no offline conflict
/// resolution.
///
/// Presigned URLs are excluded by rule: they expire after 3600s and must never
/// be persisted (frontend-integration-guide.md §8).
abstract class CacheStore {
  Future<void> put(String key, Object? body);
  Future<CachedPayload?> get(String key);
  Future<void> remove(String key);
  Future<void> clear();
}

class SqfliteCacheStore implements CacheStore {
  SqfliteCacheStore(this._db);

  static const table = 'response_cache';

  static const createTableSql =
      '''
CREATE TABLE IF NOT EXISTS $table (
  key TEXT PRIMARY KEY,
  body TEXT NOT NULL,
  stored_at INTEGER NOT NULL
)''';

  final Database _db;

  static Future<SqfliteCacheStore> open() async {
    final path = '${await getDatabasesPath()}/familyroots_cache.db';
    final db = await openDatabase(
      path,
      version: 1,
      onCreate: (d, _) => d.execute(createTableSql),
    );
    return SqfliteCacheStore(db);
  }

  @override
  Future<void> put(String key, Object? body) async {
    await _db.insert(table, <String, Object?>{
      'key': key,
      'body': jsonEncode(body),
      'stored_at': DateTime.now().millisecondsSinceEpoch,
    }, conflictAlgorithm: ConflictAlgorithm.replace);
  }

  @override
  Future<CachedPayload?> get(String key) async {
    final rows = await _db.query(
      table,
      where: 'key = ?',
      whereArgs: <Object?>[key],
      limit: 1,
    );
    if (rows.isEmpty) return null;
    final row = rows.first;
    return CachedPayload(
      jsonDecode(row['body']! as String),
      DateTime.fromMillisecondsSinceEpoch(row['stored_at']! as int),
    );
  }

  @override
  Future<void> remove(String key) =>
      _db.delete(table, where: 'key = ?', whereArgs: <Object?>[key]);

  @override
  Future<void> clear() => _db.delete(table);
}
