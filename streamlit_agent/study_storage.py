"""Shared storage helpers for local and deployed study results.

Locally, the app stores results in interactions.db as before. For deployment,
set a hosted database URL in Streamlit secrets:

    study_database_url = "postgresql://..."
"""

import os
from functools import lru_cache

import pandas as pd
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError, ProgrammingError


DEFAULT_STUDY_DATABASE_URL = "sqlite:///interactions.db"


INTERACTION_COLUMNS = {
    "participant_id": "TEXT",
    "treatment": "TEXT",
    "assistant_version": "TEXT",
    "explanation_displayed_time": "TIMESTAMP",
}


STUDY_SESSION_COLUMNS = {
    "consent_given": "INTEGER",
    "consent_version": "TEXT",
    "consent_timestamp": "TIMESTAMP",
}


def _read_streamlit_secret(name):
    try:
        import streamlit as st

        return st.secrets.get(name)
    except Exception:
        return None


def get_study_database_url():
    """Return the configured study-results database URL."""
    return (
        _read_streamlit_secret("study_database_url")
        or os.getenv("STUDY_DATABASE_URL")
        or os.getenv("DATABASE_URL")
        or DEFAULT_STUDY_DATABASE_URL
    )


def _normalize_database_url(database_url):
    """Make common hosted Postgres URLs SQLAlchemy-friendly."""
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+psycopg2://", 1)
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return database_url


@lru_cache(maxsize=4)
def get_study_engine(database_url=None):
    database_url = _normalize_database_url(database_url or get_study_database_url())
    engine_options = {"pool_pre_ping": True}
    if database_url.startswith("sqlite"):
        engine_options["connect_args"] = {"check_same_thread": False}
    return create_engine(database_url, **engine_options)


def _existing_columns(engine, table_name):
    try:
        return {column["name"] for column in inspect(engine).get_columns(table_name)}
    except Exception:
        return set()


def _ensure_columns(engine, table_name, required_columns):
    existing_columns = _existing_columns(engine, table_name)
    missing_columns = [
        (column_name, column_type)
        for column_name, column_type in required_columns.items()
        if column_name not in existing_columns
    ]
    if not missing_columns:
        return

    with engine.begin() as connection:
        for column_name, column_type in missing_columns:
            connection.execute(
                text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
            )


def _execute_schema_statement(engine, sql, table_to_verify=None):
    """Run DDL safely when cloud deployment starts more than one app worker."""
    try:
        with engine.begin() as connection:
            connection.execute(text(sql))
    except (IntegrityError, ProgrammingError):
        if table_to_verify and table_to_verify in inspect(engine).get_table_names():
            return
        raise


@lru_cache(maxsize=1)
def initialize_interactions_database():
    engine = get_study_engine()
    _execute_schema_statement(
        engine,
        """
        CREATE TABLE IF NOT EXISTS interactions (
            session_id TEXT,
            id INTEGER,
            participant_id TEXT,
            treatment TEXT,
            assistant_version TEXT,
            user_query TEXT,
            assistant_response TEXT,
            intermediate_steps TEXT,
            simplified_intermediate_steps TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            user_query_sent_time TIMESTAMP,
            response_displayed_time TIMESTAMP,
            explanation_button_displayed_time TIMESTAMP,
            explanation_clicked_time TIMESTAMP,
            explanation_clicked BOOLEAN DEFAULT FALSE,
            explanation_displayed_time TIMESTAMP
        )
        """,
        table_to_verify="interactions",
    )
    _execute_schema_statement(
        engine,
        """
        CREATE INDEX IF NOT EXISTS idx_interactions_session_question
        ON interactions (session_id, id)
        """,
        table_to_verify="interactions",
    )
    _ensure_columns(engine, "interactions", INTERACTION_COLUMNS)


@lru_cache(maxsize=1)
def initialize_questionnaire_database():
    engine = get_study_engine()
    _execute_schema_statement(
        engine,
        """
        CREATE TABLE IF NOT EXISTS study_sessions (
            session_id TEXT PRIMARY KEY,
            participant_id TEXT NOT NULL,
            assistant_version TEXT NOT NULL,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            pre_completed_at TIMESTAMP,
            tasks_completed_at TIMESTAMP,
            post_completed_at TIMESTAMP,
            consent_given INTEGER,
            consent_version TEXT,
            consent_timestamp TIMESTAMP
        )
        """,
        table_to_verify="study_sessions",
    )
    _execute_schema_statement(
        engine,
        """
        CREATE TABLE IF NOT EXISTS questionnaire_responses (
            session_id TEXT NOT NULL,
            participant_id TEXT NOT NULL,
            assistant_version TEXT NOT NULL,
            phase TEXT NOT NULL,
            question_id TEXT NOT NULL,
            construct TEXT NOT NULL,
            response_numeric REAL,
            response_text TEXT,
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (session_id, phase, question_id)
        )
        """,
        table_to_verify="questionnaire_responses",
    )
    _ensure_columns(engine, "study_sessions", STUDY_SESSION_COLUMNS)


def _format_timestamp(value):
    if value is None:
        return None
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value)


