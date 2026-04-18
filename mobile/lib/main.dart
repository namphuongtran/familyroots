import 'package:flutter/material.dart';
import 'app/app.dart';
import 'core/di/injection.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();

  // TODO: initialize Firebase, Sentry, Hive when ready
  // await Firebase.initializeApp();
  // await SentryFlutter.init(...)  ;
  // await Hive.initFlutter();

  configureDependencies();

  runApp(const FamilyRootsApp());
}
