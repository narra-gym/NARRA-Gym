import csv
import io
import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.config import settings


def _utcnow() -> str:
    return datetime.utcnow().isoformat()


class ExperimentStore:
    """SQLite-backed persistence for benchmark sessions, logs, and exports."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._lock = threading.Lock()
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        self._init_db()
        self._seed_default_conditions()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS participants (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    metadata_json TEXT
                );

                CREATE TABLE IF NOT EXISTS experiment_conditions (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    active INTEGER NOT NULL DEFAULT 1,
                    assignment_count INTEGER NOT NULL DEFAULT 0,
                    llm_config_json TEXT NOT NULL,
                    metadata_json TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS experiment_sessions (
                    id TEXT PRIMARY KEY,
                    participant_id TEXT NOT NULL,
                    story_id TEXT,
                    condition_id TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    emotional_need TEXT,
                    metadata_json TEXT,
                    FOREIGN KEY(participant_id) REFERENCES participants(id),
                    FOREIGN KEY(condition_id) REFERENCES experiment_conditions(id)
                );

                CREATE TABLE IF NOT EXISTS story_events (
                    id TEXT PRIMARY KEY,
                    session_id TEXT,
                    participant_id TEXT,
                    story_id TEXT,
                    event_type TEXT NOT NULL,
                    payload_json TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS turn_logs (
                    id TEXT PRIMARY KEY,
                    session_id TEXT,
                    participant_id TEXT,
                    story_id TEXT,
                    turn_index INTEGER NOT NULL,
                    action_type TEXT NOT NULL,
                    user_input TEXT,
                    choice_id TEXT,
                    choice_text TEXT,
                    response_character_id TEXT,
                    response_text TEXT,
                    latency_ms REAL,
                    model_provider TEXT,
                    llm_config_json TEXT,
                    metadata_json TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS feedback_logs (
                    id TEXT PRIMARY KEY,
                    session_id TEXT,
                    participant_id TEXT,
                    story_id TEXT,
                    user_id TEXT,
                    rating INTEGER NOT NULL,
                    feelings_json TEXT,
                    scores_json TEXT,
                    comment TEXT,
                    feedback_type TEXT,
                    form_version TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS llm_call_logs (
                    id TEXT PRIMARY KEY,
                    session_id TEXT,
                    participant_id TEXT,
                    story_id TEXT,
                    source TEXT NOT NULL,
                    task TEXT NOT NULL,
                    model_provider TEXT,
                    model_name TEXT,
                    request_messages_json TEXT,
                    response_text TEXT,
                    error TEXT,
                    latency_ms REAL,
                    metadata_json TEXT,
                    created_at TEXT NOT NULL
                );
                """
            )
            self._ensure_column(conn, "feedback_logs", "scores_json", "TEXT")
            self._ensure_column(conn, "feedback_logs", "form_version", "TEXT")

    def _ensure_column(self, conn: sqlite3.Connection, table_name: str, column_name: str, column_type: str) -> None:
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        existing = {row["name"] for row in rows}
        if column_name in existing:
            return
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")

    def _default_llm_config(self) -> Dict[str, str]:
        return {
            "default": settings.get_llm_model("default"),
            "story": settings.get_llm_model("story"),
            "interactive_element": settings.get_llm_model("interactive_element"),
            "questions": settings.get_llm_model("questions"),
            "keywords": settings.get_llm_model("keywords"),
            "profile_keywords": settings.get_llm_model("profile_keywords"),
            "reflection": settings.get_llm_model("reflection"),
        }

    def _selected_model_llm_config(self, selected_model: Optional[str]) -> Dict[str, str]:
        if not selected_model:
            return {}
        return {
            task: selected_model
            for task in settings.BENCHMARK_TASKS
        }

    def _seed_default_conditions(self) -> None:
        if self.list_conditions(include_inactive=True):
            return

        raw = settings.EXPERIMENT_CONDITIONS_JSON
        if raw:
            try:
                conditions = json.loads(raw)
            except json.JSONDecodeError:
                conditions = []
        else:
            conditions = []

        if not conditions:
            conditions = [
                {
                    "id": "baseline",
                    "name": "Baseline",
                    "description": "Default NARRA-Gym benchmark condition",
                    "active": True,
                    "llm_config": self._default_llm_config(),
                    "metadata": {},
                }
            ]

        with self._connect() as conn:
            for condition in conditions:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO experiment_conditions
                    (id, name, description, active, assignment_count, llm_config_json, metadata_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        condition.get("id", str(uuid.uuid4())),
                        condition.get("name", "Unnamed Condition"),
                        condition.get("description"),
                        1 if condition.get("active", True) else 0,
                        int(condition.get("assignment_count", 0)),
                        json.dumps(condition.get("llm_config", self._default_llm_config()), ensure_ascii=False),
                        json.dumps(condition.get("metadata", {}), ensure_ascii=False),
                        _utcnow(),
                    ),
                )

    def ensure_participant(self, participant_id: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> str:
        participant_id = participant_id or f"participant-{uuid.uuid4()}"
        metadata = metadata or {}
        with self._connect() as conn:
            existing = conn.execute("SELECT id FROM participants WHERE id = ?", (participant_id,)).fetchone()
            if existing is None:
                conn.execute(
                    "INSERT INTO participants (id, created_at, metadata_json) VALUES (?, ?, ?)",
                    (participant_id, _utcnow(), json.dumps(metadata, ensure_ascii=False)),
                )
        return participant_id

    def list_conditions(self, include_inactive: bool = False) -> List[Dict[str, Any]]:
        query = "SELECT * FROM experiment_conditions"
        if not include_inactive:
            query += " WHERE active = 1"
        query += " ORDER BY name ASC"
        with self._connect() as conn:
            rows = conn.execute(query).fetchall()
        return [self._row_to_condition(row) for row in rows]

    def get_condition(self, condition_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM experiment_conditions WHERE id = ?",
                (condition_id,),
            ).fetchone()
        return self._row_to_condition(row) if row else None

    def _row_to_condition(self, row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "id": row["id"],
            "name": row["name"],
            "description": row["description"],
            "active": bool(row["active"]),
            "assignment_count": row["assignment_count"],
            "llm_config": json.loads(row["llm_config_json"] or "{}"),
            "metadata": json.loads(row["metadata_json"] or "{}"),
            "created_at": row["created_at"],
        }

    def assign_condition(self, requested_condition_id: Optional[str] = None) -> Dict[str, Any]:
        with self._lock:
            with self._connect() as conn:
                if requested_condition_id:
                    row = conn.execute(
                        "SELECT * FROM experiment_conditions WHERE id = ? AND active = 1",
                        (requested_condition_id,),
                    ).fetchone()
                    if row is None:
                        raise ValueError(f"Condition '{requested_condition_id}' is not available")
                else:
                    row = conn.execute(
                        """
                        SELECT * FROM experiment_conditions
                        WHERE active = 1
                        ORDER BY assignment_count ASC, created_at ASC
                        LIMIT 1
                        """
                    ).fetchone()
                    if row is None:
                        raise ValueError("No active experiment conditions available")

                conn.execute(
                    "UPDATE experiment_conditions SET assignment_count = assignment_count + 1 WHERE id = ?",
                    (row["id"],),
                )
                refreshed = conn.execute(
                    "SELECT * FROM experiment_conditions WHERE id = ?",
                    (row["id"],),
                ).fetchone()
        return self._row_to_condition(refreshed)

    def create_session(
        self,
        participant_id: str,
        mode: str = "benchmark",
        requested_condition_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        selected_model: Optional[str] = None,
    ) -> Dict[str, Any]:
        participant_id = self.ensure_participant(participant_id)
        condition = self.assign_condition(requested_condition_id)
        session_id = f"session-{uuid.uuid4()}"
        now = _utcnow()
        session_metadata = dict(metadata or {})
        if selected_model:
            session_metadata["selected_model"] = selected_model
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO experiment_sessions
                (id, participant_id, story_id, condition_id, mode, status, started_at, completed_at, emotional_need, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    participant_id,
                    None,
                    condition["id"],
                    mode,
                    "active",
                    now,
                    None,
                    None,
                    json.dumps(session_metadata, ensure_ascii=False),
                ),
            )
        session = self.get_session(session_id) or {
            "session_id": session_id,
            "participant_id": participant_id,
            "condition": condition,
            "mode": mode,
            "started_at": now,
            "selected_model": selected_model,
        }
        return session

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM experiment_sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
        return self._row_to_session(row) if row else None

    def _count_by_session(self, conn: sqlite3.Connection, table_name: str, session_id: str) -> int:
        row = conn.execute(
            f"SELECT COUNT(*) AS count FROM {table_name} WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return int(row["count"]) if row else 0

    def list_sessions(self, mode: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        query = "SELECT * FROM experiment_sessions"
        params: List[Any] = []
        if mode:
            query += " WHERE mode = ?"
            params.append(mode)
        query += " ORDER BY started_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
            results: List[Dict[str, Any]] = []
            for row in rows:
                session = self._row_to_session(row)
                session["turn_count"] = self._count_by_session(conn, "turn_logs", row["id"])
                session["feedback_count"] = self._count_by_session(conn, "feedback_logs", row["id"])
                session["story_event_count"] = self._count_by_session(conn, "story_events", row["id"])
                results.append(session)
        return results

    def list_sessions_for_participant(self, participant_id: str, mode: Optional[str] = None) -> List[Dict[str, Any]]:
        query = "SELECT * FROM experiment_sessions WHERE participant_id = ?"
        params: List[Any] = [participant_id]
        if mode:
            query += " AND mode = ?"
            params.append(mode)
        query += " ORDER BY started_at ASC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_session(row) for row in rows]

    def list_blind_sessions_for_participant(self, participant_id: str, mode: str = "benchmark") -> List[Dict[str, Any]]:
        sessions = self.list_sessions_for_participant(participant_id, mode=mode)
        return [session for session in sessions if session.get("blind_mode")]

    def get_latest_active_blind_session(self, participant_id: str, mode: str = "benchmark") -> Optional[Dict[str, Any]]:
        sessions = self.list_blind_sessions_for_participant(participant_id, mode=mode)
        active_sessions = [session for session in sessions if session.get("status") == "active"]
        return active_sessions[-1] if active_sessions else None

    def count_completed_blind_sessions(self, participant_id: str, mode: str = "benchmark") -> int:
        sessions = self.list_blind_sessions_for_participant(participant_id, mode=mode)
        return sum(1 for session in sessions if session.get("status") == "completed")

    def get_blind_session_progress(self, participant_id: str, mode: str = "benchmark") -> List[Dict[str, Any]]:
        return self.list_blind_sessions_for_participant(participant_id, mode=mode)

    def _list_rows_for_session(
        self,
        table_name: str,
        session_id: str,
        order_by: str,
    ) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM {table_name} WHERE session_id = ? ORDER BY {order_by}",
                (session_id,),
            ).fetchall()
        return [self._export_row(table_name, row) for row in rows]

    def _row_to_session(self, row: sqlite3.Row) -> Dict[str, Any]:
        metadata = json.loads(row["metadata_json"] or "{}")
        selected_model = metadata.get("selected_model")
        condition = self.get_condition(row["condition_id"])
        llm_config_override = self._selected_model_llm_config(selected_model)
        result = dict(row)
        result.pop("metadata_json", None)
        result["session_id"] = row["id"]
        result["metadata"] = metadata
        result["selected_model"] = selected_model
        result["condition"] = condition
        result["llm_config_override"] = llm_config_override
        result["blind_mode"] = bool(metadata.get("blind_mode"))
        result["blind_code"] = metadata.get("blind_code")
        result["blind_slot_index"] = metadata.get("blind_slot_index")
        result["blind_total_slots"] = metadata.get("blind_total_slots")
        result["blind_mapping_version"] = metadata.get("blind_mapping_version")
        result["quick_test_mode"] = bool(metadata.get("quick_test_mode"))
        return result

    def attach_story_to_session(
        self,
        session_id: str,
        story_id: str,
        emotional_need: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        session = self.get_session(session_id)
        if session is None:
            return
        merged_metadata = dict(session.get("metadata") or {})
        merged_metadata.update(metadata or {})
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE experiment_sessions
                SET story_id = ?, emotional_need = COALESCE(?, emotional_need), metadata_json = ?
                WHERE id = ?
                """,
                (
                    story_id,
                    emotional_need,
                    json.dumps(merged_metadata, ensure_ascii=False),
                    session_id,
                ),
            )

    def complete_session(self, session_id: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        session = self.get_session(session_id)
        if session is None:
            return
        merged_metadata = dict(session.get("metadata") or {})
        merged_metadata.update(metadata or {})
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE experiment_sessions
                SET status = ?, completed_at = ?, metadata_json = ?
                WHERE id = ?
                """,
                ("completed", _utcnow(), json.dumps(merged_metadata, ensure_ascii=False), session_id),
            )

    def log_story_event(
        self,
        event_type: str,
        story_id: Optional[str] = None,
        session_id: Optional[str] = None,
        participant_id: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> str:
        event_id = f"event-{uuid.uuid4()}"
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO story_events (id, session_id, participant_id, story_id, event_type, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    session_id,
                    participant_id,
                    story_id,
                    event_type,
                    json.dumps(payload or {}, ensure_ascii=False),
                    _utcnow(),
                ),
            )
        return event_id

    def log_turn(
        self,
        session_id: Optional[str],
        participant_id: Optional[str],
        story_id: str,
        action_type: str,
        user_input: Optional[str],
        response_text: Optional[str],
        choice_id: Optional[str] = None,
        choice_text: Optional[str] = None,
        response_character_id: Optional[str] = None,
        latency_ms: Optional[float] = None,
        llm_config: Optional[Dict[str, Any]] = None,
        model_provider: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        with self._connect() as conn:
            if session_id:
                row = conn.execute(
                    "SELECT COALESCE(MAX(turn_index), 0) + 1 AS next_turn FROM turn_logs WHERE session_id = ?",
                    (session_id,),
                ).fetchone()
                next_turn = int(row["next_turn"])
            else:
                next_turn = 1
            turn_id = f"turn-{uuid.uuid4()}"
            conn.execute(
                """
                INSERT INTO turn_logs
                (id, session_id, participant_id, story_id, turn_index, action_type, user_input, choice_id, choice_text,
                 response_character_id, response_text, latency_ms, model_provider, llm_config_json, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    turn_id,
                    session_id,
                    participant_id,
                    story_id,
                    next_turn,
                    action_type,
                    user_input,
                    choice_id,
                    choice_text,
                    response_character_id,
                    response_text,
                    latency_ms,
                    model_provider,
                    json.dumps(llm_config or {}, ensure_ascii=False),
                    json.dumps(metadata or {}, ensure_ascii=False),
                    _utcnow(),
                ),
            )
        return turn_id

    def save_feedback(
        self,
        feedback_id: str,
        session_id: Optional[str],
        participant_id: Optional[str],
        story_id: Optional[str],
        user_id: Optional[str],
        rating: int,
        feelings: List[str],
        comment: Optional[str],
        feedback_type: Optional[str],
        scores: Optional[Dict[str, int]] = None,
        form_version: Optional[str] = None,
    ) -> Dict[str, Any]:
        with self._connect() as conn:
            created_at = _utcnow()
            existing = None
            if feedback_type == "benchmark_session_end" and session_id:
                existing = conn.execute(
                    """
                    SELECT * FROM feedback_logs
                    WHERE session_id = ? AND feedback_type = ?
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (session_id, feedback_type),
                ).fetchone()

            if existing is not None:
                feedback_id = existing["id"]
                conn.execute(
                    """
                    UPDATE feedback_logs
                    SET participant_id = ?, story_id = ?, user_id = ?, rating = ?, feelings_json = ?, scores_json = ?,
                        comment = ?, form_version = ?, created_at = ?
                    WHERE id = ?
                    """,
                    (
                        participant_id,
                        story_id,
                        user_id,
                        rating,
                        json.dumps(feelings or [], ensure_ascii=False),
                        json.dumps(scores or {}, ensure_ascii=False),
                        comment,
                        form_version,
                        created_at,
                        feedback_id,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO feedback_logs
                    (id, session_id, participant_id, story_id, user_id, rating, feelings_json, scores_json, comment, feedback_type, form_version, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        feedback_id,
                        session_id,
                        participant_id,
                        story_id,
                        user_id,
                        rating,
                        json.dumps(feelings or [], ensure_ascii=False),
                        json.dumps(scores or {}, ensure_ascii=False),
                        comment,
                        feedback_type,
                        form_version,
                        created_at,
                    ),
                )
            row = conn.execute(
                "SELECT * FROM feedback_logs WHERE id = ?",
                (feedback_id,),
            ).fetchone()
        return self._export_row("feedback_logs", row) if row else {"id": feedback_id}

    def log_llm_call(self, payload: Dict[str, Any]) -> str:
        call_id = payload.get("id") or f"llm-{uuid.uuid4()}"
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO llm_call_logs
                (id, session_id, participant_id, story_id, source, task, model_provider, model_name,
                 request_messages_json, response_text, error, latency_ms, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    call_id,
                    payload.get("session_id"),
                    payload.get("participant_id"),
                    payload.get("story_id"),
                    payload.get("source"),
                    payload.get("task"),
                    payload.get("model_provider"),
                    payload.get("model_name"),
                    json.dumps(payload.get("request_messages") or [], ensure_ascii=False),
                    payload.get("response_text"),
                    payload.get("error"),
                    payload.get("latency_ms"),
                    json.dumps(payload.get("metadata") or {}, ensure_ascii=False),
                    payload.get("created_at") or _utcnow(),
                ),
            )
        return call_id

    def list_story_events(self, session_id: str) -> List[Dict[str, Any]]:
        return self._list_rows_for_session("story_events", session_id, "created_at ASC")

    def list_turn_logs(self, session_id: str) -> List[Dict[str, Any]]:
        return self._list_rows_for_session("turn_logs", session_id, "turn_index ASC, created_at ASC")

    def list_feedback_logs(self, session_id: str) -> List[Dict[str, Any]]:
        return self._list_rows_for_session("feedback_logs", session_id, "created_at ASC")

    def list_llm_call_logs(self, session_id: str) -> List[Dict[str, Any]]:
        return self._list_rows_for_session("llm_call_logs", session_id, "created_at ASC")

    def _decode_json_field(
        self,
        row_dict: Dict[str, Any],
        json_key: str,
        target_key: str,
        default: Any,
    ) -> None:
        raw = row_dict.pop(json_key, None)
        if raw in (None, ""):
            row_dict[target_key] = default
            return
        try:
            row_dict[target_key] = json.loads(raw)
        except json.JSONDecodeError:
            row_dict[target_key] = default

    def _export_row(self, table_name: str, row: sqlite3.Row) -> Dict[str, Any]:
        result = dict(row)
        if table_name == "participants":
            self._decode_json_field(result, "metadata_json", "metadata", {})
        elif table_name == "experiment_conditions":
            self._decode_json_field(result, "llm_config_json", "llm_config", {})
            self._decode_json_field(result, "metadata_json", "metadata", {})
            result["active"] = bool(result.get("active", 0))
        elif table_name == "experiment_sessions":
            self._decode_json_field(result, "metadata_json", "metadata", {})
            result["selected_model"] = result["metadata"].get("selected_model")
            result["blind_mode"] = bool(result["metadata"].get("blind_mode"))
            result["blind_code"] = result["metadata"].get("blind_code")
            result["blind_slot_index"] = result["metadata"].get("blind_slot_index")
            result["blind_total_slots"] = result["metadata"].get("blind_total_slots")
            result["blind_mapping_version"] = result["metadata"].get("blind_mapping_version")
        elif table_name == "story_events":
            self._decode_json_field(result, "payload_json", "payload", {})
        elif table_name == "turn_logs":
            self._decode_json_field(result, "llm_config_json", "llm_config", {})
            self._decode_json_field(result, "metadata_json", "metadata", {})
        elif table_name == "feedback_logs":
            self._decode_json_field(result, "feelings_json", "feelings", [])
            self._decode_json_field(result, "scores_json", "scores", {})
        elif table_name == "llm_call_logs":
            self._decode_json_field(result, "request_messages_json", "request_messages", [])
            self._decode_json_field(result, "metadata_json", "metadata", {})
        return result

    def export_table_rows(self, table_name: str) -> List[Dict[str, Any]]:
        allowed = {
            "participants",
            "experiment_conditions",
            "experiment_sessions",
            "story_events",
            "turn_logs",
            "feedback_logs",
            "llm_call_logs",
        }
        if table_name not in allowed:
            raise ValueError(f"Unsupported export table: {table_name}")
        with self._connect() as conn:
            rows = conn.execute(f"SELECT * FROM {table_name} ORDER BY rowid ASC").fetchall()
        return [self._export_row(table_name, row) for row in rows]

    def export_bundle(self) -> Dict[str, Any]:
        return {
            "exported_at": _utcnow(),
            "participants": self.export_table_rows("participants"),
            "conditions": self.export_table_rows("experiment_conditions"),
            "sessions": self.export_table_rows("experiment_sessions"),
            "story_events": self.export_table_rows("story_events"),
            "turn_logs": self.export_table_rows("turn_logs"),
            "feedback_logs": self.export_table_rows("feedback_logs"),
            "llm_call_logs": self.export_table_rows("llm_call_logs"),
        }

    def export_table_csv(self, table_name: str) -> str:
        rows = self.export_table_rows(table_name)
        buffer = io.StringIO()
        if not rows:
            writer = csv.writer(buffer)
            writer.writerow(["empty"])
            writer.writerow(["true"])
            return buffer.getvalue()
        writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
        return buffer.getvalue()
