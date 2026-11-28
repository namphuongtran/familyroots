import '../../../core/l10n/generated/app_localizations.dart';
import '../../../domain/clan/clan_membership.dart';

/// The one place a [ClanRole] becomes user-facing text. Kept out of `domain/`
/// so the enum stays free of l10n.
String clanRoleLabel(AppLocalizations l10n, ClanRole role) => switch (role) {
  ClanRole.admin => l10n.clanRoleAdmin,
  ClanRole.editor => l10n.clanRoleEditor,
  ClanRole.viewer => l10n.clanRoleViewer,
  ClanRole.unknown => l10n.clanRoleUnknown,
};
