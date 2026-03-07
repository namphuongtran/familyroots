/// API endpoint path constants for the web app.
class ApiConstants {
  ApiConstants._();

  // TODO: implement in Prompt 2

  static const String baseUrl = '/api/v1';
  static const String auth = '$baseUrl/auth';
  static const String members = '$baseUrl/members';
  static const String relationships = '$baseUrl/relationships';
  static const String documents = '$baseUrl/documents';
  static const String events = '$baseUrl/events';
  static const String tree = '$baseUrl/tree';
  static const String clans = '$baseUrl/clans';
  static const String notifications = '$baseUrl/notifications';
  static const String admin = '$baseUrl/admin';
}
