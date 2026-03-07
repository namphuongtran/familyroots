-- ============================================================
-- 004_fcm_tokens.sql
-- User FCM device tokens for push notifications.
-- One row per device per user. Tokens are cleaned up when
-- Firebase reports them as unregistered.
-- ============================================================

CREATE TABLE IF NOT EXISTS public.user_fcm_tokens (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID NOT NULL,       -- references auth.users(id) in Supabase
    fcm_token  TEXT NOT NULL,
    device_os  VARCHAR(20),         -- 'ios', 'android', 'web'
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_user_fcm_token UNIQUE (user_id, fcm_token)
);

-- Index for looking up tokens by user
CREATE INDEX IF NOT EXISTS idx_user_fcm_tokens_user_id
    ON public.user_fcm_tokens(user_id);

-- RLS: users can only manage their own tokens
ALTER TABLE public.user_fcm_tokens ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users manage own FCM tokens"
    ON public.user_fcm_tokens
    FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- Service role bypass for notification service
CREATE POLICY "Service role full access to FCM tokens"
    ON public.user_fcm_tokens
    FOR ALL
    USING (auth.role() = 'service_role');
