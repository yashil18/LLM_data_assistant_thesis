"""Shared runtime helpers for faster local and cloud responses."""

from pathlib import Path

import pandas as pd
import streamlit as st
from langchain_community.utilities import SQLDatabase
from sqlalchemy import create_engine


SQL_AGENT_PREFIX = """
You are a data assistant for a fixed SQLite Superstore database.
Use the SQL tools to answer the user's question accurately and concisely.

Known database structure:
- Orders: order dates, customers, products, Category, Sub-Category, Region,
  Sales, Quantity, Discount, and Profit.
- People: Regional Manager and Region.
- Returns: Returned and Order ID.

Work efficiently:
- The schema above is already known. Do not list tables or inspect schemas
  unless the question genuinely requires information not included above.
- Use only the necessary SQL-tool calls.
- Check a query once before executing it.
- Never modify the database.
- Quote column names containing spaces with double quotes.
- Use strftime('%Y', "Order Date") for year filters.
- Use the word "dollars" instead of the dollar sign in final answers.
- Round financial values to two decimal places in final answers.
- If a question is unrelated to the database, say so clearly.

Returned-order rule:
- Count distinct returned Order IDs before joining them to Orders.
- Never use COUNT(*) after joining returned orders to order lines.
- Use this pattern when count and sales are requested:

WITH returned_orders AS (
    SELECT DISTINCT "Order ID"
    FROM Returns
    WHERE "Returned" = 'Yes'
)
SELECT COUNT(DISTINCT r."Order ID") AS distinct_returned_orders,
       SUM(o."Sales") AS total_returned_sales
FROM returned_orders r
JOIN Orders o ON r."Order ID" = o."Order ID";

Return a clear, user-friendly answer based only on the database results.
"""


SQL_AGENT_SUFFIX = """
Use the fewest necessary tool calls, execute the relevant SQL query, and return
the final answer in concise natural language.
"""


@st.cache_resource(show_spinner=False)
def load_sql_database(database_path, excel_path):
    """Open the bundled SQLite database, creating it only when it is missing."""
    database_path = Path(database_path).resolve()
    excel_path = Path(excel_path).resolve()

    if not database_path.exists():
        with create_engine(
            f"sqlite:///{database_path.as_posix()}"
        ).begin() as connection:
            workbook = pd.ExcelFile(excel_path)
            for sheet_name in workbook.sheet_names:
                workbook.parse(sheet_name).to_sql(
                    sheet_name,
                    connection,
                    index=False,
                    if_exists="replace",
                )

    engine = create_engine(
        f"sqlite:///{database_path.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    return SQLDatabase(engine)


def _tool_value(tool_input, key):
    if isinstance(tool_input, dict):
        return tool_input.get(key, "")
    return str(tool_input or "")


def _compact_result(result, max_length=700):
    text = " ".join(str(result).split())
    if len(text) <= max_length:
        return text
    return text[: max_length - 3].rstrip() + "..."


def format_sql_explanation(steps):
    """Create a readable explanation without another LLM request."""
    explanation_steps = []

    for action, result in steps:
        tool = getattr(action, "tool", "")
        tool_input = getattr(action, "tool_input", {})

        if tool == "sql_db_list_tables":
            explanation_steps.append(
                "I checked which database tables were available. "
                f"The database returned: `{_compact_result(result, 250)}`"
            )
        elif tool == "sql_db_schema":
            table_names = _tool_value(tool_input, "table_names") or "the relevant tables"
            explanation_steps.append(
                f"I checked the structure of `{table_names}` to identify the "
                "columns needed for the question."
            )
        elif tool == "sql_db_query_checker":
            explanation_steps.append(
                "I checked the SQL query for mistakes before running it."
            )
        elif tool == "sql_db_query":
            query = _tool_value(tool_input, "query")
            result_text = _compact_result(result)
            explanation_steps.append(
                "I ran the following SQL query:\n\n"
                f"```sql\n{query}\n```\n\n"
                f"The database returned: `{result_text}`"
            )

    if not explanation_steps:
        return (
            "The assistant answered directly and did not need additional "
            "database-query steps."
        )

    return "\n\n".join(
        f"**Step {index}:**\n\n{text}"
        for index, text in enumerate(explanation_steps, start=1)
    )
