/// Public surface of the auth slice. Other slices import this and nothing
/// deeper; the import-boundary test enforces it.
library;

export 'application/session_controller.dart'
    show SessionController, sessionControllerProvider, authRepositoryProvider;
export 'data/auth_repository.dart' show AuthRepository;
export 'presentation/blocked_page.dart' show BlockedPage, BlockedReason;
export 'presentation/login_page.dart' show LoginPage;
export 'presentation/pending_approval_page.dart' show PendingApprovalPage;
export 'presentation/verify_email_page.dart' show VerifyEmailPage;
