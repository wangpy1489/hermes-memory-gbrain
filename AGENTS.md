# AGENTS.md — hermes-memory-gbrain

Instructions for AI coding assistants working on this project.

## Project Overview

A MemoryProvider plugin for Hermes Agent that bridges to GBrain. Implements the `MemoryProvider` ABC from `agent/memory_provider.py`.

## Key Files

```
hermes_memory_gbrain/
├── __init__.py    # GbrainMemoryProvider — implements MemoryProvider ABC
├── client.py      # gbrain CLI wrapper — subprocess calls
└── config.py      # GbrainConfig — JSON config handling
```

## Reference: Hermes Agent source

The authoritative source for the MemoryProvider interface lives at:
`~/.hermes/hermes-agent/agent/memory_provider.py`

Key classes:
- `MemoryProvider` (ABC) — the interface
- `MemoryManager` — `agent/memory_manager.py` — orchestrates providers

Reference implementations:
- `plugins/memory/honcho/__init__.py` — most complex (threading, cadence, dialectic)
- `plugins/memory/mem0/__init__.py` — simpler (REST API calls)

## Design Principles

1. **Keep it simple** — gbrain is local PostgreSQL, no network latency. Synchronous CLI calls are fine.
2. **Fail open** — if gbrain is down, Hermes keeps working. Never block the agent loop.
3. **Respect token budget** — prefetch output must fit within configurable context window.
4. **No extra deps** — use only Python stdlib + subprocess for gbrain CLI.

## gbrain CLI Reference

```bash
gbrain query <question>    # Hybrid search (RRF + vector + expansion)
gbrain search <query>      # Keyword search (tsvector)
gbrain put <slug>          # Write/update a page (reads from stdin)
gbrain get <slug>          # Read a page
gbrain list                # List pages
```

## Development

```bash
# Run tests
python -m pytest tests/ -v

# Test with Hermes
hermes config set memory.provider gbrain
hermes memory status
```

## Commit Conventions

```
feat: <description>    # New feature
fix: <description>     # Bug fix
refactor: <desc>       # Code restructuring
docs: <description>    # Documentation
test: <description>    # Tests only
```
