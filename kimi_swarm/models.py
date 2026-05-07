"""Data models for swarm orchestration."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TokenUsage:
        return cls(**data)


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

    def to_dict(self) -> dict[str, Any]:
        return {"used_tokens": self.used_tokens, "max_tokens": self.max_tokens}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ContextWindow:
        cw = cls(used_tokens=data.get("used_tokens", 0), max_tokens=data.get("max_tokens", 32768))
        return cw


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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentConfig:
        return cls(**data)


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

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "description": self.description,
            "status": self.status,
            "progress_percent": self.progress_percent,
            "result": self.result,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskInfo:
        completed_at = None
        if data.get("completed_at"):
            completed_at = datetime.fromisoformat(data["completed_at"])
        return cls(
            task_id=data.get("task_id", str(uuid.uuid4())[:8]),
            description=data.get("description", ""),
            status=data.get("status", "pending"),
            progress_percent=data.get("progress_percent", 0.0),
            result=data.get("result", ""),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),
            completed_at=completed_at,
        )


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

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "agent_type": self.agent_type,
            "model": self.model,
            "phase": self.phase.value,
            "resolved_model": self.resolved_model,
            "task": self.task.to_dict() if self.task else None,
            "tokens": self.tokens.to_dict(),
            "context": self.context.to_dict(),
            "messages_count": self.messages_count,
            "spawn_time": self.spawn_time.isoformat(),
            "last_active": self.last_active.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentStatus:
        return cls(
            agent_id=data["agent_id"],
            name=data["name"],
            agent_type=data["agent_type"],
            model=data["model"],
            phase=AgentPhase(data["phase"]),
            resolved_model=data.get("resolved_model", ""),
            task=TaskInfo.from_dict(data["task"]) if data.get("task") else None,
            tokens=TokenUsage.from_dict(data.get("tokens", {})),
            context=ContextWindow.from_dict(data.get("context", {})),
            messages_count=data.get("messages_count", 0),
            spawn_time=datetime.fromisoformat(data["spawn_time"]) if data.get("spawn_time") else datetime.now(),
            last_active=datetime.fromisoformat(data["last_active"]) if data.get("last_active") else datetime.now(),
            metadata=data.get("metadata", {}),
        )


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

    def to_dict(self) -> dict[str, Any]:
        return {
            "swarm_id": self.swarm_id,
            "topology": self.topology.value,
            "max_agents": self.max_agents,
            "agents": [a.to_dict() for a in self.agents],
            "main_context": self.main_context.to_dict(),
            "created_at": self.created_at.isoformat(),
            "is_active": self.is_active,
            "overall_progress": self.overall_progress,
            "active_agents": self.active_agents,
            "completed_tasks": self.completed_tasks,
            "total_tasks": self.total_tasks,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SwarmStatus:
        return cls(
            swarm_id=data["swarm_id"],
            topology=SwarmTopology(data["topology"]),
            max_agents=data["max_agents"],
            agents=[AgentStatus.from_dict(a) for a in data.get("agents", [])],
            main_context=ContextWindow.from_dict(data.get("main_context", {})),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),
            is_active=data.get("is_active", True),
        )
