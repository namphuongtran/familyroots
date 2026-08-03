/// Public surface of the auth slice. Other slices import this and nothing
/// deeper; the import-boundary test enforces it.
library;

export 'application/session_controller.dart'
    show SessionController, sessionControllerProvider, authRepositoryProvider;
export 'data/auth_repository.dart' show AuthRepository;
