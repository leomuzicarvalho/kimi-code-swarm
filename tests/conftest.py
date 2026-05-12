import os

# Force simulated agent execution in tests to avoid spawning real
# Kimi CLI subprocesses and keep test suite fast.
os.environ.setdefault("KIMI_SWARM_SIMULATE", "1")
