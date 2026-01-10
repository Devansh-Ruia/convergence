from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
from bson import ObjectId


class GitHubContext(BaseModel):
    """GitHub PR context."""
    repo_owner: str
    repo_name: str
    pr_number: int
    pr_title: str
    pr_url: str
    head_sha: str
    author: str


class FileChange(BaseModel):
    """A file changed in the PR."""
    path: str
    status: str  # modified, added, deleted, renamed
    patch: str = ""  # The diff content
    additions: int = 0
    deletions: int = 0


class FinalReview(BaseModel):
    """Final review posted to GitHub."""
    summary: str
    findings_count: int
    critical_count: int
    posted_at: datetime
    github_review_id: Optional[int] = None


class ReviewSession(BaseModel):
    """A PR review session."""
    github: GitHubContext
    files: list[FileChange] = []
    status: str = "pending"  # pending, analyzing, converging, complete, failed
    agents_dispatched: list[str] = []
    agents_completed: list[str] = []
    final_review: Optional[FinalReview] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    error: Optional[str] = None

    class Config:
        arbitrary_types_allowed = True