"""Data models for swarm orchestration."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any


class SwarmTopology(str, Enum):
    HIERARCHICAL = "hierarchical"
    MESH = "mesh"
    CONSENSUS = "consensus"


class AgentPhase(str, Enum):
    IDLE = "idle"
    SPAWNING = "spawning"
    PLANNING = "planning"
    EXECUTING = "executing"
    REVIEWING = "reviewing"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    TERMINATED = "terminated"


class AgentType(str, Enum):
    CODER = "coder"
    TESTER = "tester"
    REVIEWER = "reviewer"
    ARCHITECT = "architect"
    SECURITY = "security"
    RESEARCH = "research"
    WRITER = "writer"
    CUSTOM = "custom"


@dataclass
class TokenUsage:
    """Token consumption for an agent."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def add(self, prompt: int = 0, completion: int = 0) -> None:
        self.prompt_tokens += prompt
        self.completion_tokens += completion
        self.total_tokens = self.prompt_tokens + self.completion_tokens


@dataclass
class ContextWindow:
    """Context window stats for an agent."""

    used_tokens: int = 0
    max_tokens: int = 32768  # default 32k
    usage_percent: float = field(init=False)

    def __post_init__(self) -> None:
        self.usage_percent = (
            (self.used_tokens / self.max_tokens) * 100 if self.max_tokens > 0 else 0.0
        )

    def update(self, used: int) -> None:
        self.used_tokens = used
        self.usage_percent = (
            (self.used_tokens / self.max_tokens) * 100 if self.max_tokens > 0 else 0.0
        )


@dataclass
class AgentConfig:
    """Configuration for spawning an agent."""

    type: str
    name: str
    model: str = "inherit"
    domain: str = ""
    task: str = ""
    system_prompt: str = ""
    max_tokens: int = 32768


@dataclass
class TaskInfo:
    """Information about an assigned task."""

    task_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    description: str = ""
    status: str = "pending"  # pending, in_progress, completed, failed
    progress_percent: float = 0.0
    result: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None


@dataclass
class AgentStatus:
    """Live status of a single agent."""

    agent_id: str
    name: str
    agent_type: str
    model: str          # Ruflo alias or explicit model name requested
    phase: AgentPhase
    resolved_model: str = ""  # Actual Kimi model name (e.g. moonshot-v1-32k)
    task: TaskInfo | None = None
    tokens: TokenUsage = field(default_factory=TokenUsage)
    context: ContextWindow = field(default_factory=ContextWindow)
    messages_count: int = 0
    spawn_time: datetime = field(default_factory=datetime.now)
    last_active: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def uptime_seconds(self) -> float:
        return (datetime.now() - self.spawn_time).total_seconds()


@dataclass
class SwarmStatus:
    """Overall swarm status."""

    swarm_id: str
    topology: SwarmTopology
    max_agents: int
    agents: list[AgentStatus] = field(default_factory=list)
    main_context: ContextWindow = field(default_factory=lambda: ContextWindow(used_tokens=0, max_tokens=128000))
    created_at: datetime = field(default_factory=datetime.now)
    is_active: bool = True

    @property
    def active_agents(self) -> int:
        return sum(
            1 for a in self.agents if a.phase not in (AgentPhase.TERMINATED, AgentPhase.FAILED)
        )

    @property
    def completed_tasks(self) -> int:
        return sum(
            1 for a in self.agents if a.task and a.task.status == "completed"
        )

    @property
    def total_tasks(self) -> int:
        return sum(1 for a in self.agents if a.task is not None)

    @property
    def overall_progress(self) -> float:
        if not self.agents:
            return 0.0
        return sum(
            a.task.progress_percent for a in self.agents if a.task
        ) / max(len([a for a in self.agents if a.task]), 1)
