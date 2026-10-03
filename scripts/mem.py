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

import hashlib
import re
import sqlite3
import sys
import textwrap
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

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
        "  content_hash TEXT NOT NULL,"
        "  chunk_idx INTEGER NOT NULL,"
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
    db.execute("""
        CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
            INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES ('delete', old.id, old.text);
            INSERT INTO chunks_fts(rowid, text) VALUES (new.id, new.text);
        END""")
    db.commit()
    return db


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


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
    content_hash = _hash(text)
    rel = str(_relative(fp))
    mtime = fp.stat().st_mtime

    db = get_db()
    # remove old chunks for this file
    db.execute("DELETE FROM chunks WHERE filepath = ?", (rel,))
    chunks = chunk_markdown(text)
    for idx, (start, end, chunk_text) in enumerate(chunks):
        db.execute(
            "INSERT INTO chunks (filepath, content_hash, chunk_idx, text, start_line, end_line, mtime) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (rel, content_hash, idx, chunk_text, start, end, mtime),
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
    """Hybrid search: FTS5 BM25 → TF-IDF cosine merge → temporal decay → MMR re-rank."""
    db = get_db()
    rows = _fts_query(db, query, limit=50)

    if not rows:
        print("no results")
        db.close()
        return

    # Unpack: (filepath, chunk_idx, text, start_line, end_line, mtime, bm25)
    texts = [r[2] for r in rows]

    # -- TF-IDF cosine similarity (numpy vector leg) --
    tfidf, vocab, idf_vec = _build_tfidf(texts)
    qvec = _query_tfidf(query, vocab, idf_vec)
    cos_sims = tfidf @ qvec  # (n,)

    # -- Hybrid merge: 0.5 × BM25 + 0.5 × TF-IDF cosine --
    bm25_scores = np.array([1.0 / (1.0 + abs(r[6])) for r in rows])
    bm25_norm = bm25_scores / (bm25_scores.max() or 1)
    cos_norm = (cos_sims - cos_sims.min()) / (cos_sims.max() - cos_sims.min() + 1e-9)
    hybrid = 0.5 * bm25_norm + 0.5 * cos_norm

    # -- Temporal decay --
    decays = np.array([_decay_weight(r[0]) for r in rows])
    scored = hybrid * decays

    # -- MMR re-rank for diversity --
    order = _mmr_rerank(qvec, tfidf, scored, top_k=10)

    db.close()

    for rank, idx in enumerate(order):
        fp, _cidx, text, sl, el, _mtime, _bm = rows[idx]
        snippet = textwrap.shorten(text, width=120, placeholder="…")
        print(f"[{scored[idx]:.3f}] {snippet}")
        print(f"       ← {fp}:{sl}-{el}")
        if rank < len(order) - 1:
            print()


# ── numpy-powered TF-IDF + MMR pipeline ──


def _tokenize(text: str) -> list[str]:
    return re.findall(r"\b[a-zA-Z0-9]+\b", text.lower())


def _build_tfidf(documents: list[str]) -> tuple[np.ndarray, dict[str, int], np.ndarray]:
    """Build L2-normalized TF-IDF matrix. Returns (matrix, vocab, idf)."""
    tokenized = [_tokenize(d) for d in documents]
    vocab: dict[str, int] = {}
    for tokens in tokenized:
        for t in tokens:
            vocab.setdefault(t, len(vocab))

    n_docs = len(documents)
    n_terms = len(vocab)
    if n_terms == 0:
        return np.zeros((n_docs, 1)), {}, np.zeros(1)

    # TF
    tf = np.zeros((n_docs, n_terms))
    for i, tokens in enumerate(tokenized):
        counts = Counter(tokens)
        for t, c in counts.items():
            tf[i, vocab[t]] = c / len(tokens)

    # IDF
    df = np.zeros(n_terms)
    for tokens in tokenized:
        for t in set(tokens):
            df[vocab[t]] += 1
    idf_vec = np.log((n_docs + 1) / (df + 1)) + 1

    # TF-IDF + L2 normalize
    tfidf = tf * idf_vec
    norms = np.linalg.norm(tfidf, axis=1, keepdims=True)
    norms[norms == 0] = 1
    return tfidf / norms, vocab, idf_vec


def _query_tfidf(query: str, vocab: dict[str, int], idf_vec: np.ndarray) -> np.ndarray:
    """Build L2-normalized TF-IDF vector for query."""
    tokens = _tokenize(query)
    if not tokens or not vocab:
        return np.zeros(len(vocab) or 1)
    counts = Counter(tokens)
    vec = np.zeros(len(vocab))
    n_tokens = len(tokens)
    for t, c in counts.items():
        if t in vocab:
            vec[vocab[t]] = (c / n_tokens) * idf_vec[vocab[t]]
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec /= norm
    return vec


def _mmr_rerank(
    query_vec: np.ndarray,
    chunk_vecs: np.ndarray,
    relevance: np.ndarray,
    top_k: int = 10,
    lambda_param: float = 0.7,
) -> list[int]:
    """MMR re-ranking: balance relevance against diversity.

    relevance is the pre-computed score per chunk (hybrid × decay).
    lambda_param: 1.0 = pure relevance, 0.0 = pure diversity.
    """
    n = chunk_vecs.shape[0]
    if n <= 1:
        return list(range(n))

    sim_chunks = chunk_vecs @ chunk_vecs.T  # (n, n) pairwise cosine
    selected: list[int] = []
    remaining = list(range(n))

    for _ in range(min(top_k, n)):
        if not selected:
            best = int(np.argmax(relevance))
            selected.append(best)
            remaining.remove(best)
            continue

        max_sim_to_selected = np.array(
            [sim_chunks[i, selected].max() for i in remaining]
        )
        mmr_scores = (
            lambda_param * relevance[remaining]
            - (1 - lambda_param) * max_sim_to_selected
        )
        best = remaining[int(np.argmax(mmr_scores))]
        selected.append(best)
        remaining.remove(best)

    return selected


def _fts_query(db: sqlite3.Connection, query: str, limit: int = 20) -> list:
    """Try phrase match, then AND, then OR."""
    safe = query.replace('"', '""')
    terms = [t for t in safe.split() if len(t) > 0]
    if not terms:
        return []

    strategies = [
        " ".join(f'"{t}"' for t in terms),
        " AND ".join(terms),
        " OR ".join(terms),
    ]
    for fts_query in strategies:
        try:
            rows = db.execute(
                "SELECT c.filepath, c.chunk_idx, c.text, c.start_line, c.end_line, c.mtime, "
                "       fts.rank AS bm25 "
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
        "SELECT filepath, content_hash, COUNT(*) as chunks, MAX(mtime) "
        "FROM chunks GROUP BY filepath ORDER BY filepath"
    ).fetchall()
    if not rows:
        print("no indexed files")
    else:
        for fp, _h, n, mtime in rows:
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
