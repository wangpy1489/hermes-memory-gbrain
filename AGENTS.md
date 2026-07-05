# AGENTS.md — hermes-memory-gbrain

## Design

- **Write path:** filesystem writes to `{brain_dir}/memory/hermes/`
- **Read path:** `gbrain query` via subprocess
- **Fail open:** never blocks Hermes agent loop
- **No extra deps:** Python stdlib only

## Key decisions (from grill-me)

| Decision | Choice |
|----------|--------|
| Write path | Filesystem (not `gbrain put`) |
| Pages | `user.md` + `context.md` |
| Format | Frontmatter + Compiled Truth + Timeline |
| Compiled Truth | Manual maintain, agent doesn't touch |
| Prefetch | `gbrain query <current message>`, raw output |
| Tools | `gbrain_search` + `gbrain_query` |
| Sync turns | No |

## Commit conventions

```
feat: <desc>
fix: <desc>
docs: <desc>
```
