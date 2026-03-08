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
    posthumous_name: str | None = None
    status: str  # 'married','divorced','widowed','separated'
    marriage_date: date | None = None
    divorce_date: date | None = None
    spouse_order: int | None = None
    membership_role: str | None = None  # blood, spouse, adopted


class TreeNode(BaseModel):
    """Recursive tree node representing a person and their descendants."""

    id: str
    full_name: str
    birth_name: str | None = None
    posthumous_name: str | None = None
    gender: str
    birth_date: date | None = None
    birth_date_approx: bool = False
    death_date: date | None = None
    death_date_approx: bool = False
    birth_place: str | None = None
    generation: int | None = None
    avatar_url: str | None = None
    membership_role: str | None = None  # blood, spouse, adopted
    is_founder: bool = False
    depth: int = 0
    spouses: list[SpouseNode] = []
    children: list["TreeNode"] = []  # recursive

    model_config = {"from_attributes": True}


TreeNode.model_rebuild()  # required for self-referential models


class TreeRequest(BaseModel):
    """Request params for fetching a family tree."""

    root_person_id: str | None = None
    # If None, uses clan founder as root
    max_generations: int = Field(default=10, ge=1, le=50)


class TreeResponse(BaseModel):
    """Response containing the assembled family tree."""

    tree: TreeNode
    total_persons: int
    total_generations: int
