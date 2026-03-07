import 'package:flutter/material.dart';

/// Platform super admin dashboard — overview of all clans on the platform.
///
/// Only accessible to the platform super admin.
class PlatformDashboardPage extends StatelessWidget {
  const PlatformDashboardPage({super.key});

  @override
  Widget build(BuildContext context) {
    // TODO: implement in Prompt 2
    return Scaffold(
      appBar: AppBar(title: const Text('Platform Dashboard')),
      body: const Center(child: Text('Platform Dashboard — All Clans Overview')),
    );
  }
}
