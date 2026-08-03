import '../../../core/network/api_exception.dart';
import '../../../core/storage/cache_store.dart';
import '../../../domain/clan/clan_membership.dart';
import '../data/clan_dto.dart';
import '../data/clan_repository.dart';

class Stale<T> {
  const Stale(this.value, this.asOf);

  final T value;

  /// Null when the value came from the network.
  final DateTime? asOf;

  bool get isStale => asOf != null;
}

/// Every successful read is cached; when the network fails the cached payload
/// is served with an isStale flag so the UI can show the "dữ liệu ngày …"
/// banner. Writes always require the network — there is no write queue.
class CachedClanReader {
  CachedClanReader(this._repo, this._cache);

  static const cacheKey = 'GET /me/clans';

  final ClanRepository _repo;
  final CacheStore _cache;

  Future<Stale<List<ClanMembership>>> myClans() async {
    try {
      final clans = await _repo.myClans();
      await _cache.put(
        cacheKey,
        clans
            .map(
              (c) => <String, Object?>{
                'clan_id': c.clanId.value,
                'clan_name': c.clanName,
                'clan_slug': c.clanSlug,
                'role': c.role.name,
                'joined_at': c.joinedAt?.toIso8601String(),
              },
            )
            .toList(),
      );
      return Stale<List<ClanMembership>>(clans, null);
    } on NetworkException {
      return _fromCache();
    } on TimeoutException {
      return _fromCache();
    }
    // An ApiException deliberately propagates: a 403 is an answer, not an
    // outage, and must never be papered over with a stale list.
  }

  Future<Stale<List<ClanMembership>>> _fromCache() async {
    final hit = await _cache.get(cacheKey);
    if (hit == null) throw const NetworkException('no cached clans');
    final rows = (hit.body! as List<Object?>).map(clanMembershipFromJson);
    return Stale<List<ClanMembership>>(rows.toList(), hit.storedAt);
  }
}
