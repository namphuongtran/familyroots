import 'package:flutter/material.dart';

/// Cross-tenant audit log page.
///
/// Only accessible to the platform super admin.
class PlatformAuditPage extends StatelessWidget {
  const PlatformAuditPage({super.key});

  @override
  Widget build(BuildContext context) {
    // TODO: implement in Prompt 2
    return Scaffold(
      appBar: AppBar(title: const Text('Audit Log')),
      body: const Center(child: Text('Cross-Tenant Audit Log')),
    );
  }
}
