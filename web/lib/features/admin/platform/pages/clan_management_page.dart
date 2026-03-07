import 'package:flutter/material.dart';

/// Clan management page — suspend/reactivate clan tenants.
///
/// Only accessible to the platform super admin.
class ClanManagementPage extends StatelessWidget {
  const ClanManagementPage({super.key});

  @override
  Widget build(BuildContext context) {
    // TODO: implement in Prompt 2
    return Scaffold(
      appBar: AppBar(title: const Text('Clan Management')),
      body: const Center(child: Text('Suspend / Reactivate Clans')),
    );
  }
}
