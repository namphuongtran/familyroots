"""Pydantic v2 schemas for family tree API."""

from datetime import date

from pydantic import BaseModel, Field


class SpouseNode(BaseModel):
    """Spouse info attached to a tree node."""

    id: str
    full_name: str
    gender: str
    birth_date: date | None = None
    death_date: date | None = None
    avatar_url: str | None = None
    relation_subtype: str   # 'married','divorced','widowed','partner'
    start_date: date | None = None
    end_date: date | None = None
    is_primary: bool


class TreeNode(BaseModel):
    """Recursive tree node representing a family member and their descendants."""

    id: str
    full_name: str
    birth_name: str | None = None
    gender: str
    birth_date: date | None = None
    birth_date_approx: bool = False
    death_date: date | None = None
    death_date_approx: bool = False
    birth_place: str | None = None
    generation: int | None = None
    avatar_url: str | None = None
    is_clan_member: bool = True
    is_clan_founder: bool = False
    depth: int = 0
    spouses: list[SpouseNode] = []
    children: list[TreeNode] = []  # recursive

    model_config = {"from_attributes": True}


TreeNode.model_rebuild()  # required for self-referential models


class TreeRequest(BaseModel):
    """Request params for fetching a family tree."""

    root_member_id: str | None = None
    # If None, uses clan founder as root
    max_generations: int = Field(default=10, ge=1, le=10)


class TreeResponse(BaseModel):
    """Response containing the assembled family tree."""

    tree: TreeNode
    total_members: int
    total_generations: int
