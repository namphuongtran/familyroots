-- Row Level Security (RLS) policies for multi-tenant isolation
-- TODO: implement in Prompt 2

-- Example: Restrict members table to authenticated users within their clan
-- ALTER TABLE clan_{slug}.members ENABLE ROW LEVEL SECURITY;
-- CREATE POLICY "members_clan_isolation" ON clan_{slug}.members
--   USING (clan_id = current_setting('app.current_clan_id')::uuid);
