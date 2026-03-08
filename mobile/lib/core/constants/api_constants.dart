/// API endpoint constants.
class ApiConstants {
  ApiConstants._();

  // TODO: implement in Prompt 2 — load from env
  static const String baseUrl = 'http://localhost:8000/api/v1';

  static const String auth = '/auth';
  static const String persons = '/persons';
  static const String marriages = '/marriages';
  static const String parentChild = '/parent-child';
  static const String documents = '/documents';
  static const String events = '/events';
  static const String tree = '/tree';
  static const String clans = '/clans';
  static const String notifications = '/notifications';
}
