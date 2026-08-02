import 'dart:async';
import 'dart:convert';
import 'dart:io';

/// Global setup applied to every test under `test/`.
///
/// Several screens paint decorative images through [NetworkImage]. Widget
/// tests must never reach the network, and flutter_test already stops them —
/// but it answers every request with HTTP 400, which makes the image resolver
/// throw `NetworkImageLoadException` and fails any test whose tree contains
/// one. Answer with a 1x1 transparent PNG instead, so image widgets resolve
/// the way they do in the app and tests assert on the widgets they care about.
///
/// The override is installed *after* `testMain()` deliberately. Declaring a
/// `testWidgets` initialises TestWidgetsFlutterBinding, which installs the
/// 400-answering client as `HttpOverrides.global`; assigning afterwards is
/// what makes this one the client in effect once the tests actually run.
Future<void> testExecutable(FutureOr<void> Function() testMain) async {
  await testMain();
  HttpOverrides.global = _TransparentImageHttpOverrides();
}

/// A 1x1 fully transparent PNG — the smallest response the image codec accepts.
final List<int> _transparentPixelPng = base64Decode(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==',
);

class _TransparentImageHttpOverrides extends HttpOverrides {
  @override
  HttpClient createHttpClient(SecurityContext? context) => _FakeHttpClient();
}

/// The fakes below implement only the members [NetworkImage] actually touches.
/// Anything else throws rather than returning a silent null, so a test that
/// starts making real HTTP calls fails loudly instead of drifting.
class _FakeHttpClient implements HttpClient {
  @override
  bool autoUncompress = true;

  @override
  Future<HttpClientRequest> getUrl(Uri url) async => _FakeHttpClientRequest();

  @override
  void close({bool force = false}) {}

  @override
  dynamic noSuchMethod(Invocation invocation) => throw UnsupportedError(
    'tests must not use HttpClient.${invocation.memberName}',
  );
}

class _FakeHttpClientRequest implements HttpClientRequest {
  @override
  final HttpHeaders headers = _FakeHttpHeaders();

  @override
  Future<HttpClientResponse> close() async => _FakeHttpClientResponse();

  @override
  dynamic noSuchMethod(Invocation invocation) => throw UnsupportedError(
    'tests must not use HttpClientRequest.${invocation.memberName}',
  );
}

class _FakeHttpClientResponse implements HttpClientResponse {
  @override
  int get statusCode => HttpStatus.ok;

  @override
  int get contentLength => _transparentPixelPng.length;

  @override
  HttpClientResponseCompressionState get compressionState =>
      HttpClientResponseCompressionState.notCompressed;

  @override
  StreamSubscription<List<int>> listen(
    void Function(List<int> event)? onData, {
    Function? onError,
    void Function()? onDone,
    bool? cancelOnError,
  }) {
    return Stream<List<int>>.value(_transparentPixelPng).listen(
      onData,
      onError: onError,
      onDone: onDone,
      cancelOnError: cancelOnError,
    );
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => throw UnsupportedError(
    'tests must not use HttpClientResponse.${invocation.memberName}',
  );
}

/// Header writes are accepted and dropped — no request is ever sent.
class _FakeHttpHeaders implements HttpHeaders {
  @override
  void add(String name, Object value, {bool preserveHeaderCase = false}) {}

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}
