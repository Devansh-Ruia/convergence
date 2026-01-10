from app.agents.security import SecurityAgent
from app.agents.performance import PerformanceAgent
from app.agents.testing import TestingAgent
from app.agents.runner import run_agent, run_all_agents

AGENTS = {
    "security": SecurityAgent,
    "performance": PerformanceAgent,
    "testing": TestingAgent
}

__all__ = [
    "SecurityAgent",
    "PerformanceAgent", 
    "TestingAgent",
    "AGENTS",
    "run_agent",
    "run_all_agents"
]