# AGENTS.md — hermes-memory-gbrain

Read-only MemoryProvider: gbrain is queried for context, never written to.

## Design

- **Read path:** `gbrain query` via subprocess for `prefetch()` + two tools
- **No write path:** Hermes `MEMORY.md` is the canonical store
- **Fail open:** never blocks Hermes agent loop
- **No extra deps:** Python stdlib only

## Hooks bound

| Hook | Role |
|------|------|
| `prefetch` | `gbrain query <current message>` before each turn |
| `system_prompt_block` | Static hint that gbrain tools are available |
| `get_tool_schemas` | `gbrain_search` + `gbrain_query` |
| `handle_tool_call` | Dispatch to gbrain CLI |

## Config

```json
{
  "brain_dir": "~/my-brain",
  "command": "gbrain",
  "timeout": 30
}
```

## Commit conventions

```
feat: <desc>
fix: <desc>
refactor: <desc>
docs: <desc>
```
