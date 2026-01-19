from app.agents.security import SecurityAgent
from app.agents.performance import PerformanceAgent
from app.agents.testing import TestingAgent
from app.agents.architecture import ArchitectureAgent
from app.agents.documentation import DocumentationAgent
from app.agents.runner import run_agent, run_all_agents

AGENTS = {
    "security": SecurityAgent,
    "performance": PerformanceAgent,
    "testing": TestingAgent,
    "architecture": ArchitectureAgent,
    "documentation": DocumentationAgent
}

__all__ = [
    "SecurityAgent",
    "PerformanceAgent", 
    "TestingAgent",
    "ArchitectureAgent",
    "DocumentationAgent",
    "AGENTS",
    "run_agent",
    "run_all_agents"
]