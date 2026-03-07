import 'package:flutter/material.dart';
import 'app/app.dart';

// TODO: implement in Prompt 2 — initialize Firebase, Sentry, DI

void main() {
  WidgetsFlutterBinding.ensureInitialized();

  // TODO: implement in Prompt 2
  // await Firebase.initializeApp();
  // await SentryFlutter.init(...);
  // configureDependencies();

  runApp(const FamilyRootsWebApp());
}
