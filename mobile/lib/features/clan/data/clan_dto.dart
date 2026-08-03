import '../../../domain/clan/clan_membership.dart';
import '../../../domain/shared/ids.dart';

/// The only place that knows the backend's wire shape for clans.
ClanMembership clanMembershipFromJson(Object? json) {
  final m = json! as Map<String, Object?>;
  final joined = m['joined_at'];
  return ClanMembership(
    clanId: ClanId(m['clan_id']! as String),
    clanName: m['clan_name']! as String,
    clanSlug: m['clan_slug'] as String? ?? '',
    role: ClanRole.fromWire(m['role']),
    joinedAt: joined is String ? DateTime.tryParse(joined) : null,
  );
}
