# hermes-memory-gbrain

GBrain memory provider plugin for [Hermes Agent](https://github.com/NousResearch/hermes-agent).

## What it does

Connects Hermes' memory pipeline to a [GBrain](https://github.com/NousResearch/gbrain) knowledge base — a Postgres-backed semantic memory system with vector search, fact deduplication, and contradiction detection.

Instead of requiring explicit tool calls to access memory (the current MCP approach), this plugin makes gbrain a **native Hermes memory provider**:

- **Prefetch injection** — relevant gbrain context is automatically injected before each turn
- **Write-through** — `memory(action='add')` calls are mirrored into gbrain
- **Cross-profile sharing** — multiple Hermes profiles share one gbrain instance
- **Tool access** — `gbrain_search` / `gbrain_query` tools for explicit recall

## Installation

### Prerequisites

- Hermes Agent >= 0.7.0
- GBrain installed and initialized: `gbrain init`

### Quick Install

```bash
# Clone into Hermes plugins directory
git clone https://github.com/wangpy1489/hermes-memory-gbrain \
  ~/.hermes/plugins/gbrain

# Activate the provider
hermes config set memory.provider gbrain

# Verify
hermes memory status
```

### Manual Install

```bash
./install.sh
```

## Configuration

```yaml
# ~/.hermes/config.yaml
memory:
  provider: gbrain
```

Optional: create `~/.hermes/gbrain.json` for advanced config:

```json
{
  "context_tokens": 2000,
  "prefetch_mode": "hybrid",
  "write_mirror": true
}
```

## Architecture

```
Hermes Agent
  ┌─ MemoryManager ─────────────────────────────────┐
  │                                                  │
  │  ┌─ BuiltinProvider (MEMORY.md + USER.md)        │
  │  └─ GbrainMemoryProvider ◄── this plugin         │
  │       │                                          │
  │       ├─ prefetch(query) ──► gbrain query        │
  │       ├─ on_memory_write() ► gbrain put          │
  │       ├─ sync_turn() ──────► gbrain put (opt)    │
  │       └─ handle_tool_call() ► gbrain search/query│
  │                                                  │
  └──────────────────────────────────────────────────┘
                          │
                          ▼
              ┌─────────────────────┐
              │  GBrain (Postgres)  │
              │  • vector search    │
              │  • knowledge graph  │
              │  • fact dedup       │
              └─────────────────────┘
```

## License

MIT
