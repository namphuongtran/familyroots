import 'package:flutter/material.dart';
import 'app/app.dart';

// TODO: implement in Prompt 2 — initialize Firebase, Sentry, Hive, DI

void main() {
  WidgetsFlutterBinding.ensureInitialized();

  // TODO: implement in Prompt 2
  // await Firebase.initializeApp();
  // await SentryFlutter.init(...);
  // await Hive.initFlutter();
  // configureDependencies();

  runApp(const FamilyRootsApp());
}
