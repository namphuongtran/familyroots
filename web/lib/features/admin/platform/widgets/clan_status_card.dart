import 'package:flutter/material.dart';

/// Card widget displaying a clan's status (active/suspended) with actions.
///
/// Used in the platform admin clan management page.
class ClanStatusCard extends StatelessWidget {
  const ClanStatusCard({
    super.key,
    required this.clanId,
    required this.clanName,
    required this.isActive,
    this.onSuspend,
    this.onReactivate,
  });

  final String clanId;
  final String clanName;
  final bool isActive;
  final VoidCallback? onSuspend;
  final VoidCallback? onReactivate;

  @override
  Widget build(BuildContext context) {
    // TODO: implement in Prompt 2
    return Card(
      child: ListTile(
        title: Text(clanName),
        subtitle: Text(isActive ? 'Active' : 'Suspended'),
        trailing: isActive
            ? TextButton(onPressed: onSuspend, child: const Text('Suspend'))
            : TextButton(onPressed: onReactivate, child: const Text('Reactivate')),
      ),
    );
  }
}
