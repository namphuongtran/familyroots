import 'package:flutter/material.dart';

import '../../../core/l10n/generated/app_localizations.dart';
import '../../../core/theme/tokens.dart';
import '../../../domain/clan/clan_membership.dart';

/// Dumb view: data in, events out. No transport, no container — so it is
/// trivially widget- and golden-testable.
class MyClansView extends StatelessWidget {
  const MyClansView({
    super.key,
    required this.clans,
    required this.onSelect,
    this.staleAsOf,
  });

  final List<ClanMembership> clans;
  final void Function(ClanMembership) onSelect;

  /// Set when the payload came from the read cache instead of the network.
  final String? staleAsOf;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final t = context.tokens;

    return Scaffold(
      appBar: AppBar(title: Text(l10n.myClansTitle)),
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          if (staleAsOf != null)
            Container(
              // The no-line rule: a background shift, not a border.
              color: t.surfaceContainerLow,
              padding: EdgeInsets.all(t.spaceSm),
              child: Text(l10n.staleDataBanner(staleAsOf!)),
            ),
          Padding(
            padding: EdgeInsets.all(t.spaceMd),
            child: Text(l10n.clanCount(clans.length)),
          ),
          Expanded(
            child: ListView.builder(
              itemCount: clans.length,
              itemBuilder: (context, i) {
                final clan = clans[i];
                return Card(
                  margin: EdgeInsets.symmetric(
                    horizontal: t.spaceMd,
                    vertical: t.spaceXs,
                  ),
                  child: ListTile(
                    title: Text(clan.clanName),
                    subtitle: Text(clan.role.name),
                    onTap: () => onSelect(clan),
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}
