import '../../../core/network/api_client.dart';
import '../../../domain/clan/clan_membership.dart';
import 'clan_dto.dart';

class ClanRepository {
  ClanRepository(this._api);
  final ApiClient _api;

  /// GET /me/clans — approved memberships only, a plain canonical array with
  /// no `meta`. Pending memberships are never listed, so this is empty for a
  /// purely-pending user.
  Future<List<ClanMembership>> myClans() async {
    final page = await _api.getPage<ClanMembership>(
      '/me/clans',
      parse: clanMembershipFromJson,
    );
    return page.items;
  }

  /// POST /me/clans/{id}/select — optional validation, 403
  /// clan_membership_required if not approved. The selection is NOT stored
  /// server-side; the client persists it and sends the header.
  Future<ClanMembership> select(String clanId) => _api.post<ClanMembership>(
    '/me/clans/$clanId/select',
    parse: clanMembershipFromJson,
  );
}
