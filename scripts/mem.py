#!/usr/bin/env python3
"""memweave-inspired memory system for pi harness — Markdown files + SQLite FTS5.

Usage:
  python3 mem.py search <query>            # full-text search
  python3 mem.py add <path>                # index a markdown file
  python3 mem.py write <name> <content>    # write + index a memory
  python3 mem.py list                      # list indexed files
  python3 mem.py stats                     # show memory stats
  python3 mem.py rebuild                   # rebuild index from all .md files

Store: pi/memory/*.md  |  Index: pi/memory.db
"""

import re
import sqlite3
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path

BOTFILES = Path(__file__).resolve().parent.parent
MEMORY_DIR = BOTFILES / "pi" / "memory"
DB_PATH = BOTFILES / "pi" / "memory.db"
CHUNK_SIZE = 500  # characters per chunk


def get_db() -> sqlite3.Connection:
    db = sqlite3.connect(str(DB_PATH))
    db.execute("PRAGMA journal_mode=WAL")
    db.execute(
        "CREATE TABLE IF NOT EXISTS chunks ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  filepath TEXT NOT NULL,"
        "  text TEXT NOT NULL,"
        "  start_line INTEGER NOT NULL,"
        "  end_line INTEGER NOT NULL,"
        "  mtime REAL NOT NULL)"
    )
    db.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5("
        "  text, content='chunks', content_rowid='id')"
    )
    # triggers to keep FTS in sync
    db.execute("""
        CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
            INSERT INTO chunks_fts(rowid, text) VALUES (new.id, new.text);
        END""")
    db.execute("""
        CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
            INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES ('delete', old.id, old.text);
        END""")
    db.commit()
    return db


def _is_dated(filename: str) -> bool:
    """Check if filename starts with YYYY-MM-DD pattern."""
    return bool(re.match(r"^\d{4}-\d{2}-\d{2}", filename))


def _decay_weight(filepath: str) -> float:
    """Temporal decay: recent dated files rank higher, evergreen = 1.0."""
    name = Path(filepath).name
    if not _is_dated(name):
        return 1.0  # evergreen
    try:
        date_str = name[:10]
        file_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        age_days = (datetime.now(timezone.utc) - file_date).days
        if age_days <= 0:
            return 1.0
        # half-life of 30 days
        return max(0.1, 0.5 ** (age_days / 30))
    except (ValueError, IndexError):
        return 1.0


def chunk_markdown(text: str) -> list[tuple[int, int, str]]:
    """Split markdown text into chunks with line ranges."""
    lines = text.split("\n")
    chunks = []
    current = []
    current_start = 1
    for i, line in enumerate(lines, 1):
        current.append(line)
        if len("\n".join(current)) >= CHUNK_SIZE:
            chunks.append((current_start, i, "\n".join(current)))
            current = []
            current_start = i + 1
    if current:
        chunks.append((current_start, len(lines), "\n".join(current)))
    return chunks


def cmd_add(filepath: str) -> None:
    fp = Path(filepath).resolve()
    if not fp.exists():
        print(f"ERROR: file not found: {fp}")
        sys.exit(1)
    if fp.suffix not in (".md", ".markdown"):
        print(f"WARNING: not a markdown file: {fp}")
        sys.exit(1)

    text = fp.read_text(encoding="utf-8")
    rel = str(_relative(fp))
    mtime = fp.stat().st_mtime

    db = get_db()
    # remove old chunks for this file
    db.execute("DELETE FROM chunks WHERE filepath = ?", (rel,))
    chunks = chunk_markdown(text)
    for start, end, chunk_text in chunks:
        db.execute(
            "INSERT INTO chunks (filepath, text, start_line, end_line, mtime) VALUES (?, ?, ?, ?, ?)",
            (rel, chunk_text, start, end, mtime),
        )
    db.commit()
    db.close()
    print(f"indexed {rel} ({len(chunks)} chunks)")


def cmd_write(name: str, content: str) -> None:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    fp = MEMORY_DIR / f"{name}.md"
    fp.write_text(content, encoding="utf-8")
    print(f"wrote {fp}")
    cmd_add(str(fp))


