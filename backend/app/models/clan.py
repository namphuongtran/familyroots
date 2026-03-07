"""Clan ORM model (public schema) — uses TimestampMixin only, NOT ClanScopedMixin."""

# TODO: implement in Prompt 2
#
# class Clan(TimestampMixin, Base):
#     __tablename__ = "clans"
#     id, name, slug, is_active
#     created_at, updated_at inherited from TimestampMixin
#     NOTE: No clan_id column — this IS the clans table
