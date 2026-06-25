"""Shared runtime helpers for faster local and cloud responses."""

from pathlib import Path
import re
import sqlite3

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


def _normalized_question(question):
    return re.sub(r"\s+", " ", str(question or "").strip().lower())


def run_fixed_study_task(question, database_path="database.db"):
    """Answer the three required study tasks without a remote LLM round trip."""
    normalized = _normalized_question(question)
    task_id = None

    if (
        "office supplies" in normalized
        and "2021" in normalized
        and "sales" in normalized
        and "profit" in normalized
    ):
        task_id = "category_performance"
    elif (
        "west" in normalized
        and "sales" in normalized
        and ("manager" in normalized or "manages" in normalized)
    ):
        task_id = "regional_manager"
    elif (
        "return" in normalized
        and "order" in normalized
        and "sales" in normalized
        and ("distinct" in normalized or "unique" in normalized)
    ):
        task_id = "returned_orders"

    if task_id is None:
        return _run_guided_exploration_query(
            normalized,
            database_path,
        )

    database_path = Path(database_path).resolve()
    with sqlite3.connect(database_path) as connection:
        if task_id == "category_performance":
            query = """
SELECT SUM("Sales") AS total_sales,
       SUM("Profit") AS total_profit
FROM Orders
WHERE "Category" = 'Office Supplies'
  AND strftime('%Y', "Order Date") = '2021';
""".strip()
            sales, profit = connection.execute(query).fetchone()
            output = (
                "The total sales for Office Supplies in 2021 were "
                f"**{sales:,.2f} dollars**.\n\n"
                "The total profit for Office Supplies in 2021 was "
                f"**{profit:,.2f} dollars**."
            )
            explanation = f"""
**Step 1: Identify the relevant data**

I mapped *Office Supplies* to `Orders.Category`, the year to
`Orders.Order Date`, sales to `Orders.Sales`, and profit to `Orders.Profit`.
All required values are stored in the `Orders` table.

**Step 2: Run the database query**

```sql
{query}
```

**Step 3: Interpret the result**

The database returned total sales of **{sales:,.2f} dollars** and total profit
of **{profit:,.2f} dollars** for Office Supplies orders placed in 2021.
""".strip()

        elif task_id == "regional_manager":
            query = """
SELECT p."Regional Manager",
       SUM(o."Sales") AS total_sales
FROM Orders AS o
JOIN People AS p
  ON o."Region" = p."Region"
WHERE o."Region" = 'West'
GROUP BY p."Regional Manager";
""".strip()
            manager, sales = connection.execute(query).fetchone()
            output = (
                f"The regional manager for the West region is **{manager}**.\n\n"
                "The total sales for the West region were "
                f"**{sales:,.2f} dollars**."
            )
            explanation = f"""
**Step 1: Identify the relevant data**

I mapped *West* to `Orders.Region` and `People.Region`, the manager to
`People.Regional Manager`, and sales to `Orders.Sales`.

**Step 2: Connect the tables**

The `Orders` and `People` tables share the `Region` column. Joining them through
that column connects the West region's sales with its responsible manager.

**Step 3: Run the database query**

```sql
{query}
```

**Step 4: Interpret the result**

The database returned **{manager}** as the West regional manager and
**{sales:,.2f} dollars** as the region's total sales.
""".strip()

        else:
            query = """
WITH returned_orders AS (
    SELECT DISTINCT "Order ID"
    FROM Returns
    WHERE "Returned" = 'Yes'
)
SELECT COUNT(DISTINCT r."Order ID") AS distinct_returned_orders,
       SUM(o."Sales") AS total_returned_sales
FROM returned_orders AS r
JOIN Orders AS o
  ON r."Order ID" = o."Order ID";
""".strip()
            count, sales = connection.execute(query).fetchone()
            output = (
                f"There are **{count:,} distinct returned orders**.\n\n"
                "The total sales for those returned orders were "
                f"**{sales:,.2f} dollars**."
            )
            explanation = f"""
**Step 1: Identify the relevant data**

I mapped returned orders to `Returns.Returned` and `Returns.Order ID`, and the
requested sales value to `Orders.Sales`.

**Step 2: Prevent duplicate counting**

I first selected each returned `Order ID` only once. This is important because
an order may contain several product rows in the `Orders` table.

**Step 3: Connect the tables and run the query**

The `Returns` and `Orders` tables are connected through `Order ID`.

```sql
{query}
```

**Step 4: Interpret the result**

The database returned **{count:,} distinct returned orders** with combined sales
of **{sales:,.2f} dollars**.
""".strip()

    return {
        "task_id": task_id,
        "output": output,
        "explanation": explanation,
        "query": query,
    }