def insert_interaction(
    session_id,
    question_id,
    participant_id,
    treatment,
    assistant_version,
    user_query,
    assistant_response,
    intermediate_steps,
    simplified_intermediate_steps,
    user_query_sent_time,
    response_displayed_time,
    explanation_button_displayed_time,
    explanation_clicked_time,
    explanation_clicked,
    explanation_displayed_time,
):
    initialize_interactions_database()
    params = {
        "session_id": session_id,
        "id": question_id,
        "participant_id": participant_id,
        "treatment": treatment,
        "assistant_version": assistant_version,
        "user_query": user_query,
        "assistant_response": assistant_response,
        "intermediate_steps": str(intermediate_steps),
        "simplified_intermediate_steps": str(simplified_intermediate_steps),
        "user_query_sent_time": _format_timestamp(user_query_sent_time),
        "response_displayed_time": _format_timestamp(response_displayed_time),
        "explanation_button_displayed_time": _format_timestamp(
            explanation_button_displayed_time
        ),
        "explanation_clicked_time": _format_timestamp(explanation_clicked_time),
        "explanation_clicked": bool(explanation_clicked) if explanation_clicked else False,
        "explanation_displayed_time": _format_timestamp(explanation_displayed_time),
    }
    with get_study_engine().begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO interactions (
                    session_id, id, participant_id, treatment, assistant_version,
                    user_query, assistant_response, intermediate_steps,
                    simplified_intermediate_steps, user_query_sent_time,
                    response_displayed_time, explanation_button_displayed_time,
                    explanation_clicked_time, explanation_clicked,
                    explanation_displayed_time
                )
                VALUES (
                    :session_id, :id, :participant_id, :treatment, :assistant_version,
                    :user_query, :assistant_response, :intermediate_steps,
                    :simplified_intermediate_steps, :user_query_sent_time,
                    :response_displayed_time, :explanation_button_displayed_time,
                    :explanation_clicked_time, :explanation_clicked,
                    :explanation_displayed_time
                )
                """
            ),
            params,
        )


def update_explanation_clicked(session_id, interaction_id):
    initialize_interactions_database()
    with get_study_engine().begin() as connection:
        connection.execute(
            text(
                """
                UPDATE interactions
                SET explanation_clicked = TRUE,
                    explanation_clicked_time = CURRENT_TIMESTAMP,
                    explanation_displayed_time = CURRENT_TIMESTAMP
                WHERE session_id = :session_id AND id = :interaction_id
                """
            ),
            {"session_id": session_id, "interaction_id": interaction_id},
        )


def upsert_study_session(session_id, participant_id, assistant_version, consent_version):
    initialize_questionnaire_database()
    with get_study_engine().begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO study_sessions (
                    session_id, participant_id, assistant_version, started_at,
                    consent_given, consent_version, consent_timestamp
                )
                VALUES (
                    :session_id, :participant_id, :assistant_version,
                    CURRENT_TIMESTAMP, 1, :consent_version, CURRENT_TIMESTAMP
                )
                ON CONFLICT (session_id) DO UPDATE SET
                    participant_id = excluded.participant_id,
                    assistant_version = excluded.assistant_version,
                    consent_given = excluded.consent_given,
                    consent_version = excluded.consent_version,
                    consent_timestamp = excluded.consent_timestamp
                """
            ),
            {
                "session_id": session_id,
                "participant_id": participant_id,
                "assistant_version": assistant_version,
                "consent_version": consent_version,
            },
        )


def insert_questionnaire_responses(
    session_id,
    participant_id,
    assistant_version,
    phase,
    responses,
):
    initialize_questionnaire_database()
    rows = []
    for question_id, response in responses.items():
        value = response["value"]
        numeric_value = value if isinstance(value, (int, float)) else None
        text_value = None if numeric_value is not None else str(value)
        rows.append(
            {
                "session_id": session_id,
                "participant_id": participant_id,
                "assistant_version": assistant_version,
                "phase": phase,
                "question_id": question_id,
                "construct": response["construct"],
                "response_numeric": numeric_value,
                "response_text": text_value,
            }
        )

    with get_study_engine().begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO questionnaire_responses (
                    session_id, participant_id, assistant_version, phase,
                    question_id, construct, response_numeric, response_text,
                    submitted_at
                )
                VALUES (
                    :session_id, :participant_id, :assistant_version, :phase,
                    :question_id, :construct, :response_numeric, :response_text,
                    CURRENT_TIMESTAMP
                )
                ON CONFLICT (session_id, phase, question_id) DO UPDATE SET
                    participant_id = excluded.participant_id,
                    assistant_version = excluded.assistant_version,
                    construct = excluded.construct,
                    response_numeric = excluded.response_numeric,
                    response_text = excluded.response_text,
                    submitted_at = CURRENT_TIMESTAMP
                """
            ),
            rows,
        )


def has_previous_pre_questionnaire(participant_id):
    initialize_questionnaire_database()
    with get_study_engine().connect() as connection:
        result = connection.execute(
            text(
                """
                SELECT 1
                FROM questionnaire_responses
                WHERE participant_id = :participant_id AND phase = 'pre'
                LIMIT 1
                """
            ),
            {"participant_id": participant_id},
        ).fetchone()
    return result is not None


def update_study_session(session_id, **fields):
    if not fields:
        return

    allowed_fields = {
        "pre_completed_at",
        "tasks_completed_at",
        "post_completed_at",
        "consent_given",
        "consent_version",
        "consent_timestamp",
    }
    invalid_fields = set(fields) - allowed_fields
    if invalid_fields:
        raise ValueError(f"Unsupported study session fields: {sorted(invalid_fields)}")

    assignments = ", ".join(f"{field} = :{field}" for field in fields)
    params = dict(fields)
    params["session_id"] = session_id
    initialize_questionnaire_database()
    with get_study_engine().begin() as connection:
        connection.execute(
            text(f"UPDATE study_sessions SET {assignments} WHERE session_id = :session_id"),
            params,
        )


def read_study_table(table_name, database_url=None):
    if table_name not in {"study_sessions", "questionnaire_responses", "interactions"}:
        raise ValueError(f"Unsupported table: {table_name}")

    engine = get_study_engine(database_url)
    if table_name not in inspect(engine).get_table_names():
        return pd.DataFrame()

    with engine.connect() as connection:
        return pd.read_sql_query(text(f"SELECT * FROM {table_name}"), connection)
