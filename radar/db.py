"""Persistencia en SQLite: ofertas, estados y registro de búsquedas."""

import json
import sqlite3
from datetime import datetime

from .config import db_path

ESTADOS = {
    "nueva": "Nueva",
    "interesa": "Me interesa",
    "postulada": "Postulé",
    "entrevista": "Entrevista",
    "descartada": "Descartada",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    uid             TEXT UNIQUE NOT NULL,
    source          TEXT NOT NULL,
    title           TEXT NOT NULL,
    company         TEXT,
    location        TEXT,
    modality        TEXT,
    url             TEXT,
    alt_urls        TEXT DEFAULT '[]',
    description     TEXT,
    salary          TEXT,
    published_at    TEXT,
    fingerprint     TEXT,
    extra           TEXT DEFAULT '{}',
    found_at        TEXT NOT NULL,
    last_seen_at    TEXT NOT NULL,
    rule_score      INTEGER DEFAULT 0,
    rule_reasons    TEXT DEFAULT '[]',
    excluded        INTEGER DEFAULT 0,
    exclude_reason  TEXT,
    ai_score        INTEGER,
    ai_json         TEXT,
    ai_at           TEXT,
    cover_letter    TEXT,
    recruiter_msg   TEXT,
    letter_by_ai    INTEGER DEFAULT 0,
    questions       TEXT DEFAULT '[]',
    status          TEXT DEFAULT 'nueva',
    status_at       TEXT,
    notes           TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_jobs_fp ON jobs(fingerprint);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);

CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    found       INTEGER DEFAULT 0,
    new         INTEGER DEFAULT 0,
    relevant    INTEGER DEFAULT 0,
    errors      TEXT DEFAULT '[]',
    trigger     TEXT
);
"""


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path(), timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(jobs)")}
        if "notified_at" not in cols:  # migración: aviso por correo
            conn.execute("ALTER TABLE jobs ADD COLUMN notified_at TEXT")


def get_meta(key: str):
    with connect() as conn:
        row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None


def set_meta(key: str, value: str) -> None:
    with connect() as conn:
        conn.execute("INSERT INTO meta (key, value) VALUES (?, ?) "
                     "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))


# ---------- ofertas ----------

def get_by_uid(uid: str):
    with connect() as conn:
        return conn.execute("SELECT * FROM jobs WHERE uid = ?", (uid,)).fetchone()


def find_duplicate(fp: str, source: str):
    if not fp or fp.endswith("|"):
        return None
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM jobs WHERE fingerprint = ? AND source != ? LIMIT 1", (fp, source)
        ).fetchone()


def touch(uid: str) -> None:
    with connect() as conn:
        conn.execute("UPDATE jobs SET last_seen_at = ? WHERE uid = ?", (now(), uid))


def add_alt_url(job_id: int, source: str, url: str) -> None:
    with connect() as conn:
        row = conn.execute("SELECT alt_urls FROM jobs WHERE id = ?", (job_id,)).fetchone()
        alts = json.loads(row["alt_urls"] or "[]")
        if url and all(a["url"] != url for a in alts):
            alts.append({"source": source, "url": url})
            conn.execute(
                "UPDATE jobs SET alt_urls = ?, last_seen_at = ? WHERE id = ?",
                (json.dumps(alts, ensure_ascii=False), now(), job_id),
            )


def insert_job(job: dict, score: dict) -> int:
    ts = now()
    with connect() as conn:
        cur = conn.execute(
            """INSERT INTO jobs (uid, source, title, company, location, modality, url, description,
                   salary, published_at, fingerprint, extra, found_at, last_seen_at, rule_score,
                   rule_reasons, excluded, exclude_reason, status, status_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                job["uid"], job["source"], job["title"], job.get("company"), job.get("location"),
                job.get("modality"), job.get("url"), job.get("description"), job.get("salary"),
                job.get("published_at"), job.get("fingerprint"),
                json.dumps(job.get("extra", {}), ensure_ascii=False), ts, ts, score["score"],
                json.dumps(score["reasons"], ensure_ascii=False), int(score["excluded"]),
                score.get("exclude_reason"), "nueva", ts,
            ),
        )
        return cur.lastrowid


def update_rule_score(job_id: int, score: dict) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE jobs SET rule_score=?, rule_reasons=?, excluded=?, exclude_reason=? WHERE id=?",
            (score["score"], json.dumps(score["reasons"], ensure_ascii=False),
             int(score["excluded"]), score.get("exclude_reason"), job_id),
        )


