import hashlib
import json
import re
import time
import uuid
from datetime import datetime, timezone

import duckdb


class GridDB:
    def __init__(self, path: str = "grid_data.duckdb"):
        self.path = path
        self.conn = duckdb.connect(path)
        self.session_id = str(uuid.uuid4())
        self._init_schema()
        self._init_session()

    def _init_schema(self):
        self.conn.execute("DROP TABLE IF EXISTS web_cache CASCADE")
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS tool_logs (
                id INTEGER PRIMARY KEY,
                session_id VARCHAR,
                tool_name VARCHAR,
                tool_input VARCHAR,
                tool_output VARCHAR,
                duration_ms INTEGER,
                status VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.conn.execute("""
            CREATE SEQUENCE IF NOT EXISTS seq_tool_logs START 1
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS web_cache (
                url_hash VARCHAR PRIMARY KEY,
                url VARCHAR,
                content VARCHAR,
                fetched_at_ms BIGINT DEFAULT (epoch_ms(CURRENT_TIMESTAMP)),
                ttl_seconds INTEGER DEFAULT 3600
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS scan_results (
                id INTEGER PRIMARY KEY,
                session_id VARCHAR,
                target VARCHAR,
                scan_type VARCHAR,
                raw_output VARCHAR,
                open_ports JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.conn.execute("""
            CREATE SEQUENCE IF NOT EXISTS seq_scan_results START 1
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id VARCHAR PRIMARY KEY,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ended_at TIMESTAMP,
                turn_count INTEGER DEFAULT 0
            )
        """)

    def _init_session(self):
        self.conn.execute(
            "INSERT INTO sessions (id) VALUES (?)",
            [self.session_id],
        )

    def log_tool_call(
        self,
        tool_name: str,
        tool_input: str,
        tool_output: str,
        duration_ms: int,
        status: str,
    ):
        self.conn.execute(
            """
            INSERT INTO tool_logs (id, session_id, tool_name, tool_input, tool_output, duration_ms, status)
            VALUES (nextval('seq_tool_logs'), ?, ?, ?, ?, ?, ?)
            """,
            [self.session_id, tool_name, tool_input[:500], tool_output[:3000], duration_ms, status],
        )

    def get_web_cache(self, url: str, ttl_seconds: int = 3600) -> str | None:
        url_hash = hashlib.md5(url.encode()).hexdigest()
        row = self.conn.execute(
            """
            SELECT content
            FROM web_cache
            WHERE url_hash = ? AND (fetched_at_ms + ttl_seconds * 1000) > epoch_ms(CURRENT_TIMESTAMP)
            """,
            [url_hash],
        ).fetchone()
        if row:
            return row[0]
        return None

    def set_web_cache(self, url: str, content: str, ttl_seconds: int = 3600):
        url_hash = hashlib.md5(url.encode()).hexdigest()
        self.conn.execute("DELETE FROM web_cache WHERE url_hash = ?", [url_hash])
        self.conn.execute(
            """
            INSERT INTO web_cache (url_hash, url, content, fetched_at_ms, ttl_seconds)
            VALUES (?, ?, ?, epoch_ms(CURRENT_TIMESTAMP), ?)
            """,
            [url_hash, url, content[:8000], ttl_seconds],
        )

    def store_scan_result(
        self,
        target: str,
        scan_type: str,
        raw_output: str,
        open_ports: list | None = None,
    ):
        self.conn.execute(
            """
            INSERT INTO scan_results (id, session_id, target, scan_type, raw_output, open_ports)
            VALUES (nextval('seq_scan_results'), ?, ?, ?, ?, ?)
            """,
            [self.session_id, target, scan_type, raw_output[:5000],
             json.dumps(open_ports or [])],
        )

    @staticmethod
    def _parse_nmap_ports(raw: str) -> list[dict]:
        ports = []
        for m in re.finditer(r"(\d+)/(tcp|udp)\s+open\s+(\S+)", raw):
            ports.append({"port": int(m.group(1)), "protocol": m.group(2), "service": m.group(3)})
        return ports

    @staticmethod
    def _parse_ncscan_ports(raw: str) -> list[dict]:
        ports = []
        for line in raw.splitlines():
            m = re.match(r"\s*(\d+)/(tcp|udp)", line.strip())
            if m:
                ports.append({"port": int(m.group(1)), "protocol": m.group(2)})
        return ports

    def query(self, sql: str) -> str:
        sql = sql.strip().rstrip(";")
        allowed = ("SELECT", "WITH", "EXPLAIN", "DESCRIBE", "SHOW", "PRAGMA")
        if not sql.upper().startswith(allowed):
            return "Error: Only read-only queries allowed (SELECT, WITH, EXPLAIN, DESCRIBE, SHOW, PRAGMA)."
        try:
            result = self.conn.execute(sql)
            desc = [d[0] for d in result.description]
            rows = result.fetchall()
            if not rows:
                return "(no results)"
            header = " | ".join(str(c) for c in desc)
            sep = "---".join("---" for _ in desc)
            lines = [header, sep]
            for r in rows[:50]:
                lines.append(" | ".join(str(v) if v is not None else "NULL" for v in r))
            if len(rows) > 50:
                lines.append(f"... ({len(rows)} total rows)")
            txt = f"{len(rows)} row(s):\n" + "\n".join(lines)
            return txt
        except Exception as e:
            return f"Query error: {e}"

    def analytics(self) -> str:
        lines = ["-- Analytics --"]

        row = self.conn.execute(
            "SELECT count(*), avg(duration_ms) FROM tool_logs WHERE session_id = ?",
            [self.session_id],
        ).fetchone()
        total, avg_dur = row or (0, 0)
        lines.append(f"Calls this session: {total}  (avg {avg_dur:.0f}ms)" if total else "Calls this session: 0")

        if total:
            top = self.conn.execute(
                """
                SELECT tool_name, count(*) as cnt
                FROM tool_logs WHERE session_id = ?
                GROUP BY tool_name ORDER BY cnt DESC LIMIT 5
                """,
                [self.session_id],
            ).fetchall()
            lines.append("Top tools:")
            for name, cnt in top:
                lines.append(f"  {name}: {cnt}")

            errs = self.conn.execute(
                """
                SELECT tool_name, count(*) as errs
                FROM tool_logs WHERE session_id = ? AND status = 'error'
                GROUP BY tool_name ORDER BY errs DESC LIMIT 5
                """,
                [self.session_id],
            ).fetchall()
            if errs:
                lines.append("Errors:")
                for name, cnt in errs:
                    lines.append(f"  {name}: {cnt}")

            slow = self.conn.execute(
                """
                SELECT tool_name, max(duration_ms) as slowest
                FROM tool_logs WHERE session_id = ?
                GROUP BY tool_name ORDER BY slowest DESC LIMIT 5
                """,
                [self.session_id],
            ).fetchall()
            lines.append("Slowest calls:")
            for name, dur in slow:
                lines.append(f"  {name}: {dur}ms")

        return "\n".join(lines)

    def end_session(self):
        self.conn.execute(
            "UPDATE sessions SET ended_at = CURRENT_TIMESTAMP, turn_count = (SELECT count(*) FROM tool_logs WHERE session_id = ?) WHERE id = ?",
            [self.session_id, self.session_id],
        )

    def close(self):
        try:
            self.end_session()
        except Exception:
            pass
        try:
            self.conn.close()
        except Exception:
            pass