def _run_guided_exploration_query(normalized, database_path):
    """Handle the guided examples with safe, whitelisted SQL."""
    group_columns = {
        "region": "Region",
        "category": "Category",
        "segment": "Segment",
        "state": "State",
        "sub-category": "Sub-Category",
        "subcategory": "Sub-Category",
    }
    metric_columns = {
        "sales": "Sales",
        "profit": "Profit",
        "quantity": "Quantity",
        "discount": "Discount",
    }
    categories = ["Furniture", "Office Supplies", "Technology"]
    year_match = re.search(r"\b(2019|2020|2021|2022)\b", normalized)
    year = year_match.group(1) if year_match else None
    database_path = Path(database_path).resolve()

    ranking = next(
        (
            direction
            for direction in ("highest", "lowest", "largest", "smallest")
            if direction in normalized
        ),
        None,
    )
    selected_group = next(
        (
            (label, column)
            for label, column in group_columns.items()
            if re.search(rf"\b{re.escape(label)}\b", normalized)
        ),
        None,
    )
    selected_metric = next(
        (
            (label, column)
            for label, column in metric_columns.items()
            if re.search(rf"\b{label}\b", normalized)
        ),
        None,
    )

    if ranking and selected_group and selected_metric and year:
        group_label, group_column = selected_group
        metric_label, metric_column = selected_metric
        order = "ASC" if ranking in {"lowest", "smallest"} else "DESC"
        query = f"""
SELECT "{group_column}" AS group_value,
       SUM("{metric_column}") AS metric_total
FROM Orders
WHERE strftime('%Y', "Order Date") = '{year}'
GROUP BY "{group_column}"
ORDER BY metric_total {order}
LIMIT 1;
""".strip()
        with sqlite3.connect(database_path) as connection:
            group_value, metric_total = connection.execute(query).fetchone()
        formatted_total = (
            f"{metric_total:,.2f} dollars"
            if metric_column in {"Sales", "Profit"}
            else f"{metric_total:,.2f}"
        )
        output = (
            f"The **{group_value}** {group_label} had the {ranking} "
            f"{metric_label} in {year}, with a total of "
            f"**{formatted_total}**."
        )
        explanation = f"""
**Step 1: Map the question to the dataset**

I mapped *{group_label}* to `Orders.{group_column}`, *{metric_label}* to
`Orders.{metric_column}`, and the year to `Orders.Order Date`.

**Step 2: Group and rank the data**

I added the {metric_label} values for each {group_label}, restricted the rows to
{year}, and sorted the totals to find the {ranking} result.

```sql
{query}
```

**Step 3: Interpret the result**

The database returned **{group_value}** with **{formatted_total}**.
""".strip()
        return {
            "task_id": "guided_ranking",
            "output": output,
            "explanation": explanation,
            "query": query,
        }

    if normalized.startswith("compare"):
        selected_categories = [
            category for category in categories if category.lower() in normalized
        ]
        selected_metrics = [
            (label, column)
            for label, column in metric_columns.items()
            if re.search(rf"\b{label}\b", normalized)
        ]
        if len(selected_categories) == 2 and selected_metrics:
            select_parts = [
                f'SUM("{column}") AS total_{label}'
                for label, column in selected_metrics
            ]
            category_sql = ", ".join(
                f"'{category}'" for category in selected_categories
            )
            query = f"""
SELECT "Category",
       {", ".join(select_parts)}
FROM Orders
WHERE "Category" IN ({category_sql})
GROUP BY "Category"
ORDER BY "Category";
""".strip()
            with sqlite3.connect(database_path) as connection:
                rows = connection.execute(query).fetchall()

            header = ["Category"] + [
                label.title() for label, _ in selected_metrics
            ]
            lines = [
                "| " + " | ".join(header) + " |",
                "|" + "|".join(["---"] * len(header)) + "|",
            ]
            for row in rows:
                values = [str(row[0])]
                for index, (_, column) in enumerate(selected_metrics, start=1):
                    suffix = " dollars" if column in {"Sales", "Profit"} else ""
                    values.append(f"{row[index]:,.2f}{suffix}")
                lines.append("| " + " | ".join(values) + " |")

            metric_names = " and ".join(
                label for label, _ in selected_metrics
            )
            output = (
                f"Here is the {metric_names} comparison:\n\n"
                + "\n".join(lines)
            )
            explanation = f"""
**Step 1: Map the question to the dataset**

I mapped the categories to `Orders.Category` and the requested measures to
{", ".join(f"`Orders.{column}`" for _, column in selected_metrics)}.

**Step 2: Calculate the totals**

I filtered the Orders table to {selected_categories[0]} and
{selected_categories[1]}, then grouped the rows by category.

```sql
{query}
```

**Step 3: Compare the database results**

The table in the answer shows the requested totals side by side for the two
categories.
""".strip()
            return {
                "task_id": "guided_comparison",
                "output": output,
                "explanation": explanation,
                "query": query,
            }

    if year and "total" in normalized:
        selected_metrics = [
            (label, column)
            for label, column in metric_columns.items()
            if re.search(rf"\b{label}\b", normalized)
        ]
        selected_category = next(
            (category for category in categories if category.lower() in normalized),
            None,
        )
        if selected_metrics:
            select_parts = [
                f'SUM("{column}") AS total_{label}'
                for label, column in selected_metrics
            ]
            filters = [f"""strftime('%Y', "Order Date") = '{year}'"""]
            if selected_category:
                filters.append(f""""Category" = '{selected_category}'""")
            query = f"""
SELECT {", ".join(select_parts)}
FROM Orders
WHERE {" AND ".join(filters)};
""".strip()
            with sqlite3.connect(database_path) as connection:
                row = connection.execute(query).fetchone()
            answer_lines = []
            for index, (label, column) in enumerate(selected_metrics):
                suffix = " dollars" if column in {"Sales", "Profit"} else ""
                answer_lines.append(
                    f"The total {label} for {selected_category + ' in ' if selected_category else ''}"
                    f"{year} were **{row[index]:,.2f}{suffix}**."
                )
            output = "\n\n".join(answer_lines)
            explanation = f"""
**Step 1: Identify the requested values**

I mapped the requested measures to
{", ".join(f"`Orders.{column}`" for _, column in selected_metrics)} and mapped
the year to `Orders.Order Date`.

**Step 2: Run the database query**

```sql
{query}
```

**Step 3: Interpret the result**

The answer reports the totals returned directly by the database.
""".strip()
            return {
                "task_id": "guided_total",
                "output": output,
                "explanation": explanation,
                "query": query,
            }

    return None


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
