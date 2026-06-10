# Tables

Standard Markdown pipe tables, themed automatically:

| Attack            | Vector                      | Primary mitigation              |
| ----------------- | --------------------------- | ------------------------------- |
| Prompt injection  | Untrusted content in RAG    | Treat model output as untrusted |
| Jailbreak         | Adversarial instructions    | Policy + output filtering       |
| ArtPrompt         | ASCII-encoded payloads      | Decode-aware input screening    |
| Tool abuse        | Over-privileged agents      | Least privilege, gated actions  |
