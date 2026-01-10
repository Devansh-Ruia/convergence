from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
from bson import ObjectId


class Finding(BaseModel):
    """A single code review finding."""
    id: str
    file_path: str
    line_start: int
    line_end: int
    severity: int = Field(ge=1, le=5)  # 1-5
    category: str
    title: str
    description: str
    suggestion: str = ""
    code_snippet: str = ""


class AgentFindings(BaseModel):
    """Findings from a single agent."""
    session_id: str
    agent_type: str  # security, performance, testing
    findings: list[Finding] = []
    model_used: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)