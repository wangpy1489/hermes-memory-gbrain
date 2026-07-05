# hermes-memory-gbrain

GBrain memory provider for [Hermes Agent](https://github.com/NousResearch/hermes-agent).

Bridges Hermes' memory pipeline to a [GBrain](https://github.com/NousResearch/gbrain) knowledge base. Hermes `memory()` writes become structured pages in your brain; gbrain semantic search auto-injects context before every turn.

## How it works

```
Hermes memory(action='add', target='user', content='偏好 Python')
        │
        ▼
memory/hermes/user.md          ← Timeline append
memory/hermes/context.md       ← Timeline append
        │
        ▼
gbrain sync && embed           ← cron job indexes
        │
        ▼
prefetch("what languages?")    ← gbrain query → auto-inject
```

**Write path:** Filesystem → `{brain_dir}/memory/hermes/{user,context}.md`  
**Read path:** `gbrain query <message>` → injected before each turn

## Install

```bash
git clone https://github.com/wangpy1489/hermes-memory-gbrain \
  ~/.hermes/plugins/gbrain
cd ~/.hermes/plugins/gbrain && ./install.sh
```

## Configure

Create `~/.hermes/gbrain.json`:

```json
{
  "brain_dir": "~/ppy-brain",
  "command": "gbrain",
  "timeout": 30
}
```

Activate:

```bash
hermes config set memory.provider gbrain
hermes memory status
```

## License

MIT
