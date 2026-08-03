import 'package:freezed_annotation/freezed_annotation.dart';

import '../shared/ids.dart';

part 'clan_membership.freezed.dart';

enum ClanRole {
  admin,
  editor,
  viewer,
  unknown;

  /// Never throws: an unrecognised role degrades to [unknown] so a new server
  /// role cannot crash a shipped client. `invalid_role_assignment` is the
  /// backend's own guard for corrupted values.
  static ClanRole fromWire(Object? raw) {
    for (final r in ClanRole.values) {
      if (r.name == raw) return r;
    }
    return ClanRole.unknown;
  }

  bool get canEdit => this == admin || this == editor;
  bool get canAdminister => this == admin;
}

@freezed
abstract class ClanMembership with _$ClanMembership {
  const factory ClanMembership({
    required ClanId clanId,
    required String clanName,
    required String clanSlug,
    required ClanRole role,
    required DateTime? joinedAt,
  }) = _ClanMembership;

  const ClanMembership._();
}
