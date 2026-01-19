from abc import ABC, abstractmethod
from app.models.session import FileChange


class BaseAgent(ABC):
    """Base class for all review agents."""
    
    agent_type: str = "base"
    
    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """Return the system prompt for this agent."""
        pass
    
    def build_user_prompt(
        self,
        repo_owner: str,
        repo_name: str,
        pr_title: str,
        files: list[FileChange]
    ) -> str:
        """Build the user prompt with PR context."""
        
        files_content = []
        for f in files:
            if f.patch:
                files_content.append(f"""### File: {f.path}
Status: {f.status} (+{f.additions}/-{f.deletions})
```diff
{f.patch}
```
""")
        
        files_str = "\n".join(files_content) if files_content else "No file changes to review."
        
        return f"""Review this pull request for {self.agent_type} issues.

**Repository:** {repo_owner}/{repo_name}
**PR Title:** {pr_title}

**Files Changed:**

{files_str}

Analyze each file carefully. Return your findings as a JSON object with this exact structure:
{{
  "findings": [
    {{
      "id": "{self.agent_type[:3]}-001",
      "file_path": "path/to/file.py",
      "line_start": 10,
      "line_end": 10,
      "severity": 3,
      "category": "category-name",
      "title": "Short descriptive title",
      "description": "Detailed explanation of the issue",
      "suggestion": "How to fix this issue",
      "code_snippet": "the problematic code",
      "confidence": 0.95,
      "reasoning": "Why you are flagging this issue"
    }}
  ],
  "summary": "1-2 sentence overall assessment"
}}

Rules:
- Only report genuine {self.agent_type} concerns, not style issues
- Be specific with line numbers from the diff
- severity: 1=info, 2=low, 3=medium, 4=high, 5=critical
- Return empty findings array if no issues found
- Return ONLY valid JSON, no markdown code blocks"""

    def get_output_schema(self) -> dict:
        """JSON schema for expected output."""
        return {
            "type": "object",
            "properties": {
                "findings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "file_path": {"type": "string"},
                            "line_start": {"type": "integer"},
                            "line_end": {"type": "integer"},
                            "severity": {"type": "integer", "minimum": 1, "maximum": 5},
                            "category": {"type": "string"},
                            "title": {"type": "string"},
                            "description": {"type": "string"},
                            "suggestion": {"type": "string"},
                            "code_snippet": {"type": "string"},
                            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                            "reasoning": {"type": "string"}
                        },
                        "required": ["id", "file_path", "line_start", "severity", "category", "title", "description"]
                    }
                },
                "summary": {"type": "string"}
            },
            "required": ["findings", "summary"]
        }
