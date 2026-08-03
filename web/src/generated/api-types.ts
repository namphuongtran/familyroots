/**
 * GENERATED FILE — DO NOT EDIT BY HAND.
 * Source: the backend OpenAPI document (/openapi.json)
 * Regenerate with: pnpm gen:api
 */

export interface paths {
    "/api/v1/auth/register": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Register
         * @description Register — always the same response whether or not the email has an account
         *     (non-enumerating, ADR-021). Real state arrives after email verify + login.
         */
        post: operations["register_api_v1_auth_register_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/onboard": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Onboard Authenticated User
         * @description Attach the current authenticated user to a clan after OAuth login.
         */
        post: operations["onboard_authenticated_user_api_v1_auth_onboard_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/login": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Login
         * @description Authenticate a user via Supabase Auth.
         */
        post: operations["login_api_v1_auth_login_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/logout": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Logout
         * @description Invalidate the current session (revoke refresh tokens).
         */
        post: operations["logout_api_v1_auth_logout_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/refresh": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Refresh Token
         * @description Exchange a refresh token for a new access token.
         */
        post: operations["refresh_token_api_v1_auth_refresh_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/forgot-password": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Forgot Password
         * @description Trigger a password-reset email. ALWAYS returns 200 with the same message,
         *     regardless of whether the email exists or the provider is reachable — never leak
         *     account existence or provider state. Reset completion happens client-side via the
         *     Supabase SDK (verify recovery token + update password).
         */
        post: operations["forgot_password_api_v1_auth_forgot_password_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/resend-verification": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Resend Verification
         * @description Resend the email-verification link. ALWAYS returns 200 with the same message
         *     regardless of whether the email exists or the provider is reachable — never leak
         *     account existence or provider state.
         */
        post: operations["resend_verification_api_v1_auth_resend_verification_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/me": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Me
         * @description Return the authenticated user's profile.
         */
        get: operations["get_me_api_v1_auth_me_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /**
         * Update Me
         * @description Update the authenticated user's profile.
         */
        patch: operations["update_me_api_v1_auth_me_patch"];
        trace?: never;
    };
    "/api/v1/auth/me/fcm-token": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Register Fcm Token
         * @description Register or update an FCM push token.
         */
        post: operations["register_fcm_token_api_v1_auth_me_fcm_token_post"];
        /**
         * Remove Fcm Token
         * @description Remove an FCM token (e.g. on logout).
         */
        delete: operations["remove_fcm_token_api_v1_auth_me_fcm_token_delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/branches": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Branches
         * @description List all branches for the current clan.
         */
        get: operations["list_branches_api_v1_branches_get"];
        put?: never;
        /**
         * Create Branch
         * @description Create a new branch.
         */
        post: operations["create_branch_api_v1_branches_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/branches/{branch_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Branch
         * @description Get a single branch by ID.
         */
        get: operations["get_branch_api_v1_branches__branch_id__get"];
        put?: never;
        post?: never;
        /**
         * Delete Branch
         * @description Delete a branch (admin only).
         */
        delete: operations["delete_branch_api_v1_branches__branch_id__delete"];
        options?: never;
        head?: never;
        /**
         * Update Branch
         * @description Update a branch.
         */
        patch: operations["update_branch_api_v1_branches__branch_id__patch"];
        trace?: never;
    };
    "/api/v1/clans/me": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Own Clan
         * @description Get the current user's active clan info.
         */
        get: operations["get_own_clan_api_v1_clans_me_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /**
         * Update Own Clan
         * @description Update current clan info (admin only).
         */
        patch: operations["update_own_clan_api_v1_clans_me_patch"];
        trace?: never;
    };
    "/api/v1/clans/me/users": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Clan Users
         * @description List approved users in the current clan (paginated).
         */
        get: operations["list_clan_users_api_v1_clans_me_users_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/clans/me/users/pending": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Pending Users
         * @description List users pending approval (admin only).
         */
        get: operations["list_pending_users_api_v1_clans_me_users_pending_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/clans/me/users/{user_id}/approve": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Approve User
         * @description Approve a pending user (admin only).
         */
        post: operations["approve_user_api_v1_clans_me_users__user_id__approve_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/clans/me/users/{user_id}/reject": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Reject User
         * @description Reject a pending user (admin only).
         */
        post: operations["reject_user_api_v1_clans_me_users__user_id__reject_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/clans/me/users/{user_id}/role": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /**
         * Change User Role
         * @description Change a user's clan role (admin only).
         */
        patch: operations["change_user_role_api_v1_clans_me_users__user_id__role_patch"];
        trace?: never;
    };
    "/api/v1/clans/me/users/{user_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /**
         * Remove User
         * @description Remove a user from the clan (admin only).
         */
        delete: operations["remove_user_api_v1_clans_me_users__user_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/clans/me/founder": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Designate Founder
         * @description Designate or correct the clan's thủy tổ (founder) — roots GET /tree, anchors đời.
         */
        put: operations["designate_founder_api_v1_clans_me_founder_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/me/clans": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List My Clans
         * @description List all clans the authenticated user belongs to (a clan switcher — all
         *     approved memberships, unpaginated).
         */
        get: operations["list_my_clans_api_v1_me_clans_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/me/clans/{clan_id}/select": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Select Clan
         * @description Select a clan as the active context.
         */
        post: operations["select_clan_api_v1_me_clans__clan_id__select_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/persons": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Persons
         * @description List persons belonging to a clan with pagination.
         */
        get: operations["list_persons_api_v1_persons_get"];
        put?: never;
        /**
         * Create Person
         * @description Create a new person and add a clan membership.
         */
        post: operations["create_person_api_v1_persons_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/persons/search": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Search Persons
         * @description Fuzzy search persons in a clan by name.
         */
        get: operations["search_persons_api_v1_persons_search_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/persons/batch": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Batch Get Persons
         * @description Fetch multiple persons in one request with optional include/fields/profile.
         *
         *     Supported include tokens:
         *     - ``stats`` (spouse_count, child_count)
         *     - ``marriages``
         *     - ``parent_child``
         *     - ``timeline``
         *     - ``documents``
         *
         *     ``include`` applies globally. ``include_by_id`` allows per-person overrides.
         *     Unknown include tokens are ignored for backward compatibility.
         */
        post: operations["batch_get_persons_api_v1_persons_batch_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/persons/{person_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Person
         * @description Get a single person's full detail.
         */
        get: operations["get_person_api_v1_persons__person_id__get"];
        put?: never;
        post?: never;
        /**
         * Delete Person
         * @description Soft-delete a person (admin only).
         */
        delete: operations["delete_person_api_v1_persons__person_id__delete"];
        options?: never;
        head?: never;
        /**
         * Update Person
         * @description Update a person's details.
         */
        patch: operations["update_person_api_v1_persons__person_id__patch"];
        trace?: never;
    };
    "/api/v1/persons/{person_id}/restore": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Restore Person
         * @description Restore a soft-deleted person (admin only).
         */
        post: operations["restore_person_api_v1_persons__person_id__restore_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/persons/{person_id}/claim": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Submit Identity Claim
         * @description Submit a claim for linking a user profile to a person in the family tree.
         */
        post: operations["submit_identity_claim_api_v1_persons__person_id__claim_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/persons/{person_id}/marriages": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Person Marriages
         * @description Get all marriages for a person.
         */
        get: operations["person_marriages_api_v1_persons__person_id__marriages_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/persons/{person_id}/parent-child": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Person Parent Child
         * @description Get all parent-child relationships for a person.
         */
        get: operations["person_parent_child_api_v1_persons__person_id__parent_child_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/persons/{person_id}/documents": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Person Documents
         * @description Get all documents for a person.
         */
        get: operations["person_documents_api_v1_persons__person_id__documents_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/persons/{person_id}/events": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Person Events
         * @description Get all events for a person.
         */
        get: operations["person_events_api_v1_persons__person_id__events_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/persons/{person_id}/timeline": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Person Timeline
         * @description Return a chronological timeline of life events for a person.
         */
        get: operations["person_timeline_api_v1_persons__person_id__timeline_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/relationships/marriages": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Create Marriage
         * @description Create a marriage between two persons with validation.
         */
        post: operations["create_marriage_api_v1_relationships_marriages_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/relationships/marriages/{marriage_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Marriage
         * @description Get a marriage by ID.
         */
        get: operations["get_marriage_api_v1_relationships_marriages__marriage_id__get"];
        put?: never;
        post?: never;
        /**
         * Delete Marriage
         * @description Soft-delete a marriage (admin of managing clan only).
         */
        delete: operations["delete_marriage_api_v1_relationships_marriages__marriage_id__delete"];
        options?: never;
        head?: never;
        /**
         * Update Marriage
         * @description Update a marriage record (only by managing clan).
         */
        patch: operations["update_marriage_api_v1_relationships_marriages__marriage_id__patch"];
        trace?: never;
    };
    "/api/v1/relationships/parent-child": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Create Parent Child
         * @description Create a parent-child relationship with validation.
         */
        post: operations["create_parent_child_api_v1_relationships_parent_child_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/relationships/parent-child/{link_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Parent Child
         * @description Get a parent-child relationship by ID.
         */
        get: operations["get_parent_child_api_v1_relationships_parent_child__link_id__get"];
        put?: never;
        post?: never;
        /**
         * Delete Parent Child
         * @description Soft-delete a parent-child relationship (admin of managing clan only).
         */
        delete: operations["delete_parent_child_api_v1_relationships_parent_child__link_id__delete"];
        options?: never;
        head?: never;
        /**
         * Update Parent Child
         * @description Update a parent-child relationship (only by managing clan).
         */
        patch: operations["update_parent_child_api_v1_relationships_parent_child__link_id__patch"];
        trace?: never;
    };
    "/api/v1/documents": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Documents
         * @description List documents with optional filters, paginated.
         */
        get: operations["list_documents_api_v1_documents_get"];
        put?: never;
        /**
         * Upload Document
         * @description Upload a document/photo to storage and save metadata.
         */
        post: operations["upload_document_api_v1_documents_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/documents/{document_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Document
         * @description Get document metadata with a presigned download URL.
         */
        get: operations["get_document_api_v1_documents__document_id__get"];
        put?: never;
        post?: never;
        /**
         * Delete Document
         * @description Delete a document from storage and the database (admin only).
         */
        delete: operations["delete_document_api_v1_documents__document_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/documents/{document_id}/restore": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Restore Document
         * @description Restore a soft-deleted document (admin only).
         */
        post: operations["restore_document_api_v1_documents__document_id__restore_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/documents/{document_id}/set-avatar": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /**
         * Set Document As Avatar
         * @description Set a photo document as the person's avatar.
         *
         *     Publishes the image to the public avatars bucket and stamps the resulting
         *     permanent URL onto `persons.avatar_url` (ADR-036). `avatar_url` is returned so a
         *     client can render immediately without re-reading the person; it is the same value
         *     every person/tree response now carries.
         */
        patch: operations["set_document_as_avatar_api_v1_documents__document_id__set_avatar_patch"];
        trace?: never;
    };
    "/api/v1/events": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Events
         * @description List events with optional filters.
         */
        get: operations["list_events_api_v1_events_get"];
        put?: never;
        /**
         * Create Event
         * @description Create a new event.
         */
        post: operations["create_event_api_v1_events_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/events/upcoming": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Upcoming Events
         * @description Get upcoming events within the next N days.
         *
         *     ``today`` is computed HERE, in the platform timezone (Finding 3, pre-merge
         *     review) — not left to the handler's server-local ``date.today()`` fallback —
         *     so the "is it N days away" gate can't disagree with the platform's actual
         *     calendar day just because the container runs in a different system timezone.
         */
        get: operations["get_upcoming_events_api_v1_events_upcoming_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/events/{event_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Event */
        get: operations["get_event_api_v1_events__event_id__get"];
        put?: never;
        post?: never;
        /** Delete Event */
        delete: operations["delete_event_api_v1_events__event_id__delete"];
        options?: never;
        head?: never;
        /** Update Event */
        patch: operations["update_event_api_v1_events__event_id__patch"];
        trace?: never;
    };
    "/api/v1/events/{event_id}/restore": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Restore Event
         * @description Restore a soft-deleted event (ADR-022) — same role that may delete.
         */
        post: operations["restore_event_api_v1_events__event_id__restore_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tree": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Full Tree
         * @description Return the full family tree rooted at a person (or clan founder).
         */
        get: operations["get_full_tree_api_v1_tree_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tree/subtree/{person_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Subtree
         * @description Return a subtree rooted at a specific person.
         */
        get: operations["get_subtree_api_v1_tree_subtree__person_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tree/ancestors/{person_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Ancestors
         * @description Return the ancestor chain from a person up to the root.
         */
        get: operations["get_ancestors_api_v1_tree_ancestors__person_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tree/focus/{person_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Focus
         * @description Focus view: breadcrumb ancestors + focus + descendant window, with computed đời.
         */
        get: operations["get_focus_api_v1_tree_focus__person_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tree/path": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Find Path
         * @description Find the relationship path between two persons.
         */
        get: operations["find_path_api_v1_tree_path_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/exports/clan": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Export Clan
         * @description Download the full clan archive ("bản sao ngàn đời") — admin only.
         */
        get: operations["export_clan_api_v1_exports_clan_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/change-requests": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Change Requests
         * @description List change requests: the clan queue for reviewers, own proposals for viewers.
         */
        get: operations["list_change_requests_api_v1_change_requests_get"];
        put?: never;
        /**
         * Submit Change Request
         * @description Propose a correction to a person in the active clan.
         */
        post: operations["submit_change_request_api_v1_change_requests_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/change-requests/{change_request_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Change Request
         * @description Get one change request, including the live state of the record it targets.
         */
        get: operations["get_change_request_api_v1_change_requests__change_request_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/change-requests/{change_request_id}/approve": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Approve Change Request
         * @description Approve a change request and apply it to the target record.
         */
        post: operations["approve_change_request_api_v1_change_requests__change_request_id__approve_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/change-requests/{change_request_id}/reject": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Reject Change Request
         * @description Reject a change request. The target record is left untouched.
         */
        post: operations["reject_change_request_api_v1_change_requests__change_request_id__reject_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/claims": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List my identity claims
         * @description List identity claims submitted by the current user, across all clans.
         */
        get: operations["list_my_claims_api_v1_claims_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/claims/{claim_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /**
         * Cancel a pending claim
         * @description Cancel a pending identity claim submitted by the current user.
         */
        delete: operations["cancel_claim_api_v1_claims__claim_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/clans/{clan_id}/claims": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List claims for a clan
         * @description List cursor-paginated identity claims for persons created by this clan.
         */
        get: operations["list_clan_claims_api_v1_clans__clan_id__claims_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/clans/{clan_id}/claims/{claim_id}/approve": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Approve an identity claim
         * @description Approve a pending identity claim. Marks the user profile and rejects duplicate claims.
         */
        post: operations["approve_claim_api_v1_clans__clan_id__claims__claim_id__approve_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/clans/{clan_id}/claims/{claim_id}/reject": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Reject an identity claim */
        post: operations["reject_claim_api_v1_clans__clan_id__claims__claim_id__reject_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/clans/{clan_id}/claims/members/{user_id}/unlink": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Unlink a claimed identity
         * @description Unlink a claimed identity and revoke the link in UserProfile.
         */
        post: operations["unlink_identity_api_v1_clans__clan_id__claims_members__user_id__unlink_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/clans/{clan_id}/claims/members/{user_id}/prelink": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Admin Pre-link an identity
         * @description Administratively link a clan member to a person in the tree.
         */
        post: operations["prelink_identity_api_v1_clans__clan_id__claims_members__user_id__prelink_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/clans/{clan_id}/invitations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Invitations */
        get: operations["list_invitations_api_v1_clans__clan_id__invitations_get"];
        put?: never;
        /** Create Invitation */
        post: operations["create_invitation_api_v1_clans__clan_id__invitations_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/clans/{clan_id}/invitations/{invitation_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Revoke Invitation */
        delete: operations["revoke_invitation_api_v1_clans__clan_id__invitations__invitation_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/invitations/{token}/accept": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Accept Invitation */
        post: operations["accept_invitation_api_v1_invitations__token__accept_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/platform/clans": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List All Clans
         * @description List all clans on the platform.
         */
        get: operations["list_all_clans_api_v1_platform_clans_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/platform/clans/{clan_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Clan Detail
         * @description Get detailed clan info with aggregate stats.
         */
        get: operations["get_clan_detail_api_v1_platform_clans__clan_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/platform/clans/{clan_id}/suspend": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Suspend Clan
         * @description Suspend a clan.
         */
        post: operations["suspend_clan_api_v1_platform_clans__clan_id__suspend_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/platform/clans/{clan_id}/reactivate": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Reactivate Clan
         * @description Reactivate a suspended clan.
         */
        post: operations["reactivate_clan_api_v1_platform_clans__clan_id__reactivate_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/platform/metrics": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Platform Metrics
         * @description Platform-wide usage metrics.
         */
        get: operations["platform_metrics_api_v1_platform_metrics_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/platform/audit-log": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Audit Log
         * @description Cross-clan audit log.
         */
        get: operations["audit_log_api_v1_platform_audit_log_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/health": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Health
         * @description Liveness + readiness. Deliberately does NOT call the auth provider:
         *     a Supabase outage must not mark the pod unhealthy (restart loops) — auth
         *     paths already surface 503 per-request via IdentityUnavailableError.
         */
        get: operations["health_health_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /**
         * AuditLogEntryResponse
         * @description One entry in the cross-clan audit log.
         */
        AuditLogEntryResponse: {
            /** Id */
            id: string;
            /** Clan Id */
            clan_id?: string | null;
            /** Actor Id */
            actor_id: string;
            /** Actor Role */
            actor_role: string;
            /** Action */
            action: string;
            /** Resource Type */
            resource_type: string;
            /** Resource Id */
            resource_id?: string | null;
            /** Created At */
            created_at?: string | null;
        };
        /** AuthenticatedOnboardingRequest */
        AuthenticatedOnboardingRequest: {
            /**
             * Clan Action
             * @enum {string}
             */
            clan_action: "join" | "create";
            /** Clan Id */
            clan_id?: string | null;
            /** Clan Name */
            clan_name?: string | null;
            /** Clan Slug */
            clan_slug?: string | null;
        };
        /**
         * BatchError
         * @description One per-id failure in a batch fetch.
         */
        BatchError: {
            /** Id */
            id: string;
            /** Code */
            code: string;
        };
        /** Body_upload_document_api_v1_documents_post */
        Body_upload_document_api_v1_documents_post: {
            /** File */
            file: string;
            /** Title */
            title: string;
            /** Document Type */
            document_type: string;
            /** Person Id */
            person_id?: string | null;
            /** Description */
            description?: string | null;
            /** Taken Date */
            taken_date?: string | null;
            /** Taken Place */
            taken_place?: string | null;
        };
        /**
         * BranchCreateRequest
         * @description Request body for creating a branch within a clan.
         */
        BranchCreateRequest: {
            /** Name */
            name: string;
            /** Description */
            description?: string | null;
            /** Founder Person Id */
            founder_person_id?: string | null;
            /** Parent Branch Id */
            parent_branch_id?: string | null;
            /** Branch Order */
            branch_order?: number | null;
        };
        /**
         * BranchResponse
         * @description Response schema for a branch.
         */
        BranchResponse: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Clan Id
             * Format: uuid
             */
            clan_id: string;
            /** Name */
            name: string;
            /** Description */
            description?: string | null;
            /** Founder Person Id */
            founder_person_id?: string | null;
            /** Parent Branch Id */
            parent_branch_id?: string | null;
            /** Branch Order */
            branch_order?: number | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /**
         * BranchUpdateRequest
         * @description Request body for updating a branch.
         */
        BranchUpdateRequest: {
            /** Name */
            name?: string | null;
            /** Description */
            description?: string | null;
            /** Founder Person Id */
            founder_person_id?: string | null;
            /** Parent Branch Id */
            parent_branch_id?: string | null;
            /** Branch Order */
            branch_order?: number | null;
        };
        /**
         * ChangeRequestConflict
         * @description One proposed field whose target value moved to something else since submission.
         */
        ChangeRequestConflict: {
            /** Field */
            field: string;
            /** Base */
            base?: unknown;
            /** Current */
            current?: unknown;
            /** Proposed */
            proposed?: unknown;
        };
        /**
         * ChangeRequestCreateRequest
         * @description Request body for proposing a change.
         *
         *     ``action``/``resource_type`` are accepted (and constrained to the persisted
         *     CHECK-constraint vocabulary) rather than implied, so adding marriage/event/
         *     document proposals later needs no request-shape change. Anything outside the
         *     combination this build executes is rejected with
         *     ``change_request.unsupported_operation`` (422) by the domain, not by this schema
         *     — one code, one place, whatever the caller sends.
         */
        ChangeRequestCreateRequest: {
            /**
             * Action
             * @default update
             */
            action: string;
            /**
             * Resource Type
             * @default person
             */
            resource_type: string;
            /** Resource Id */
            resource_id?: string | null;
            /**
             * Changes
             * @description Proposed field values, same field names and value shapes as the PATCH /persons/{id} body (minus expected_version).
             */
            changes?: {
                [key: string]: unknown;
            };
            /**
             * Note
             * @description Optional free-text explanation from the requester.
             */
            note?: string | null;
        };
        /**
         * ChangeRequestResponse
         * @description Response schema for a change request.
         */
        ChangeRequestResponse: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Clan Id
             * Format: uuid
             */
            clan_id: string;
            /**
             * Requester Id
             * Format: uuid
             */
            requester_id: string;
            /** Action */
            action: string;
            /** Resource Type */
            resource_type: string;
            /** Resource Id */
            resource_id?: string | null;
            /** Changes */
            changes?: {
                [key: string]: unknown;
            };
            /** Note */
            note?: string | null;
            /** Status */
            status: string;
            /** Reviewed By */
            reviewed_by?: string | null;
            /** Reviewed At */
            reviewed_at?: string | null;
            /** Review Notes */
            review_notes?: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            target: components["schemas"]["ChangeRequestTarget"];
        };
        /**
         * ChangeRequestReviewRequest
         * @description Request body for approving or rejecting a change request.
         */
        ChangeRequestReviewRequest: {
            /** Review Notes */
            review_notes?: string | null;
        };
        /**
         * ChangeRequestTarget
         * @description Live state of the resource a proposal points at (ADR-037).
         *
         *     Present so a reviewer is never asked to approve blind: ``is_stale`` says the
         *     record moved at all, and ``conflicts`` says whether any of *these* fields moved
         *     — the only kind of movement that blocks approval.
         */
        ChangeRequestTarget: {
            /** Resource Type */
            resource_type: string;
            /** Resource Id */
            resource_id?: string | null;
            /**
             * Exists
             * @default false
             */
            exists: boolean;
            /**
             * Is Deleted
             * @default false
             */
            is_deleted: boolean;
            /**
             * Base Version
             * @default 1
             */
            base_version: number;
            /** Current Version */
            current_version?: number | null;
            /**
             * Is Stale
             * @default false
             */
            is_stale: boolean;
            /** Conflicts */
            conflicts?: components["schemas"]["ChangeRequestConflict"][];
        };
        /**
         * ClanDetailResponse
         * @description Detail projection for a single clan, with aggregate stats.
         */
        ClanDetailResponse: {
            /** Id */
            id: string;
            /** Name */
            name: string;
            /** Slug */
            slug: string;
            /** Is Active */
            is_active: boolean;
            /** Description */
            description?: string | null;
            /** Origin Place */
            origin_place?: string | null;
            stats: components["schemas"]["ClanStatsResponse"];
            /** Created At */
            created_at?: string | null;
        };
        /**
         * ClanResponse
         * @description Full clan detail response.
         */
        ClanResponse: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Name */
            name: string;
            /** Slug */
            slug: string;
            /** Description */
            description?: string | null;
            /** Origin Place */
            origin_place?: string | null;
            /** Founded Year */
            founded_year?: number | null;
            /** Avatar Url */
            avatar_url?: string | null;
            /** Motto */
            motto?: string | null;
            /** Ancestral Hall Location */
            ancestral_hall_location?: string | null;
            /** Clan Rules */
            clan_rules?: string | null;
            /** Is Active */
            is_active: boolean;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /**
         * ClanStatsResponse
         * @description Aggregate membership counts for a single clan.
         */
        ClanStatsResponse: {
            /** Total Members */
            total_members: number;
            /** Total Users */
            total_users: number;
        };
        /**
         * ClanStatusResponse
         * @description Acknowledgement body for suspend/reactivate.
         */
        ClanStatusResponse: {
            /** Is Active */
            is_active: boolean;
            /** Clan Id */
            clan_id: string;
        };
        /**
         * ClanSummaryResponse
         * @description One clan row in the platform-wide clan listing.
         */
        ClanSummaryResponse: {
            /** Id */
            id: string;
            /** Name */
            name: string;
            /** Slug */
            slug: string;
            /** Is Active */
            is_active: boolean;
            /** Created At */
            created_at?: string | null;
        };
        /**
         * ClanSwitchResponse
         * @description Response for POST /me/clans/{clan_id}/select — confirm clan selection.
         */
        ClanSwitchResponse: {
            /**
             * Clan Id
             * Format: uuid
             */
            clan_id: string;
            /** Clan Name */
            clan_name: string;
            /** Clan Slug */
            clan_slug: string;
            /** Role */
            role: string;
            /** Message */
            message: string;
        };
        /**
         * ClanUpdateRequest
         * @description Request body for updating clan info.
         */
        ClanUpdateRequest: {
            /** Name */
            name?: string | null;
            /** Description */
            description?: string | null;
            /** Origin Place */
            origin_place?: string | null;
            /** Founded Year */
            founded_year?: number | null;
            /** Avatar Url */
            avatar_url?: string | null;
            /** Motto */
            motto?: string | null;
            /** Ancestral Hall Location */
            ancestral_hall_location?: string | null;
            /** Clan Rules */
            clan_rules?: string | null;
        };
        /**
         * ClanUserSummary
         * @description One approved member in GET /clans/me/users (viewer-readable).
         *
         *     Carries ``display_name`` but deliberately **no** ``email``: this list is
         *     readable by every approved member of the clan, so an ``email`` field here
         *     would broadcast each member's login address to the whole clan. The
         *     admin-only pending queue uses the separate ``PendingClanUserSummary``.
         *     See ADR-039 before adding any contact field to this model.
         */
        ClanUserSummary: {
            /** Id */
            id: string;
            /** User Id */
            user_id: string;
            /** Role */
            role: string;
            /** Person Id */
            person_id?: string | null;
            /** Display Name */
            display_name?: string | null;
            /** Created At */
            created_at: string;
        };
        /** DocumentResponse */
        DocumentResponse: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Clan Id
             * Format: uuid
             */
            clan_id: string;
            /** Person Id */
            person_id?: string | null;
            /** Title */
            title: string;
            /** Document Type */
            document_type: string;
            /** Description */
            description?: string | null;
            /** Storage Path */
            storage_path: string;
            /** Presigned Url */
            presigned_url?: string | null;
            /** Presigned Url Expires At */
            presigned_url_expires_at?: string | null;
            /** File Size Bytes */
            file_size_bytes?: number | null;
            /** Mime Type */
            mime_type?: string | null;
            /** Original Filename */
            original_filename?: string | null;
            /** Taken Date */
            taken_date?: string | null;
            /** Taken Place */
            taken_place?: string | null;
            /**
             * Is Avatar
             * @default false
             */
            is_avatar: boolean;
            /**
             * Created By
             * Format: uuid
             */
            created_by: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /** DocumentSummary */
        DocumentSummary: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Title */
            title: string;
            /** Document Type */
            document_type: string;
            /** Mime Type */
            mime_type?: string | null;
            /** File Size Bytes */
            file_size_bytes?: number | null;
            /**
             * Is Avatar
             * @default false
             */
            is_avatar: boolean;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
        };
        /** Envelope[BranchResponse] */
        Envelope_BranchResponse_: {
            data: components["schemas"]["BranchResponse"];
        };
        /** Envelope[ChangeRequestResponse] */
        Envelope_ChangeRequestResponse_: {
            data: components["schemas"]["ChangeRequestResponse"];
        };
        /** Envelope[ClanDetailResponse] */
        Envelope_ClanDetailResponse_: {
            data: components["schemas"]["ClanDetailResponse"];
        };
        /** Envelope[ClanResponse] */
        Envelope_ClanResponse_: {
            data: components["schemas"]["ClanResponse"];
        };
        /** Envelope[ClanStatusResponse] */
        Envelope_ClanStatusResponse_: {
            data: components["schemas"]["ClanStatusResponse"];
        };
        /** Envelope[ClanSwitchResponse] */
        Envelope_ClanSwitchResponse_: {
            data: components["schemas"]["ClanSwitchResponse"];
        };
        /** Envelope[DocumentResponse] */
        Envelope_DocumentResponse_: {
            data: components["schemas"]["DocumentResponse"];
        };
        /** Envelope[EventResponse] */
        Envelope_EventResponse_: {
            data: components["schemas"]["EventResponse"];
        };
        /** Envelope[FocusView] */
        Envelope_FocusView_: {
            data: components["schemas"]["FocusView"];
        };
        /** Envelope[FounderDesignationResponse] */
        Envelope_FounderDesignationResponse_: {
            data: components["schemas"]["FounderDesignationResponse"];
        };
        /** Envelope[IdentityClaimResponse] */
        Envelope_IdentityClaimResponse_: {
            data: components["schemas"]["IdentityClaimResponse"];
        };
        /** Envelope[InvitationAcceptedResponse] */
        Envelope_InvitationAcceptedResponse_: {
            data: components["schemas"]["InvitationAcceptedResponse"];
        };
        /** Envelope[InvitationCreatedResponse] */
        Envelope_InvitationCreatedResponse_: {
            data: components["schemas"]["InvitationCreatedResponse"];
        };
        /** Envelope[LoginResponse] */
        Envelope_LoginResponse_: {
            data: components["schemas"]["LoginResponse"];
        };
        /** Envelope[MarriageResponse] */
        Envelope_MarriageResponse_: {
            data: components["schemas"]["MarriageResponse"];
        };
        /** Envelope[MessageData] */
        Envelope_MessageData_: {
            data: components["schemas"]["MessageData"];
        };
        /** Envelope[ParentChildResponse] */
        Envelope_ParentChildResponse_: {
            data: components["schemas"]["ParentChildResponse"];
        };
        /** Envelope[PersonResponse] */
        Envelope_PersonResponse_: {
            data: components["schemas"]["PersonResponse"];
        };
        /** Envelope[PlatformMetricsResponse] */
        Envelope_PlatformMetricsResponse_: {
            data: components["schemas"]["PlatformMetricsResponse"];
        };
        /** Envelope[RegisterResponse] */
        Envelope_RegisterResponse_: {
            data: components["schemas"]["RegisterResponse"];
        };
        /** Envelope[RelationshipPathResponse] */
        Envelope_RelationshipPathResponse_: {
            data: components["schemas"]["RelationshipPathResponse"];
        };
        /** Envelope[TokenRefreshResponse] */
        Envelope_TokenRefreshResponse_: {
            data: components["schemas"]["TokenRefreshResponse"];
        };
        /** Envelope[TreeResponse] */
        Envelope_TreeResponse_: {
            data: components["schemas"]["TreeResponse"];
        };
        /** Envelope[UserActionResponse] */
        Envelope_UserActionResponse_: {
            data: components["schemas"]["UserActionResponse"];
        };
        /** Envelope[UserProfile] */
        Envelope_UserProfile_: {
            data: components["schemas"]["UserProfile"];
        };
        /** Envelope[UserRoleChangeResponse] */
        Envelope_UserRoleChangeResponse_: {
            data: components["schemas"]["UserRoleChangeResponse"];
        };
        /** Envelope[list[BranchResponse]] */
        Envelope_list_BranchResponse__: {
            /** Data */
            data: components["schemas"]["BranchResponse"][];
        };
        /** Envelope[list[DocumentSummary]] */
        Envelope_list_DocumentSummary__: {
            /** Data */
            data: components["schemas"]["DocumentSummary"][];
        };
        /** Envelope[list[EventResponse]] */
        Envelope_list_EventResponse__: {
            /** Data */
            data: components["schemas"]["EventResponse"][];
        };
        /** Envelope[list[InvitationResponse]] */
        Envelope_list_InvitationResponse__: {
            /** Data */
            data: components["schemas"]["InvitationResponse"][];
        };
        /** Envelope[list[MarriageResponse]] */
        Envelope_list_MarriageResponse__: {
            /** Data */
            data: components["schemas"]["MarriageResponse"][];
        };
        /** Envelope[list[ParentChildResponse]] */
        Envelope_list_ParentChildResponse__: {
            /** Data */
            data: components["schemas"]["ParentChildResponse"][];
        };
        /** Envelope[list[PersonSearchResult]] */
        Envelope_list_PersonSearchResult__: {
            /** Data */
            data: components["schemas"]["PersonSearchResult"][];
        };
        /** Envelope[list[TimelineEvent]] */
        Envelope_list_TimelineEvent__: {
            /** Data */
            data: components["schemas"]["TimelineEvent"][];
        };
        /** Envelope[list[TreeNodeDetail]] */
        Envelope_list_TreeNodeDetail__: {
            /** Data */
            data: components["schemas"]["TreeNodeDetail"][];
        };
        /** Envelope[list[UpcomingEvent]] */
        Envelope_list_UpcomingEvent__: {
            /** Data */
            data: components["schemas"]["UpcomingEvent"][];
        };
        /** Envelope[list[UserClanMembership]] */
        Envelope_list_UserClanMembership__: {
            /** Data */
            data: components["schemas"]["UserClanMembership"][];
        };
        /** ErrorDetail */
        ErrorDetail: {
            /** Code */
            code: string;
            /** Message */
            message: string;
            /** Detail */
            detail?: {
                [key: string]: unknown;
            };
        };
        /**
         * ErrorEnvelope
         * @description The stable error envelope every non-2xx response uses.
         */
        ErrorEnvelope: {
            error: components["schemas"]["ErrorDetail"];
        };
        /** EventCreateRequest */
        EventCreateRequest: {
            /** Person Id */
            person_id?: string | null;
            /** Event Type */
            event_type: string;
            /** Title */
            title: string;
            /** Description */
            description?: string | null;
            /**
             * Event Date
             * Format: date
             */
            event_date: string;
            /**
             * Event Date Precision
             * @default exact
             */
            event_date_precision: string;
            /** Event Date Display */
            event_date_display?: string | null;
            /**
             * Is Lunar Calendar
             * @default false
             */
            is_lunar_calendar: boolean;
            /**
             * Is Recurring
             * @default true
             */
            is_recurring: boolean;
            /**
             * Notify Days Before
             * @default 7
             */
            notify_days_before: number;
        };
        /**
         * EventPersonSummary
         * @description Minimal person payload embedded in event responses.
         */
        EventPersonSummary: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Full Name */
            full_name: string;
            /** Avatar Url */
            avatar_url?: string | null;
        };
        /** EventResponse */
        EventResponse: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Clan Id
             * Format: uuid
             */
            clan_id: string;
            /** Person Id */
            person_id?: string | null;
            /** Event Type */
            event_type: string;
            /** Title */
            title: string;
            /** Description */
            description?: string | null;
            event_date?: components["schemas"]["HistoricalDate"];
            /** Is Lunar Calendar */
            is_lunar_calendar: boolean;
            /** Is Recurring */
            is_recurring: boolean;
            /** Notify Days Before */
            notify_days_before: number;
            /**
             * Created By
             * Format: uuid
             */
            created_by: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
            /**
             * Version
             * @default 1
             */
            version: number;
            /**
             * Is Deleted
             * @default false
             */
            is_deleted: boolean;
        };
        /** EventUpdateRequest */
        EventUpdateRequest: {
            /** Event Type */
            event_type?: string | null;
            /** Title */
            title?: string | null;
            /** Description */
            description?: string | null;
            /** Event Date */
            event_date?: string | null;
            /** Event Date Precision */
            event_date_precision?: string | null;
            /** Event Date Display */
            event_date_display?: string | null;
            /** Is Lunar Calendar */
            is_lunar_calendar?: boolean | null;
            /** Is Recurring */
            is_recurring?: boolean | null;
            /** Notify Days Before */
            notify_days_before?: number | null;
            /** Expected Version */
            expected_version: number;
        };
        /** FCMTokenRequest */
        FCMTokenRequest: {
            /** Token */
            token: string;
            /**
             * Device Platform
             * @enum {string}
             */
            device_platform: "android" | "ios" | "web";
        };
        /**
         * FocusAncestor
         * @description One breadcrumb ancestor above the focus person (thủy-tổ-first).
         */
        FocusAncestor: {
            /** Id */
            id: string;
            /** Full Name */
            full_name: string;
            /** Gender */
            gender: string;
            birth_date?: components["schemas"]["HistoricalDate"];
            death_date?: components["schemas"]["HistoricalDate"];
            /** Avatar Url */
            avatar_url?: string | null;
            /** Generation */
            generation?: number | null;
            /**
             * Is Founder
             * @default false
             */
            is_founder: boolean;
        };
        /**
         * FocusTreeNode
         * @description A node in the focus subtree, with focus-only enrichment fields.
         */
        FocusTreeNode: {
            /** Id */
            id: string;
            /** Full Name */
            full_name: string;
            /** Gender */
            gender: string;
            /** Birth Name */
            birth_name?: string | null;
            /** Posthumous Name */
            posthumous_name?: string | null;
            birth_date?: components["schemas"]["HistoricalDate"];
            death_date?: components["schemas"]["HistoricalDate"];
            /** Birth Place */
            birth_place?: string | null;
            /** Avatar Url */
            avatar_url?: string | null;
            /** Membership Role */
            membership_role?: string | null;
            /**
             * Is Founder
             * @default false
             */
            is_founder: boolean;
            /** Generation */
            generation?: number | null;
            /**
             * Depth
             * @default 0
             */
            depth: number;
            /** Branch Id */
            branch_id?: string | null;
            /** Branch Name */
            branch_name?: string | null;
            /** Branch Order */
            branch_order?: number | null;
            /**
             * Has More Descendants
             * @default false
             */
            has_more_descendants: boolean;
            /** Mother Id */
            mother_id?: string | null;
            /** Mother Spouse Order */
            mother_spouse_order?: number | null;
            /**
             * Pedigree Collapse Ref
             * @default false
             */
            pedigree_collapse_ref: boolean;
            /**
             * Spouses
             * @default []
             */
            spouses: components["schemas"]["SpouseNode"][];
            /**
             * Children
             * @default []
             */
            children: components["schemas"]["FocusTreeNode"][];
        };
        /**
         * FocusView
         * @description Consolidated payload for the interactive focus-tree screen.
         */
        FocusView: {
            /** Focus Person Id */
            focus_person_id: string;
            /** Generation Of Focus */
            generation_of_focus?: number | null;
            /**
             * Ancestors
             * @default []
             */
            ancestors: components["schemas"]["FocusAncestor"][];
            focus_subtree?: components["schemas"]["FocusTreeNode"] | null;
        };
        /** ForgotPasswordRequest */
        ForgotPasswordRequest: {
            /**
             * Email
             * Format: email
             */
            email: string;
        };
        /**
         * FounderDesignationRequest
         * @description Body for PUT /clans/me/founder — designate or correct the thủy tổ.
         */
        FounderDesignationRequest: {
            /**
             * Person Id
             * Format: uuid
             */
            person_id: string;
        };
        /**
         * FounderDesignationResponse
         * @description Result of a founder designation (ADR-026).
         */
        FounderDesignationResponse: {
            /**
             * Person Id
             * Format: uuid
             */
            person_id: string;
            /** Previous Person Id */
            previous_person_id?: string | null;
            /** Message */
            message: string;
        };
        /**
         * HistoricalDate
         * @description A historical date with precision and optional human-readable/lunar representation.
         */
        HistoricalDate: {
            /** Date */
            date?: string | null;
            /**
             * Precision
             * @default exact
             */
            precision: string;
            /** Display */
            display?: string | null;
            /** Lunar */
            lunar?: string | null;
        };
        /** IdentityClaimPrelink */
        IdentityClaimPrelink: {
            /**
             * Person Id
             * Format: uuid
             * @description ID of the Person to link the user to.
             */
            person_id: string;
        };
        /** IdentityClaimResponse */
        IdentityClaimResponse: {
            /** Requester Note */
            requester_note?: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
            /**
             * Person Id
             * Format: uuid
             */
            person_id: string;
            /** Status */
            status: string;
            /** Reviewer Note */
            reviewer_note?: string | null;
            /** Reviewed By */
            reviewed_by?: string | null;
            /** Reviewed At */
            reviewed_at?: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /** IdentityClaimReview */
        IdentityClaimReview: {
            /** Reviewer Note */
            reviewer_note?: string | null;
        };
        /** IdentityClaimSubmit */
        IdentityClaimSubmit: {
            /** Requester Note */
            requester_note?: string | null;
        };
        /** IdentityClaimUnlink */
        IdentityClaimUnlink: {
            /**
             * Reason
             * @description Mandatory reason for unlinking identity.
             */
            reason: string;
        };
        /** InvitationAcceptedResponse */
        InvitationAcceptedResponse: {
            /**
             * Clan Id
             * Format: uuid
             */
            clan_id: string;
            /** Role */
            role: string;
            /** Message */
            message: string;
        };
        /** InvitationCreateRequest */
        InvitationCreateRequest: {
            /**
             * Email
             * Format: email
             */
            email: string;
            /**
             * Role
             * @default viewer
             */
            role: string;
        };
        /** InvitationCreatedResponse */
        InvitationCreatedResponse: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Email */
            email: string;
            /** Role */
            role: string;
            /** Token */
            token: string;
            /**
             * Expires At
             * Format: date-time
             */
            expires_at: string;
            /** Accept Path */
            accept_path: string;
        };
        /** InvitationResponse */
        InvitationResponse: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Clan Id
             * Format: uuid
             */
            clan_id: string;
            /** Email */
            email: string;
            /** Role */
            role: string;
            /** Status */
            status: string;
            /**
             * Expires At
             * Format: date-time
             */
            expires_at: string;
            /** Accepted At */
            accepted_at?: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
        };
        /**
         * ListMeta
         * @description Cursor-pagination meta carried by every list endpoint.
         */
        ListMeta: {
            /** Cursor */
            cursor?: string | null;
            /**
             * Has More
             * @default false
             */
            has_more: boolean;
            /**
             * Limit
             * @default 20
             */
            limit: number;
        };
        /** LoginRequest */
        LoginRequest: {
            /**
             * Email
             * Format: email
             */
            email: string;
            /** Password */
            password: string;
        };
        /** LoginResponse */
        LoginResponse: {
            /** Access Token */
            access_token: string;
            /** Refresh Token */
            refresh_token: string;
            /** Expires In */
            expires_in: number;
            user: components["schemas"]["UserProfile"];
        };
        /**
         * MarriageCreateRequest
         * @description Request body for creating a marriage record.
         */
        MarriageCreateRequest: {
            /**
             * Person1 Id
             * Format: uuid
             */
            person1_id: string;
            /**
             * Person2 Id
             * Format: uuid
             */
            person2_id: string;
            /** Marriage Date */
            marriage_date?: string | null;
            /**
             * Marriage Date Precision
             * @default exact
             */
            marriage_date_precision: string;
            /** Marriage Date Display */
            marriage_date_display?: string | null;
            /** Divorce Date */
            divorce_date?: string | null;
            /**
             * Divorce Date Precision
             * @default exact
             */
            divorce_date_precision: string;
            /** Divorce Date Display */
            divorce_date_display?: string | null;
            /** Marriage Place */
            marriage_place?: string | null;
            /**
             * Status
             * @default married
             */
            status: string;
            /** Spouse Order */
            spouse_order?: number | null;
            /** Notes */
            notes?: string | null;
        };
        /**
         * MarriageResponse
         * @description Response schema for a marriage record.
         */
        MarriageResponse: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Person1 Id
             * Format: uuid
             */
            person1_id: string;
            /**
             * Person2 Id
             * Format: uuid
             */
            person2_id: string;
            /**
             * Created By Clan Id
             * Format: uuid
             */
            created_by_clan_id: string;
            marriage_date?: components["schemas"]["HistoricalDate"];
            divorce_date?: components["schemas"]["HistoricalDate"];
            /** Marriage Place */
            marriage_place?: string | null;
            /** Status */
            status: string;
            /** Spouse Order */
            spouse_order?: number | null;
            /** Notes */
            notes?: string | null;
            /**
             * Created By
             * Format: uuid
             */
            created_by: string;
            /** Updated By */
            updated_by?: string | null;
            /**
             * Is Deleted
             * @default false
             */
            is_deleted: boolean;
            /** Deleted At */
            deleted_at?: string | null;
            /** Deleted By */
            deleted_by?: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
            /**
             * Version
             * @default 1
             */
            version: number;
        };
        /**
         * MarriageUpdateRequest
         * @description Request body for updating a marriage record.
         */
        MarriageUpdateRequest: {
            /** Marriage Date */
            marriage_date?: string | null;
            /** Marriage Date Precision */
            marriage_date_precision?: string | null;
            /** Marriage Date Display */
            marriage_date_display?: string | null;
            /** Divorce Date */
            divorce_date?: string | null;
            /** Divorce Date Precision */
            divorce_date_precision?: string | null;
            /** Divorce Date Display */
            divorce_date_display?: string | null;
            /** Marriage Place */
            marriage_place?: string | null;
            /** Status */
            status?: string | null;
            /** Spouse Order */
            spouse_order?: number | null;
            /** Notes */
            notes?: string | null;
            /** Expected Version */
            expected_version: number;
        };
        /**
         * MessageData
         * @description Delete/action acknowledgements: {"data": {"message": ..., "id": ...}}.
         */
        MessageData: {
            /** Message */
            message: string;
            /** Id */
            id?: string | null;
        };
        /** PageEnvelope[AuditLogEntryResponse] */
        PageEnvelope_AuditLogEntryResponse_: {
            /** Data */
            data: components["schemas"]["AuditLogEntryResponse"][];
            meta: components["schemas"]["ListMeta"];
        };
        /** PageEnvelope[ChangeRequestResponse] */
        PageEnvelope_ChangeRequestResponse_: {
            /** Data */
            data: components["schemas"]["ChangeRequestResponse"][];
            meta: components["schemas"]["ListMeta"];
        };
        /** PageEnvelope[ClanSummaryResponse] */
        PageEnvelope_ClanSummaryResponse_: {
            /** Data */
            data: components["schemas"]["ClanSummaryResponse"][];
            meta: components["schemas"]["ListMeta"];
        };
        /** PageEnvelope[ClanUserSummary] */
        PageEnvelope_ClanUserSummary_: {
            /** Data */
            data: components["schemas"]["ClanUserSummary"][];
            meta: components["schemas"]["ListMeta"];
        };
        /** PageEnvelope[DocumentResponse] */
        PageEnvelope_DocumentResponse_: {
            /** Data */
            data: components["schemas"]["DocumentResponse"][];
            meta: components["schemas"]["ListMeta"];
        };
        /** PageEnvelope[EventResponse] */
        PageEnvelope_EventResponse_: {
            /** Data */
            data: components["schemas"]["EventResponse"][];
            meta: components["schemas"]["ListMeta"];
        };
        /** PageEnvelope[IdentityClaimResponse] */
        PageEnvelope_IdentityClaimResponse_: {
            /** Data */
            data: components["schemas"]["IdentityClaimResponse"][];
            meta: components["schemas"]["ListMeta"];
        };
        /** PageEnvelope[PendingClanUserSummary] */
        PageEnvelope_PendingClanUserSummary_: {
            /** Data */
            data: components["schemas"]["PendingClanUserSummary"][];
            meta: components["schemas"]["ListMeta"];
        };
        /** PageEnvelope[PersonResponse] */
        PageEnvelope_PersonResponse_: {
            /** Data */
            data: components["schemas"]["PersonResponse"][];
            meta: components["schemas"]["ListMeta"];
        };
        /**
         * ParentChildCreateRequest
         * @description Request body for creating a parent-child relationship.
         */
        ParentChildCreateRequest: {
            /**
             * Parent Id
             * Format: uuid
             */
            parent_id: string;
            /**
             * Child Id
             * Format: uuid
             */
            child_id: string;
            /**
             * Relationship Type
             * @default biological
             */
            relationship_type: string;
            /** Birth Order */
            birth_order?: number | null;
            /** Notes */
            notes?: string | null;
        };
        /**
         * ParentChildResponse
         * @description Response schema for a parent-child relationship.
         */
        ParentChildResponse: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Parent Id
             * Format: uuid
             */
            parent_id: string;
            /**
             * Child Id
             * Format: uuid
             */
            child_id: string;
            /**
             * Created By Clan Id
             * Format: uuid
             */
            created_by_clan_id: string;
            /** Relationship Type */
            relationship_type: string;
            /** Birth Order */
            birth_order?: number | null;
            /** Notes */
            notes?: string | null;
            /**
             * Created By
             * Format: uuid
             */
            created_by: string;
            /** Updated By */
            updated_by?: string | null;
            /**
             * Is Deleted
             * @default false
             */
            is_deleted: boolean;
            /** Deleted At */
            deleted_at?: string | null;
            /** Deleted By */
            deleted_by?: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
            /**
             * Version
             * @default 1
             */
            version: number;
        };
        /**
         * ParentChildUpdateRequest
         * @description Request body for updating a parent-child relationship.
         */
        ParentChildUpdateRequest: {
            /** Relationship Type */
            relationship_type?: string | null;
            /** Birth Order */
            birth_order?: number | null;
            /** Notes */
            notes?: string | null;
            /** Expected Version */
            expected_version: number;
        };
        /**
         * PathStep
         * @description One node along a relationship path.
         *
         *     The kinship-descriptor-only fields (``birth_date``/``birth_date_precision``)
         *     are stripped by the handler before the response, so they are absent here.
         */
        PathStep: {
            /** Person Id */
            person_id: string;
            /** Full Name */
            full_name: string;
            /** Gender */
            gender: string;
            /** Edge Type */
            edge_type?: string | null;
            /** Avatar Url */
            avatar_url?: string | null;
        };
        /**
         * PendingClanUserSummary
         * @description One pending join request in GET /clans/me/users/pending (admin-only).
         *
         *     Intentionally NOT a subclass of :class:`ClanUserSummary`, and intentionally
         *     duplicating its fields: subclassing would mean any field added to the
         *     viewer-readable model silently widens this one too — and, worse, invites the
         *     inverse "tidy-up" that merges the two and leaks ``email`` to every viewer.
         *     The asymmetry is the point; see ADR-039.
         *
         *     ``email`` is justified here and only here: the admin is making an identity
         *     decision (approving grants read access to hundreds of living relatives'
         *     records), already holds approve/reject/role powers, and the address is the
         *     account holder's own registration email — not a genealogy record about a
         *     third party.
         */
        PendingClanUserSummary: {
            /** Id */
            id: string;
            /** User Id */
            user_id: string;
            /** Role */
            role: string;
            /** Person Id */
            person_id?: string | null;
            /** Display Name */
            display_name?: string | null;
            /** Email */
            email?: string | null;
            /** Created At */
            created_at: string;
        };
        /**
         * PersonBatchEnvelope
         * @description POST /persons/batch: {data: [<person>], meta: {errors: [...]}}.
         *
         *     `data` items are the same dynamic person projection as GET /persons/{id}
         *     (documented as the full PersonResponse; sparse `fields=`/`include=` are subsets).
         */
        PersonBatchEnvelope: {
            /** Data */
            data: components["schemas"]["PersonResponse"][];
            meta: components["schemas"]["PersonBatchMeta"];
        };
        /**
         * PersonBatchGetRequest
         * @description Request body for fetching multiple persons in one read operation.
         * @example {
         *       "fields": "id,full_name,stats",
         *       "ids": [
         *         "11111111-1111-1111-1111-111111111111",
         *         "22222222-2222-2222-2222-222222222222"
         *       ],
         *       "include": "stats",
         *       "include_by_id": {
         *         "11111111-1111-1111-1111-111111111111": "marriages,parent_child"
         *       },
         *       "profile": "summary"
         *     }
         */
        PersonBatchGetRequest: {
            /** Ids */
            ids: string[];
            /**
             * Profile
             * @default full
             */
            profile: string;
            /**
             * Include
             * @description Global comma-separated embedded resources. Supported: stats,marriages,parent_child,timeline,documents
             */
            include?: string | null;
            /**
             * Fields
             * @description Comma-separated sparse fields. Example: id,full_name,stats
             */
            fields?: string | null;
            /**
             * Include By Id
             * @description Per-person embedded resources keyed by person id. Values are comma-separated include tokens with same support as include.
             */
            include_by_id?: {
                [key: string]: string;
            } | null;
        };
        /**
         * PersonBatchMeta
         * @description meta for POST /persons/batch — the sanctioned `errors` adjunct (CLAUDE.md).
         */
        PersonBatchMeta: {
            /**
             * Errors
             * @default []
             */
            errors: components["schemas"]["BatchError"][];
        };
        /**
         * PersonCreateRequest
         * @description Request body for creating a new person.
         */
        PersonCreateRequest: {
            /** Full Name */
            full_name: string;
            /** Birth Name */
            birth_name?: string | null;
            /** Courtesy Name */
            courtesy_name?: string | null;
            /** Posthumous Name */
            posthumous_name?: string | null;
            /** Alias Name */
            alias_name?: string | null;
            /**
             * Gender
             * @default unknown
             */
            gender: string;
            /** Birth Date */
            birth_date?: string | null;
            /**
             * Birth Date Precision
             * @default exact
             */
            birth_date_precision: string;
            /** Birth Date Display */
            birth_date_display?: string | null;
            /** Death Date */
            death_date?: string | null;
            /**
             * Death Date Precision
             * @default exact
             */
            death_date_precision: string;
            /** Death Date Display */
            death_date_display?: string | null;
            /** Lunar Birth Date */
            lunar_birth_date?: string | null;
            /** Lunar Death Date */
            lunar_death_date?: string | null;
            /** Birth Place */
            birth_place?: string | null;
            /** Death Place */
            death_place?: string | null;
            /** Burial Place */
            burial_place?: string | null;
            /** Tomb Location */
            tomb_location?: string | null;
            /** Residence Place */
            residence_place?: string | null;
            /** Religion */
            religion?: string | null;
            /**
             * Nationality
             * @default VN
             */
            nationality: string;
            /** Occupation */
            occupation?: string | null;
            /** Education Level */
            education_level?: string | null;
            /** Title Rank */
            title_rank?: string | null;
            /** Phone */
            phone?: string | null;
            /** Email */
            email?: string | null;
            /** Biography */
            biography?: string | null;
            /**
             * Avatar Url
             * @description Read-only. avatar_url is server-managed and cannot be set directly. Use PATCH /documents/{document_id}/set-avatar, which publishes the image to the public avatars bucket and stamps the resulting permanent URL.
             */
            avatar_url?: string | null;
            /** Notes */
            notes?: string | null;
        };
        /**
         * PersonResponse
         * @description Response schema for a single person.
         */
        PersonResponse: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Created By Clan Id */
            created_by_clan_id?: string | null;
            /** Full Name */
            full_name: string;
            /** Birth Name */
            birth_name?: string | null;
            /** Courtesy Name */
            courtesy_name?: string | null;
            /** Posthumous Name */
            posthumous_name?: string | null;
            /** Alias Name */
            alias_name?: string | null;
            /** Gender */
            gender: string;
            birth_date?: components["schemas"]["HistoricalDate"];
            death_date?: components["schemas"]["HistoricalDate"];
            /** Birth Place */
            birth_place?: string | null;
            /** Death Place */
            death_place?: string | null;
            /** Burial Place */
            burial_place?: string | null;
            /** Tomb Location */
            tomb_location?: string | null;
            /** Residence Place */
            residence_place?: string | null;
            /** Religion */
            religion?: string | null;
            /** Nationality */
            nationality: string;
            /** Occupation */
            occupation?: string | null;
            /** Education Level */
            education_level?: string | null;
            /** Title Rank */
            title_rank?: string | null;
            /** Phone */
            phone?: string | null;
            /** Email */
            email?: string | null;
            /** Biography */
            biography?: string | null;
            /** Avatar Url */
            avatar_url?: string | null;
            /** Notes */
            notes?: string | null;
            /** Is Deleted */
            is_deleted: boolean;
            /**
             * Created By
             * Format: uuid
             */
            created_by: string;
            /** Updated By */
            updated_by?: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
            /**
             * Version
             * @default 1
             */
            version: number;
        };
        /**
         * PersonSearchResult
         * @description One row of GET /persons/search (a lean, search-specific person projection).
         */
        PersonSearchResult: {
            /** Id */
            id: string;
            /** Full Name */
            full_name: string;
            /** Gender */
            gender: string;
            birth_date: components["schemas"]["HistoricalDate"];
            /** Avatar Url */
            avatar_url?: string | null;
            /** Version */
            version: number;
            /** Generation */
            generation?: number | null;
            /** Membership Role */
            membership_role?: string | null;
            /** Is Founder */
            is_founder: boolean;
        };
        /**
         * PersonUpdateRequest
         * @description Request body for updating a person. All content fields optional.
         */
        PersonUpdateRequest: {
            /** Full Name */
            full_name?: string | null;
            /** Birth Name */
            birth_name?: string | null;
            /** Courtesy Name */
            courtesy_name?: string | null;
            /** Posthumous Name */
            posthumous_name?: string | null;
            /** Alias Name */
            alias_name?: string | null;
            /** Gender */
            gender?: string | null;
            /** Birth Date */
            birth_date?: string | null;
            /** Birth Date Precision */
            birth_date_precision?: string | null;
            /** Birth Date Display */
            birth_date_display?: string | null;
            /** Death Date */
            death_date?: string | null;
            /** Death Date Precision */
            death_date_precision?: string | null;
            /** Death Date Display */
            death_date_display?: string | null;
            /** Lunar Birth Date */
            lunar_birth_date?: string | null;
            /** Lunar Death Date */
            lunar_death_date?: string | null;
            /** Birth Place */
            birth_place?: string | null;
            /** Death Place */
            death_place?: string | null;
            /** Burial Place */
            burial_place?: string | null;
            /** Tomb Location */
            tomb_location?: string | null;
            /** Residence Place */
            residence_place?: string | null;
            /** Religion */
            religion?: string | null;
            /** Nationality */
            nationality?: string | null;
            /** Occupation */
            occupation?: string | null;
            /** Education Level */
            education_level?: string | null;
            /** Title Rank */
            title_rank?: string | null;
            /** Phone */
            phone?: string | null;
            /** Email */
            email?: string | null;
            /** Biography */
            biography?: string | null;
            /**
             * Avatar Url
             * @description Read-only. avatar_url is server-managed and cannot be set directly. Use PATCH /documents/{document_id}/set-avatar, which publishes the image to the public avatars bucket and stamps the resulting permanent URL.
             */
            avatar_url?: string | null;
            /** Notes */
            notes?: string | null;
            /** Expected Version */
            expected_version: number;
        };
        /**
         * PlatformMetricsResponse
         * @description Platform-wide adoption metrics.
         */
        PlatformMetricsResponse: {
            /** Total Clans */
            total_clans: number;
            /** Active Clans */
            active_clans: number;
            /** Suspended Clans */
            suspended_clans: number;
            /** Total Members */
            total_members: number;
            /** Total Users */
            total_users: number;
        };
        /** RefreshRequest */
        RefreshRequest: {
            /** Refresh Token */
            refresh_token: string;
        };
        /** RegisterRequest */
        RegisterRequest: {
            /**
             * Email
             * Format: email
             */
            email: string;
            /** Password */
            password: string;
            /** Full Name */
            full_name: string;
            /**
             * Clan Action
             * @enum {string}
             */
            clan_action: "join" | "create";
            /** Clan Id */
            clan_id?: string | null;
            /** Clan Name */
            clan_name?: string | null;
            /** Clan Slug */
            clan_slug?: string | null;
        };
        /**
         * RegisterResponse
         * @description Onboard-only now (ADR-021): POST /auth/register is non-enumerating and
         *     returns a uniform ``{"message": ...}`` body built by the route, not this
         *     schema. POST /auth/onboard (already-authenticated users attaching to a
         *     clan) still returns this full shape via ``_assign_clan_membership``.
         */
        RegisterResponse: {
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
            /** Email */
            email: string;
            /** Full Name */
            full_name: string;
            /**
             * Clan Id
             * Format: uuid
             */
            clan_id: string;
            /** Is Approved */
            is_approved: boolean;
            /** Message */
            message: string;
        };
        /**
         * RelationshipPathResponse
         * @description Response body for ``GET /tree/path``.
         */
        RelationshipPathResponse: {
            /**
             * Path
             * @default []
             */
            path: components["schemas"]["PathStep"][];
            /** Description */
            description?: string | null;
            /**
             * Found
             * @default false
             */
            found: boolean;
        };
        /** ResendVerificationRequest */
        ResendVerificationRequest: {
            /**
             * Email
             * Format: email
             */
            email: string;
        };
        /**
         * SpouseNode
         * @description Spouse info attached to a tree node.
         */
        SpouseNode: {
            /** Id */
            id: string;
            /** Full Name */
            full_name: string;
            /** Gender */
            gender: string;
            birth_date?: components["schemas"]["HistoricalDate"];
            death_date?: components["schemas"]["HistoricalDate"];
            /** Avatar Url */
            avatar_url?: string | null;
            /** Posthumous Name */
            posthumous_name?: string | null;
            /** Status */
            status: string;
            /** Marriage Date */
            marriage_date?: string | null;
            /** Divorce Date */
            divorce_date?: string | null;
            /** Spouse Order */
            spouse_order?: number | null;
            /** Membership Role */
            membership_role?: string | null;
        };
        /** TimelineEvent */
        TimelineEvent: {
            event_date?: components["schemas"]["HistoricalDate"];
            /** Event Type */
            event_type: string;
            /** Title */
            title: string;
            /** Description */
            description?: string | null;
            /** Related Person Id */
            related_person_id?: string | null;
            /** Related Person Name */
            related_person_name?: string | null;
        };
        /**
         * TokenRefreshResponse
         * @description POST /auth/refresh — a refreshed token pair (no user profile).
         */
        TokenRefreshResponse: {
            /** Access Token */
            access_token: string;
            /** Refresh Token */
            refresh_token: string;
            /** Expires In */
            expires_in: number;
        };
        /**
         * TreeNode
         * @description Recursive tree node representing a person and their descendants.
         */
        TreeNode: {
            /** Id */
            id: string;
            /** Full Name */
            full_name: string;
            /** Birth Name */
            birth_name?: string | null;
            /** Posthumous Name */
            posthumous_name?: string | null;
            /** Gender */
            gender: string;
            birth_date?: components["schemas"]["HistoricalDate"];
            death_date?: components["schemas"]["HistoricalDate"];
            /** Birth Place */
            birth_place?: string | null;
            /** Generation */
            generation?: number | null;
            /** Avatar Url */
            avatar_url?: string | null;
            /** Membership Role */
            membership_role?: string | null;
            /**
             * Is Founder
             * @default false
             */
            is_founder: boolean;
            /**
             * Depth
             * @default 0
             */
            depth: number;
            /** Mother Id */
            mother_id?: string | null;
            /** Mother Spouse Order */
            mother_spouse_order?: number | null;
            /**
             * Pedigree Collapse Ref
             * @default false
             */
            pedigree_collapse_ref: boolean;
            /**
             * Spouses
             * @default []
             */
            spouses: components["schemas"]["SpouseNode"][];
            /**
             * Children
             * @default []
             */
            children: components["schemas"]["TreeNode"][];
        };
        /**
         * TreeNodeDetail
         * @description Detail node with some biographic data.
         */
        TreeNodeDetail: {
            /** Id */
            id: string;
            /** Full Name */
            full_name: string;
            /** Gender */
            gender: string;
            birth_date?: components["schemas"]["HistoricalDate"];
            death_date?: components["schemas"]["HistoricalDate"];
            /** Generation */
            generation?: number | null;
            /** Avatar Url */
            avatar_url?: string | null;
            /**
             * Is Founder
             * @default false
             */
            is_founder: boolean;
            /**
             * Depth
             * @default 0
             */
            depth: number;
            /** Mother Id */
            mother_id?: string | null;
            /** Mother Spouse Order */
            mother_spouse_order?: number | null;
            /**
             * Pedigree Collapse Ref
             * @default false
             */
            pedigree_collapse_ref: boolean;
            /**
             * Spouses
             * @default []
             */
            spouses: components["schemas"]["SpouseNode"][];
            /**
             * Children
             * @default []
             */
            children: components["schemas"]["TreeNodeDetail"][];
            /** Birth Name */
            birth_name?: string | null;
            /** Posthumous Name */
            posthumous_name?: string | null;
            /** Birth Place */
            birth_place?: string | null;
            /** Membership Role */
            membership_role?: string | null;
        };
        /**
         * TreeResponse
         * @description Response containing the assembled family tree.
         */
        TreeResponse: {
            tree: components["schemas"]["TreeNode"];
            /** Total Persons */
            total_persons: number;
            /** Total Generations */
            total_generations: number;
        };
        /** UpcomingEvent */
        UpcomingEvent: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Person Id */
            person_id?: string | null;
            /** Person Name */
            person_name?: string | null;
            /** Person Avatar Url */
            person_avatar_url?: string | null;
            person?: components["schemas"]["EventPersonSummary"] | null;
            /** Event Type */
            event_type: string;
            /** Title */
            title: string;
            event_date?: components["schemas"]["HistoricalDate"];
            /**
             * Next Occurrence
             * Format: date
             */
            next_occurrence: string;
            /** Days Until */
            days_until: number;
            /** Is Lunar Calendar */
            is_lunar_calendar: boolean;
        };
        /**
         * UserActionResponse
         * @description approve/reject/remove acknowledgement: {message, user_id}.
         */
        UserActionResponse: {
            /** Message */
            message: string;
            /** User Id */
            user_id: string;
        };
        /**
         * UserClanMembership
         * @description A single clan membership for the authenticated user.
         */
        UserClanMembership: {
            /**
             * Clan Id
             * Format: uuid
             */
            clan_id: string;
            /** Clan Name */
            clan_name: string;
            /** Clan Slug */
            clan_slug: string;
            /** Role */
            role: string;
            /** Joined At */
            joined_at?: string | null;
        };
        /** UserProfile */
        UserProfile: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Email */
            email: string;
            /** Full Name */
            full_name: string;
            /** Clan Id */
            clan_id?: string | null;
            /** Clan Name */
            clan_name?: string | null;
            /** Role */
            role?: string | null;
            /**
             * Is Approved
             * @default false
             */
            is_approved: boolean;
            /**
             * Has Pending Membership
             * @default false
             */
            has_pending_membership: boolean;
            /** Person Id */
            person_id?: string | null;
            /**
             * Preferred Locale
             * @default vi
             */
            preferred_locale: string;
        };
        /**
         * UserRoleChangeResponse
         * @description PATCH .../role acknowledgement: {message, user_id, role}.
         */
        UserRoleChangeResponse: {
            /** Message */
            message: string;
            /** User Id */
            user_id: string;
            /** Role */
            role: string;
        };
        /** UserUpdateRequest */
        UserUpdateRequest: {
            /** Full Name */
            full_name?: string | null;
            /** Preferred Locale */
            preferred_locale?: string | null;
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    register_api_v1_auth_register_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RegisterRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_MessageData_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    onboard_authenticated_user_api_v1_auth_onboard_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AuthenticatedOnboardingRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_RegisterResponse_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    login_api_v1_auth_login_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LoginRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_LoginResponse_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    logout_api_v1_auth_logout_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_MessageData_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    refresh_token_api_v1_auth_refresh_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RefreshRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_TokenRefreshResponse_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    forgot_password_api_v1_auth_forgot_password_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ForgotPasswordRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_MessageData_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    resend_verification_api_v1_auth_resend_verification_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ResendVerificationRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_MessageData_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    get_me_api_v1_auth_me_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_UserProfile_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    update_me_api_v1_auth_me_patch: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UserUpdateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_MessageData_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    register_fcm_token_api_v1_auth_me_fcm_token_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["FCMTokenRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_MessageData_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    remove_fcm_token_api_v1_auth_me_fcm_token_delete: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["FCMTokenRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_MessageData_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    list_branches_api_v1_branches_get: {
        parameters: {
            query?: {
                fields?: string | null;
            };
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_list_BranchResponse__"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    create_branch_api_v1_branches_post: {
        parameters: {
            query?: never;
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BranchCreateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_BranchResponse_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    get_branch_api_v1_branches__branch_id__get: {
        parameters: {
            query?: never;
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path: {
                branch_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_BranchResponse_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    delete_branch_api_v1_branches__branch_id__delete: {
        parameters: {
            query?: never;
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path: {
                branch_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_MessageData_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    update_branch_api_v1_branches__branch_id__patch: {
        parameters: {
            query?: never;
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path: {
                branch_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BranchUpdateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_BranchResponse_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    get_own_clan_api_v1_clans_me_get: {
        parameters: {
            query?: {
                include?: string | null;
            };
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_ClanResponse_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    update_own_clan_api_v1_clans_me_patch: {
        parameters: {
            query?: never;
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ClanUpdateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_ClanResponse_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    list_clan_users_api_v1_clans_me_users_get: {
        parameters: {
            query?: {
                cursor?: string | null;
                limit?: number;
            };
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PageEnvelope_ClanUserSummary_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    list_pending_users_api_v1_clans_me_users_pending_get: {
        parameters: {
            query?: {
                cursor?: string | null;
                limit?: number;
            };
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PageEnvelope_PendingClanUserSummary_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    approve_user_api_v1_clans_me_users__user_id__approve_post: {
        parameters: {
            query?: never;
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path: {
                user_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_UserActionResponse_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    reject_user_api_v1_clans_me_users__user_id__reject_post: {
        parameters: {
            query?: never;
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path: {
                user_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_UserActionResponse_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    change_user_role_api_v1_clans_me_users__user_id__role_patch: {
        parameters: {
            query: {
                role: string;
            };
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path: {
                user_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_UserRoleChangeResponse_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    remove_user_api_v1_clans_me_users__user_id__delete: {
        parameters: {
            query?: never;
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path: {
                user_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_UserActionResponse_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    designate_founder_api_v1_clans_me_founder_put: {
        parameters: {
            query?: never;
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["FounderDesignationRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_FounderDesignationResponse_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    list_my_clans_api_v1_me_clans_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_list_UserClanMembership__"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    select_clan_api_v1_me_clans__clan_id__select_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                clan_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_ClanSwitchResponse_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    list_persons_api_v1_persons_get: {
        parameters: {
            query?: {
                cursor?: string | null;
                limit?: number;
                generation?: number | null;
                gender?: string | null;
                /** @description Response profile. Use summary for list cards, detail for medium payload, full for all fields. */
                profile?: string;
                /** @description Comma-separated embedded resources. Example: stats */
                include?: string | null;
                /** @description Comma-separated sparse fields. Example: id,full_name,stats */
                fields?: string | null;
            };
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PageEnvelope_PersonResponse_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    create_person_api_v1_persons_post: {
        parameters: {
            query?: never;
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PersonCreateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_PersonResponse_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    search_persons_api_v1_persons_search_get: {
        parameters: {
            query: {
                q: string;
                limit?: number;
            };
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_list_PersonSearchResult__"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    batch_get_persons_api_v1_persons_batch_post: {
        parameters: {
            query?: never;
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PersonBatchGetRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PersonBatchEnvelope"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    get_person_api_v1_persons__person_id__get: {
        parameters: {
            query?: {
                /** @description Comma-separated embedded resources. Supported: marriages,parent_child,timeline,documents */
                include?: string | null;
                /** @description Comma-separated sparse fields. Example: id,full_name,gender,marriages */
                fields?: string | null;
                /** @description Response profile. summary/detail/full */
                profile?: string;
            };
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path: {
                person_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_PersonResponse_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    delete_person_api_v1_persons__person_id__delete: {
        parameters: {
            query?: never;
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path: {
                person_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_MessageData_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    update_person_api_v1_persons__person_id__patch: {
        parameters: {
            query?: never;
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path: {
                person_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PersonUpdateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_PersonResponse_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    restore_person_api_v1_persons__person_id__restore_post: {
        parameters: {
            query?: never;
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path: {
                person_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_PersonResponse_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    submit_identity_claim_api_v1_persons__person_id__claim_post: {
        parameters: {
            query?: never;
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path: {
                person_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["IdentityClaimSubmit"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_IdentityClaimResponse_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    person_marriages_api_v1_persons__person_id__marriages_get: {
        parameters: {
            query?: {
                fields?: string | null;
            };
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path: {
                person_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_list_MarriageResponse__"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    person_parent_child_api_v1_persons__person_id__parent_child_get: {
        parameters: {
            query?: {
                fields?: string | null;
            };
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path: {
                person_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_list_ParentChildResponse__"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    person_documents_api_v1_persons__person_id__documents_get: {
        parameters: {
            query?: {
                fields?: string | null;
            };
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path: {
                person_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_list_DocumentSummary__"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    person_events_api_v1_persons__person_id__events_get: {
        parameters: {
            query?: {
                fields?: string | null;
            };
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path: {
                person_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_list_EventResponse__"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    person_timeline_api_v1_persons__person_id__timeline_get: {
        parameters: {
            query?: never;
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path: {
                person_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_list_TimelineEvent__"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    create_marriage_api_v1_relationships_marriages_post: {
        parameters: {
            query?: never;
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MarriageCreateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_MarriageResponse_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    get_marriage_api_v1_relationships_marriages__marriage_id__get: {
        parameters: {
            query?: never;
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path: {
                marriage_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_MarriageResponse_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    delete_marriage_api_v1_relationships_marriages__marriage_id__delete: {
        parameters: {
            query?: never;
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path: {
                marriage_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_MessageData_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    update_marriage_api_v1_relationships_marriages__marriage_id__patch: {
        parameters: {
            query?: never;
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path: {
                marriage_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MarriageUpdateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_MarriageResponse_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    create_parent_child_api_v1_relationships_parent_child_post: {
        parameters: {
            query?: never;
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ParentChildCreateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_ParentChildResponse_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    get_parent_child_api_v1_relationships_parent_child__link_id__get: {
        parameters: {
            query?: never;
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path: {
                link_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_ParentChildResponse_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    delete_parent_child_api_v1_relationships_parent_child__link_id__delete: {
        parameters: {
            query?: never;
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path: {
                link_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_MessageData_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    update_parent_child_api_v1_relationships_parent_child__link_id__patch: {
        parameters: {
            query?: never;
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path: {
                link_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ParentChildUpdateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_ParentChildResponse_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    list_documents_api_v1_documents_get: {
        parameters: {
            query?: {
                person_id?: string | null;
                document_type?: string | null;
                cursor?: string | null;
                limit?: number;
                fields?: string | null;
            };
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PageEnvelope_DocumentResponse_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    upload_document_api_v1_documents_post: {
        parameters: {
            query?: never;
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "multipart/form-data": components["schemas"]["Body_upload_document_api_v1_documents_post"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_DocumentResponse_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    get_document_api_v1_documents__document_id__get: {
        parameters: {
            query?: never;
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path: {
                document_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_DocumentResponse_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    delete_document_api_v1_documents__document_id__delete: {
        parameters: {
            query?: never;
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path: {
                document_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_MessageData_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    restore_document_api_v1_documents__document_id__restore_post: {
        parameters: {
            query?: never;
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path: {
                document_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_DocumentResponse_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    set_document_as_avatar_api_v1_documents__document_id__set_avatar_patch: {
        parameters: {
            query?: never;
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path: {
                document_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_MessageData_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    list_events_api_v1_events_get: {
        parameters: {
            query?: {
                person_id?: string | null;
                event_type?: string | null;
                cursor?: string | null;
                limit?: number;
                fields?: string | null;
            };
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PageEnvelope_EventResponse_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    create_event_api_v1_events_post: {
        parameters: {
            query?: never;
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["EventCreateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_EventResponse_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    get_upcoming_events_api_v1_events_upcoming_get: {
        parameters: {
            query?: {
                days?: number;
                include?: string | null;
            };
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_list_UpcomingEvent__"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    get_event_api_v1_events__event_id__get: {
        parameters: {
            query?: {
                include?: string | null;
                fields?: string | null;
            };
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path: {
                event_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_EventResponse_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    delete_event_api_v1_events__event_id__delete: {
        parameters: {
            query?: never;
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path: {
                event_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_MessageData_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    update_event_api_v1_events__event_id__patch: {
        parameters: {
            query?: never;
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path: {
                event_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["EventUpdateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_EventResponse_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    restore_event_api_v1_events__event_id__restore_post: {
        parameters: {
            query?: never;
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path: {
                event_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_EventResponse_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    get_full_tree_api_v1_tree_get: {
        parameters: {
            query?: {
                root_person_id?: string | null;
                max_generations?: number;
                profile?: string;
            };
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_TreeResponse_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    get_subtree_api_v1_tree_subtree__person_id__get: {
        parameters: {
            query?: {
                max_generations?: number;
                profile?: string;
            };
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path: {
                person_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_TreeResponse_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    get_ancestors_api_v1_tree_ancestors__person_id__get: {
        parameters: {
            query?: {
                profile?: string;
            };
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path: {
                person_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_list_TreeNodeDetail__"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    get_focus_api_v1_tree_focus__person_id__get: {
        parameters: {
            query?: {
                descendants?: number;
                ancestors?: number;
            };
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path: {
                person_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_FocusView_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    find_path_api_v1_tree_path_get: {
        parameters: {
            query: {
                from_id: string;
                to_id: string;
            };
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_RelationshipPathResponse_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    export_clan_api_v1_exports_clan_get: {
        parameters: {
            query?: {
                format?: string;
            };
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    list_change_requests_api_v1_change_requests_get: {
        parameters: {
            query?: {
                /** @description Filter by review status. */
                status?: string | null;
                cursor?: string | null;
                limit?: number;
            };
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PageEnvelope_ChangeRequestResponse_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    submit_change_request_api_v1_change_requests_post: {
        parameters: {
            query?: never;
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ChangeRequestCreateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_ChangeRequestResponse_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    get_change_request_api_v1_change_requests__change_request_id__get: {
        parameters: {
            query?: never;
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path: {
                change_request_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_ChangeRequestResponse_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    approve_change_request_api_v1_change_requests__change_request_id__approve_post: {
        parameters: {
            query?: never;
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path: {
                change_request_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ChangeRequestReviewRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_ChangeRequestResponse_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    reject_change_request_api_v1_change_requests__change_request_id__reject_post: {
        parameters: {
            query?: never;
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path: {
                change_request_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ChangeRequestReviewRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_ChangeRequestResponse_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    list_my_claims_api_v1_claims_get: {
        parameters: {
            query?: {
                /** @description Filter by status (e.g., PENDING) */
                status?: string | null;
                cursor?: string | null;
                limit?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PageEnvelope_IdentityClaimResponse_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    cancel_claim_api_v1_claims__claim_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                claim_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    list_clan_claims_api_v1_clans__clan_id__claims_get: {
        parameters: {
            query?: {
                /** @description Filter by status (e.g., PENDING) */
                status?: string | null;
                cursor?: string | null;
                limit?: number;
                fields?: string | null;
            };
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path: {
                clan_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PageEnvelope_IdentityClaimResponse_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    approve_claim_api_v1_clans__clan_id__claims__claim_id__approve_post: {
        parameters: {
            query?: never;
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path: {
                clan_id: string;
                claim_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["IdentityClaimReview"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_IdentityClaimResponse_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    reject_claim_api_v1_clans__clan_id__claims__claim_id__reject_post: {
        parameters: {
            query?: never;
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path: {
                clan_id: string;
                claim_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["IdentityClaimReview"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_IdentityClaimResponse_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    unlink_identity_api_v1_clans__clan_id__claims_members__user_id__unlink_post: {
        parameters: {
            query?: never;
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path: {
                clan_id: string;
                user_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["IdentityClaimUnlink"];
            };
        };
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    prelink_identity_api_v1_clans__clan_id__claims_members__user_id__prelink_post: {
        parameters: {
            query?: never;
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path: {
                clan_id: string;
                user_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["IdentityClaimPrelink"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_IdentityClaimResponse_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    list_invitations_api_v1_clans__clan_id__invitations_get: {
        parameters: {
            query?: never;
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path: {
                clan_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_list_InvitationResponse__"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    create_invitation_api_v1_clans__clan_id__invitations_post: {
        parameters: {
            query?: never;
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path: {
                clan_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["InvitationCreateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_InvitationCreatedResponse_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    revoke_invitation_api_v1_clans__clan_id__invitations__invitation_id__delete: {
        parameters: {
            query?: never;
            header?: {
                "x-current-clan-id"?: string | null;
            };
            path: {
                clan_id: string;
                invitation_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    accept_invitation_api_v1_invitations__token__accept_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                token: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_InvitationAcceptedResponse_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    list_all_clans_api_v1_platform_clans_get: {
        parameters: {
            query?: {
                cursor?: string | null;
                limit?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PageEnvelope_ClanSummaryResponse_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    get_clan_detail_api_v1_platform_clans__clan_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                clan_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_ClanDetailResponse_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    suspend_clan_api_v1_platform_clans__clan_id__suspend_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                clan_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_ClanStatusResponse_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    reactivate_clan_api_v1_platform_clans__clan_id__reactivate_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                clan_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_ClanStatusResponse_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    platform_metrics_api_v1_platform_metrics_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Envelope_PlatformMetricsResponse_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    audit_log_api_v1_platform_audit_log_get: {
        parameters: {
            query?: {
                clan_id?: string | null;
                action?: string | null;
                cursor?: string | null;
                limit?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PageEnvelope_AuditLogEntryResponse_"];
                };
            };
            /** @description Missing/invalid token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Insufficient role / clan mismatch */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not found (incl. cross-clan reads) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict (stale_write, duplicates) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    health_health_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
        };
    };
}
