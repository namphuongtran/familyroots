import 'package:flutter_test/flutter_test.dart';
import 'package:family_roots_mobile/core/network/api_exception.dart';

void main() {
  group('policyActionFor covers the contract', () {
    test('401 family refreshes', () {
      expect(policyActionFor('missing_token'), PolicyAction.refreshThenRetry);
      expect(policyActionFor('invalid_token'), PolicyAction.refreshThenRetry);
      expect(policyActionFor('unauthorized'), PolicyAction.refreshThenRetry);
    });

    test('a dead refresh token signs out instead of refreshing again', () {
      expect(
        policyActionFor('auth.invalid_refresh_token'),
        PolicyAction.signOut,
      );
    });

    test('403 codes route, they never refresh or sign out', () {
      expect(
        policyActionFor('email_not_verified'),
        PolicyAction.resendVerification,
      );
      expect(
        policyActionFor('account_deactivated'),
        PolicyAction.blockedAccount,
      );
      expect(policyActionFor('clan_suspended'), PolicyAction.clanBlocked);
      expect(
        policyActionFor('no_approved_clan_membership'),
        PolicyAction.pendingOrOnboarding,
      );
      expect(
        policyActionFor('clan_membership_required'),
        PolicyAction.pendingOrOnboarding,
      );
    });

    test('clan-context codes', () {
      expect(
        policyActionFor('multiple_clans_no_selection'),
        PolicyAction.clanPicker,
      );
      expect(
        policyActionFor('invalid_clan_id_format'),
        PolicyAction.clearClanAndReResolve,
      );
    });

    test('stale_write reloads and reapplies, never blind-retries', () {
      expect(policyActionFor('stale_write'), PolicyAction.reloadAndReapply);
    });

    test('clan_founder_not_found is an onboarding state, not a 404', () {
      expect(
        policyActionFor('clan_founder_not_found'),
        PolicyAction.founderOnboarding,
      );
    });

    test('transient outages are not credential errors', () {
      expect(
        policyActionFor('auth_provider_unavailable'),
        PolicyAction.transientOutage,
      );
      expect(
        policyActionFor('storage_unavailable'),
        PolicyAction.transientOutage,
      );
      expect(
        policyActionFor('database_unavailable'),
        PolicyAction.transientOutage,
      );
    });

    test('rate limiting backs off', () {
      expect(policyActionFor('rate_limited'), PolicyAction.backOff);
    });

    test('a bad cursor drops the cursor and refetches page one', () {
      expect(policyActionFor('invalid_cursor'), PolicyAction.dropCursorRefetch);
    });

    test('an unknown code with a 401 status still refreshes', () {
      expect(
        policyActionFor('something_new', status: 401),
        PolicyAction.refreshThenRetry,
      );
    });

    test('an unknown code with a normal status does nothing special', () {
      expect(policyActionFor('person_not_found'), PolicyAction.none);
      expect(
        policyActionFor('person_not_found', status: 404),
        PolicyAction.none,
      );
    });
  });

  group('ApiException detail accessors', () {
    test('exposes current_version for stale_write', () {
      const e = ApiException(
        code: 'stale_write',
        message: 'người khác vừa sửa',
        status: 409,
        detail: <String, Object?>{'current_version': 7},
      );
      expect(e.currentVersion, 7);
      expect(e.retryAfter, isNull);
    });

    test('exposes retry_after for rate_limited', () {
      const e = ApiException(
        code: 'rate_limited',
        message: 'quá nhiều yêu cầu',
        status: 429,
        detail: <String, Object?>{'retry_after': 30},
      );
      expect(e.retryAfter, 30);
    });
  });

  test('a wrong password is displayed, not treated as a stale token', () {
    // auth.invalid_credentials is a real backend code (401, AuthenticationError
    // in app/application/auth/handlers.py). Without an explicit case it fell
    // through to the `status == 401 -> refreshThenRetry` default, which is the
    // wrong instruction: there is no token to refresh when the login itself is
    // what failed. The server message is already localised — show it.
    expect(
      policyActionFor('auth.invalid_credentials', status: 401),
      PolicyAction.none,
    );
  });

  test('an unknown 401 code still asks for a refresh', () {
    // The default must survive the case above: a genuinely unknown 401 on an
    // authenticated route most likely IS an expired token.
    expect(
      policyActionFor('some_future_code', status: 401),
      PolicyAction.refreshThenRetry,
    );
  });
}
