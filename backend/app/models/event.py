"""Event ORM model — uses ClanScopedMixin for clan_id isolation."""

# TODO: implement in Prompt 2
#
# class Event(ClanScopedMixin, Base):
#     __tablename__ = "events"
#     id, title, description, event_date, event_type
#     clan_id inherited from ClanScopedMixin
#     created_at, updated_at inherited from TimestampMixin (via ClanScopedMixin)
