# agent-ops

Repository root is reserved for docs, dependency files, and other project assets.

Architecture specs live under `docs/`.

- `docs/workflow-app-platform-v2.md`:
  App-centric workflow platform rewrite spec covering registry, integrations, connections, workflow schema, and editor UX.

The active Django workspace lives in `agent_ops/`:

```text
agent_ops/
  manage.py
  agent_ops/
  users/
  templates/
```

Workflow execution and the designer are catalog-only. Legacy workflow node definitions are unsupported.
