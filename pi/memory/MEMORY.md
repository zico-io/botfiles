## System Knowledge

- **User:** percules
- **Memory system:** memweave-inspired (Markdown + SQLite FTS5, keyword-only, no embeddings)
- **Storage:** pi/memory/*.md (plain Markdown, git-versioned)
- **Index:** pi/memory.db (SQLite, rebuildable from .md files)
- **Tools:** mem_search, mem_write, mem_list, mem_rebuild
- **Conventions:** Use mem_search before making decisions that rely on past context. Store discovered preferences, decisions, and project conventions with mem_write.