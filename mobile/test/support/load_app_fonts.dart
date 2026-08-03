import 'dart:io';

// ByteData and Uint8List come from package:flutter/services.dart, which
// re-exports dart:typed_data — importing both trips unnecessary_import.
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

/// Widget tests render a weight-insensitive placeholder font unless the real
/// ones are registered. Call this in setUpAll for any golden or layout test.
Future<void> loadAppFonts() async {
  TestWidgetsFlutterBinding.ensureInitialized();
  const families = <String, String>{
    'PlusJakartaSans': 'assets/fonts/PlusJakartaSans.ttf',
    'Manrope': 'assets/fonts/Manrope.ttf',
  };
  for (final entry in families.entries) {
    final loader = FontLoader(entry.key)
      ..addFont(
        File(entry.value).readAsBytes().then(
          (b) => ByteData.view(Uint8List.fromList(b).buffer),
        ),
      );
    await loader.load();
  }
}