def get_job(job_id: int):
    with connect() as conn:
        return conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()


def all_jobs():
    with connect() as conn:
        return conn.execute("SELECT * FROM jobs").fetchall()


def list_jobs(status=None, source=None, min_score=0, q=None, show_excluded=False, order="score"):
    sql = "SELECT * FROM jobs WHERE 1=1"
    args = []
    if show_excluded:
        sql += " AND excluded = 1"
    else:
        sql += " AND excluded = 0"
        if status:
            sql += " AND status = ?"
            args.append(status)
        sql += " AND COALESCE(ai_score, rule_score) >= ?"
        args.append(min_score)
    if source:
        sql += " AND source = ?"
        args.append(source)
    if q:
        sql += " AND (title LIKE ? OR company LIKE ? OR description LIKE ?)"
        args += [f"%{q}%"] * 3
    if order == "fecha":
        sql += " ORDER BY COALESCE(published_at, found_at) DESC, found_at DESC"
    else:
        sql += " ORDER BY COALESCE(ai_score, rule_score) DESC, COALESCE(published_at, found_at) DESC"
    sql += " LIMIT 500"
    with connect() as conn:
        return conn.execute(sql, args).fetchall()


def counts(min_score: int) -> dict:
    with connect() as conn:
        rows = conn.execute(
            """SELECT status, COUNT(*) n FROM jobs
               WHERE excluded = 0 AND COALESCE(ai_score, rule_score) >= ? GROUP BY status""",
            (min_score,),
        ).fetchall()
        out = {r["status"]: r["n"] for r in rows}
        out["_excluidas"] = conn.execute("SELECT COUNT(*) FROM jobs WHERE excluded = 1").fetchone()[0]
        out["_total"] = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        return out


def sources() -> list:
    with connect() as conn:
        return [r[0] for r in conn.execute("SELECT DISTINCT source FROM jobs ORDER BY source")]


def set_status(job_id: int, status: str) -> None:
    if status not in ESTADOS:
        raise ValueError(f"Estado inválido: {status}")
    with connect() as conn:
        conn.execute("UPDATE jobs SET status = ?, status_at = ? WHERE id = ?", (status, now(), job_id))


def set_notes(job_id: int, notes: str) -> None:
    with connect() as conn:
        conn.execute("UPDATE jobs SET notes = ? WHERE id = ?", (notes, job_id))


def set_ai(job_id: int, analysis: dict) -> None:
    score = analysis.get("puntaje")
    with connect() as conn:
        conn.execute(
            "UPDATE jobs SET ai_score = ?, ai_json = ?, ai_at = ? WHERE id = ?",
            (int(score) if isinstance(score, (int, float)) else None,
             json.dumps(analysis, ensure_ascii=False), now(), job_id),
        )


def set_letter(job_id: int, letter: str, recruiter_msg: str, by_ai: bool, questions=None) -> None:
    with connect() as conn:
        if questions is None:
            conn.execute(
                "UPDATE jobs SET cover_letter = ?, recruiter_msg = ?, letter_by_ai = ? WHERE id = ?",
                (letter, recruiter_msg, int(by_ai), job_id),
            )
        else:
            conn.execute(
                """UPDATE jobs SET cover_letter = ?, recruiter_msg = ?, letter_by_ai = ?, questions = ?
                   WHERE id = ?""",
                (letter, recruiter_msg, int(by_ai), json.dumps(questions, ensure_ascii=False), job_id),
            )


def pending_ai(min_score: int, limit: int):
    with connect() as conn:
        return conn.execute(
            """SELECT * FROM jobs WHERE excluded = 0 AND ai_json IS NULL AND rule_score >= ?
               AND status IN ('nueva', 'interesa') ORDER BY rule_score DESC, found_at DESC LIMIT ?""",
            (min_score, limit),
        ).fetchall()


# ---------- búsquedas ----------

def start_run(trigger: str) -> int:
    with connect() as conn:
        return conn.execute(
            "INSERT INTO runs (started_at, trigger) VALUES (?, ?)", (now(), trigger)
        ).lastrowid


def finish_run(run_id: int, found: int, new: int, relevant: int, errors: list) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE runs SET finished_at=?, found=?, new=?, relevant=?, errors=? WHERE id=?",
            (now(), found, new, relevant, json.dumps(errors, ensure_ascii=False), run_id),
        )


def last_run():
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM runs WHERE finished_at IS NOT NULL ORDER BY id DESC LIMIT 1"
        ).fetchone()
