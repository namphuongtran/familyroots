import 'package:flutter/material.dart';

import '../../../core/l10n/generated/app_localizations.dart';
import '../../../core/theme/tokens.dart';
import '../../../domain/clan/clan_membership.dart';

/// The picker must navigate EXPLICITLY after a selection: clearing a router
/// guard condition does not by itself pull the user forward (V13).
class ClanPickerView extends StatelessWidget {
  const ClanPickerView({
    super.key,
    required this.clans,
    required this.onSelect,
  });

  final List<ClanMembership> clans;
  final void Function(ClanMembership) onSelect;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final t = context.tokens;
    return Scaffold(
      appBar: AppBar(title: Text(l10n.clanPickerTitle)),
      body: ListView.builder(
        padding: EdgeInsets.all(t.spaceMd),
        itemCount: clans.length,
        itemBuilder: (context, i) => Card(
          margin: EdgeInsets.symmetric(vertical: t.spaceXs),
          child: ListTile(
            title: Text(clans[i].clanName),
            subtitle: Text(clans[i].role.name),
            onTap: () => onSelect(clans[i]),
          ),
        ),
      ),
    );
  }
}
