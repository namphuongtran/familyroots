import 'package:flutter/material.dart';

/// Platform-wide usage metrics page.
///
/// Only accessible to the platform super admin.
class PlatformMetricsPage extends StatelessWidget {
  const PlatformMetricsPage({super.key});

  @override
  Widget build(BuildContext context) {
    // TODO: implement in Prompt 2
    return Scaffold(
      appBar: AppBar(title: const Text('Platform Metrics')),
      body: const Center(child: Text('Platform Usage Statistics')),
    );
  }
}
