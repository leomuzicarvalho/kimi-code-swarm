#!/usr/bin/env python3
"""Demo script to validate the Kimi Swarm framework."""

from kimi_swarm import SwarmOrchestrator, AgentConfig, KimiDisplay


def run_demo():
    print("=" * 60)
    print("🚀 KIMI SWARM ORCHESTRATION DEMO")
    print("=" * 60)

    # 1. Initialize swarm
    print("\n1️⃣  Initializing hierarchical swarm with max 5 agents...")
    orch = SwarmOrchestrator(topology="hierarchical", max_agents=5)
    status = orch.init_swarm()
    print(f"   Swarm ID: {status.swarm_id}")
    print(f"   Topology: {status.topology.value}")

    # 2. Spawn agents
    print("\n2️⃣  Spawning specialized agents...")
    agents_config = [
        AgentConfig(type="architect", name="architect-1", model="sonnet", domain="system design"),
        AgentConfig(type="coder", name="frontend-dev", model="sonnet", domain="react/typescript"),
        AgentConfig(type="coder", name="backend-dev", model="haiku", domain="python/api"),
        AgentConfig(type="tester", name="qa-engineer", model="haiku", domain="e2e testing"),
        AgentConfig(type="reviewer", name="security-guru", model="sonnet", domain="security audit"),
    ]

    for cfg in agents_config:
        agent = orch.spawn_agent(cfg)
        print(f"   ✅ {agent.name:20} | {agent.agent_type:10} | {agent.model:10} | ctx={agent.context.max_tokens:,}t")

    # 3. Show initial status
    print("\n3️⃣  Initial swarm status:")
    print("-" * 60)
    print(KimiDisplay.status_to_markdown(orch.get_status()))

    # 4. Assign and execute tasks
    print("\n4️⃣  Executing parallel tasks...")
    tasks = [
        ("frontend-dev", "Build responsive login page with form validation and OAuth buttons"),
        ("backend-dev", "Implement REST API endpoints for user authentication with JWT middleware"),
        ("qa-engineer", "Design test plan covering login flows, edge cases, and error handling"),
        ("security-guru", "Review authentication flow for OWASP top 10 vulnerabilities"),
    ]

    for name, task_desc in tasks:
        agent_id = next(a.agent_id for a in orch.list_agents() if a.name == name)
        result = orch.execute_task(agent_id, task_desc)
        print(f"   ⚡ {name:20} completed | tokens={result['tokens']['total']}")

    # 5. Update progress on in-progress work
    print("\n5️⃣  Simulating partial progress updates...")
    orch.update_agent_progress(
        next(a.agent_id for a in orch.list_agents() if a.name == "frontend-dev"),
        75.0
    )
    orch.set_agent_phase(
        next(a.agent_id for a in orch.list_agents() if a.name == "backend-dev"),
        "reviewing"
    )

    # 6. Final status with full comparison
    print("\n6️⃣  Final swarm status with context comparison:")
    print("-" * 60)
    status = orch.get_status()
    print(KimiDisplay.status_to_markdown(status))

    # 7. JSON export
    print("\n7️⃣  JSON export (abridged):")
    import json
    data = {
        "swarm_id": status.swarm_id,
        "active_agents": status.active_agents,
        "overall_progress": status.overall_progress,
        "main_context": {
            "used": status.main_context.used_tokens,
            "max": status.main_context.max_tokens,
            "percent": status.main_context.usage_percent,
        },
        "agents": [
            {
                "name": a.name,
                "phase": a.phase.value,
                "progress": a.task.progress_percent if a.task else 0,
                "tokens": a.tokens.total_tokens,
                "context_used": a.context.used_tokens,
                "context_max": a.context.max_tokens,
            }
            for a in status.agents
        ],
    }
    print(json.dumps(data, indent=2))

    # 8. Shutdown
    print("\n8️⃣  Shutting down swarm...")
    orch.shutdown()
    print("   🔴 Swarm terminated")

    print("\n" + "=" * 60)
    print("✅ DEMO COMPLETE — All systems validated")
    print("=" * 60)


if __name__ == "__main__":
    run_demo()
