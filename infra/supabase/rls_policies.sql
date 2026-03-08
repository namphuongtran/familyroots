-- =============================================================
-- RLS POLICIES — Single Schema, clan_id isolation
-- All policies use Supabase Auth JWT claims
-- =============================================================

-- Helper function: get authenticated user's clan_id from user_clan_roles
-- NOTE: This returns the first approved clan. For multi-clan users, the
-- application layer handles clan selection via X-Current-Clan-Id header.
-- RLS uses this as a fallback; application-level filtering is the primary
-- isolation mechanism for multi-clan users.
CREATE OR REPLACE FUNCTION auth.user_clan_id()
RETURNS UUID AS $$
  SELECT clan_id FROM public.user_clan_roles
  WHERE user_id = auth.uid()
  AND is_approved = true
  LIMIT 1;
$$ LANGUAGE sql SECURITY DEFINER STABLE;

-- Helper function: get authenticated user's clan role
CREATE OR REPLACE FUNCTION auth.user_clan_role()
RETURNS TEXT AS $$
  SELECT role FROM public.user_clan_roles
  WHERE user_id = auth.uid()
  AND is_approved = true
  LIMIT 1;
$$ LANGUAGE sql SECURITY DEFINER STABLE;

-- Helper function: check if user belongs to a specific clan
CREATE OR REPLACE FUNCTION auth.user_belongs_to_clan(target_clan_id UUID)
RETURNS BOOLEAN AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.user_clan_roles
    WHERE user_id = auth.uid()
    AND clan_id = target_clan_id
    AND is_approved = true
  );
$$ LANGUAGE sql SECURITY DEFINER STABLE;

-- ── PERSONS (global — readable by any authenticated clan member) ──
-- Persons are global entities. Any authenticated user can read persons
-- that belong to at least one of their clans (via clan_memberships).
-- Write access is gated by the application layer + approval workflow.
ALTER TABLE public.persons ENABLE ROW LEVEL SECURITY;

CREATE POLICY "persons_select_via_clan_membership" ON public.persons
  FOR SELECT USING (
    EXISTS (
      SELECT 1 FROM public.clan_memberships cm
      JOIN public.user_clan_roles ucr ON ucr.clan_id = cm.clan_id
      WHERE cm.person_id = persons.id
        AND ucr.user_id = auth.uid()
        AND ucr.is_approved = true
    )
  );

CREATE POLICY "persons_insert_editor_above" ON public.persons
  FOR INSERT WITH CHECK (
    auth.user_clan_role() IN ('admin', 'editor')
  );

CREATE POLICY "persons_update_editor_above" ON public.persons
  FOR UPDATE USING (
    auth.user_clan_role() IN ('admin', 'editor')
  );

CREATE POLICY "persons_delete_admin_only" ON public.persons
  FOR DELETE USING (
    auth.user_clan_role() = 'admin'
  );

-- ── CLAN_MEMBERSHIPS ─────────────────────────────────────────
ALTER TABLE public.clan_memberships ENABLE ROW LEVEL SECURITY;

CREATE POLICY "clan_memberships_select_own_clan" ON public.clan_memberships
  FOR SELECT USING (auth.user_belongs_to_clan(clan_id));

CREATE POLICY "clan_memberships_write_editor_above" ON public.clan_memberships
  FOR ALL USING (
    auth.user_belongs_to_clan(clan_id)
    AND auth.user_clan_role() IN ('admin', 'editor')
  );

-- ── BRANCHES ─────────────────────────────────────────────────
ALTER TABLE public.branches ENABLE ROW LEVEL SECURITY;

CREATE POLICY "branches_select_own_clan" ON public.branches
  FOR SELECT USING (auth.user_belongs_to_clan(clan_id));

CREATE POLICY "branches_write_editor_above" ON public.branches
  FOR ALL USING (
    auth.user_belongs_to_clan(clan_id)
    AND auth.user_clan_role() IN ('admin', 'editor')
  );

-- ── MARRIAGES (global edges — write-gated by created_by_clan_id) ──
ALTER TABLE public.marriages ENABLE ROW LEVEL SECURITY;

CREATE POLICY "marriages_select_via_clan" ON public.marriages
  FOR SELECT USING (auth.user_belongs_to_clan(created_by_clan_id));

CREATE POLICY "marriages_write_editor_above" ON public.marriages
  FOR ALL USING (
    auth.user_belongs_to_clan(created_by_clan_id)
    AND auth.user_clan_role() IN ('admin', 'editor')
  );

-- ── PARENT_CHILD (global edges — write-gated by created_by_clan_id) ──
ALTER TABLE public.parent_child ENABLE ROW LEVEL SECURITY;

CREATE POLICY "parent_child_select_via_clan" ON public.parent_child
  FOR SELECT USING (auth.user_belongs_to_clan(created_by_clan_id));

CREATE POLICY "parent_child_write_editor_above" ON public.parent_child
  FOR ALL USING (
    auth.user_belongs_to_clan(created_by_clan_id)
    AND auth.user_clan_role() IN ('admin', 'editor')
  );

-- ── DOCUMENTS ────────────────────────────────────────────────
ALTER TABLE public.documents ENABLE ROW LEVEL SECURITY;

CREATE POLICY "documents_select_own_clan" ON public.documents
  FOR SELECT USING (auth.user_belongs_to_clan(clan_id));

CREATE POLICY "documents_write_editor_above" ON public.documents
  FOR ALL USING (
    auth.user_belongs_to_clan(clan_id)
    AND auth.user_clan_role() IN ('admin', 'editor')
  );

-- ── EVENTS ───────────────────────────────────────────────────
ALTER TABLE public.events ENABLE ROW LEVEL SECURITY;

CREATE POLICY "events_select_own_clan" ON public.events
  FOR SELECT USING (auth.user_belongs_to_clan(clan_id));

CREATE POLICY "events_write_editor_above" ON public.events
  FOR ALL USING (
    auth.user_belongs_to_clan(clan_id)
    AND auth.user_clan_role() IN ('admin', 'editor')
  );

-- ── CLANS (read-only for clan users) ─────────────────────────
ALTER TABLE public.clans ENABLE ROW LEVEL SECURITY;

CREATE POLICY "clans_select_own" ON public.clans
  FOR SELECT USING (auth.user_belongs_to_clan(id));

-- Only super_admin (via service role key) can INSERT/UPDATE/DELETE clans.
-- Application uses service role key for clan management — bypasses RLS.

-- ── USER_CLAN_ROLES ──────────────────────────────────────────
ALTER TABLE public.user_clan_roles ENABLE ROW LEVEL SECURITY;

CREATE POLICY "user_clan_roles_select_own_clan" ON public.user_clan_roles
  FOR SELECT USING (auth.user_belongs_to_clan(clan_id));

-- Only admin can manage roles within their clan
CREATE POLICY "user_clan_roles_manage_admin_only" ON public.user_clan_roles
  FOR ALL USING (
    auth.user_belongs_to_clan(clan_id)
    AND auth.user_clan_role() = 'admin'
  );

-- ── STORAGE: clan path isolation ─────────────────────────────
-- Users can only access files under their clan_id path in the shared bucket.
-- Bucket structure: family-roots-files/clans/{clan_id}/...
CREATE POLICY "storage_clan_isolation"
ON storage.objects FOR ALL
USING (
  bucket_id = 'family-roots-files'
  AND (storage.foldername(name))[1] = 'clans'
  AND auth.user_belongs_to_clan((storage.foldername(name))[2]::uuid)
);