def cmd_search(query: str) -> None:
    """FTS5 BM25 ranking, weighted by temporal decay."""
    db = get_db()
    rows = _fts_query(db, query, limit=50)
    db.close()
    if not rows:
        print("no results")
        return
    # FTS5 rank is negated BM25: more negative is a better match.
    scored = sorted(
        ((-bm25 * _decay_weight(fp), fp, text, sl, el) for fp, text, sl, el, bm25 in rows),
        reverse=True,
    )[:10]
    print("\n\n".join(
        f"[{score:.3f}] {textwrap.shorten(text, width=120, placeholder='…')}\n       ← {fp}:{sl}-{el}"
        for score, fp, text, sl, el in scored
    ))


def _fts_query(db: sqlite3.Connection, query: str, limit: int = 20) -> list:
    """Try all terms (AND), then any term (OR)."""
    safe = query.replace('"', '""')
    terms = [t for t in safe.split() if len(t) > 0]
    if not terms:
        return []

    quoted = [f'"{t}"' for t in terms]
    strategies = [" ".join(quoted), " OR ".join(quoted)]
    for fts_query in strategies:
        try:
            rows = db.execute(
                "SELECT c.filepath, c.text, c.start_line, c.end_line, fts.rank "
                "FROM chunks_fts fts "
                "JOIN chunks c ON c.id = fts.rowid "
                "WHERE chunks_fts MATCH ? "
                "ORDER BY fts.rank "
                "LIMIT ?",
                (fts_query, limit),
            ).fetchall()
            if rows:
                return rows
        except sqlite3.OperationalError:
            continue
    return []


def cmd_list() -> None:
    db = get_db()
    rows = db.execute(
        "SELECT filepath, COUNT(*) as chunks, MAX(mtime) "
        "FROM chunks GROUP BY filepath ORDER BY filepath"
    ).fetchall()
    if not rows:
        print("no indexed files")
    else:
        for fp, n, mtime in rows:
            ts = (
                datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
                if mtime
                else "unknown"
            )
            decay = (
                "evergreen"
                if not _is_dated(Path(fp).name)
                else f"decay={_decay_weight(fp):.2f}"
            )
            print(f"  {fp}  ({n} chunks, {ts}, {decay})")
    db.close()


def cmd_stats() -> None:
    db = get_db()
    file_count = db.execute("SELECT COUNT(DISTINCT filepath) FROM chunks").fetchone()[0]
    chunk_count = db.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    total_chars = db.execute(
        "SELECT COALESCE(SUM(LENGTH(text)), 0) FROM chunks"
    ).fetchone()[0]
    db_size = DB_PATH.stat().st_size if DB_PATH.exists() else 0
    md_count = len(list(MEMORY_DIR.rglob("*.md"))) if MEMORY_DIR.exists() else 0

    print(f"  files indexed:  {file_count}")
    print(f"  markdown files: {md_count}")
    print(f"  chunks:         {chunk_count}")
    print(f"  total chars:    {total_chars}")
    print(f"  db size:        {db_size / 1024:.1f} KB")
    print(f"  db path:        {DB_PATH}")
    print(f"  memory dir:     {MEMORY_DIR}")
    db.close()


def cmd_rebuild() -> None:
    """Rebuild index from all .md files in memory dir."""
    if not MEMORY_DIR.exists():
        print("no memory directory")
        return
    db = get_db()
    db.execute("DELETE FROM chunks")
    db.commit()
    db.close()
    count = 0
    for fp in sorted(MEMORY_DIR.rglob("*.md")):
        cmd_add(str(fp))
        count += 1
    print(f"rebuilt index from {count} files")


def _relative(p: Path) -> Path:
    try:
        return p.relative_to(MEMORY_DIR)
    except ValueError:
        return p


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "search" and len(sys.argv) >= 3:
        cmd_search(sys.argv[2])
    elif cmd == "add" and len(sys.argv) >= 3:
        cmd_add(sys.argv[2])
    elif cmd == "write" and len(sys.argv) >= 4:
        cmd_write(sys.argv[2], sys.argv[3])
    elif cmd == "list":
        cmd_list()
    elif cmd == "stats":
        cmd_stats()
    elif cmd == "rebuild":
        cmd_rebuild()
    else:
        print(f"unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
