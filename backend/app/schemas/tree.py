"""Pydantic v2 schemas for family tree API."""

from datetime import date

from pydantic import BaseModel, Field

from app.schemas.historical_date import HistoricalDate


class SpouseNode(BaseModel):
    """Spouse info attached to a tree node."""

    id: str
    full_name: str
    gender: str
    birth_date: HistoricalDate = Field(default_factory=HistoricalDate)
    death_date: HistoricalDate = Field(default_factory=HistoricalDate)
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
    birth_date: HistoricalDate = Field(default_factory=HistoricalDate)
    death_date: HistoricalDate = Field(default_factory=HistoricalDate)
    birth_place: str | None = None
    generation: int | None = None
    avatar_url: str | None = None
    membership_role: str | None = None  # blood, spouse, adopted
    is_founder: bool = False
    depth: int = 0
    mother_id: str | None = None
    mother_spouse_order: int | None = None
    spouses: list[SpouseNode] = []
    children: list[TreeNode] = []  # recursive

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


class TreeNodeSummary(BaseModel):
    """Minimal node representation for the tree structure."""

    id: str
    full_name: str
    gender: str
    birth_date: HistoricalDate = Field(default_factory=HistoricalDate)
    death_date: HistoricalDate = Field(default_factory=HistoricalDate)
    generation: int | None = None
    avatar_url: str | None = None
    is_founder: bool = False
    depth: int = 0
    mother_id: str | None = None
    mother_spouse_order: int | None = None
    spouses: list[SpouseNode] = []
    children: list[TreeNodeSummary] = []

    model_config = {"from_attributes": True}


TreeNodeSummary.model_rebuild()


class TreeNodeDetail(TreeNodeSummary):
    """Detail node with some biographic data."""

    birth_name: str | None = None
    posthumous_name: str | None = None
    birth_place: str | None = None
    membership_role: str | None = None  # blood, spouse, adopted
    children: list[TreeNodeDetail] = []  # type: ignore[assignment]

    model_config = {"from_attributes": True}


TreeNodeDetail.model_rebuild()


class FocusAncestor(BaseModel):
    """One breadcrumb ancestor above the focus person (thủy-tổ-first)."""

    id: str
    full_name: str
    gender: str
    birth_date: HistoricalDate = Field(default_factory=HistoricalDate)
    death_date: HistoricalDate = Field(default_factory=HistoricalDate)
    avatar_url: str | None = None
    generation: int | None = None
    is_founder: bool = False


class FocusTreeNode(BaseModel):
    """A node in the focus subtree, with focus-only enrichment fields."""

    id: str
    full_name: str
    gender: str
    birth_name: str | None = None
    posthumous_name: str | None = None
    birth_date: HistoricalDate = Field(default_factory=HistoricalDate)
    death_date: HistoricalDate = Field(default_factory=HistoricalDate)
    birth_place: str | None = None
    avatar_url: str | None = None
    membership_role: str | None = None
    is_founder: bool = False
    generation: int | None = None
    depth: int = 0
    branch_id: str | None = None
    branch_name: str | None = None
    branch_order: int | None = None
    has_more_descendants: bool = False
    mother_id: str | None = None
    mother_spouse_order: int | None = None
    spouses: list[SpouseNode] = []
    children: list[FocusTreeNode] = []

    model_config = {"from_attributes": True}


FocusTreeNode.model_rebuild()


class FocusView(BaseModel):
    """Consolidated payload for the interactive focus-tree screen."""

    focus_person_id: str
    generation_of_focus: int | None = None
    ancestors: list[FocusAncestor] = []
    focus_subtree: FocusTreeNode | None = None

    model_config = {"from_attributes": True}
