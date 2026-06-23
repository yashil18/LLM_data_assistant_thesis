"""
Lightweight knowledge graph for the Superstore data assistant.

The graph models the most important business concepts, database tables,
columns, and relationships used by the assistant.
"""

import json
import re

KG_NODES = {
    "Orders": "Main table with order, customer, product, location, sales, profit, quantity, and discount data.",
    "People": "Table with regional managers and their regions.",
    "Returns": "Table with returned orders and their order IDs.",
    "Sales": "Financial metric stored in Orders.Sales.",
    "Profit": "Financial metric stored in Orders.Profit.",
    "Quantity": "Number of sold items stored in Orders.Quantity.",
    "Discount": "Discount value stored in Orders.Discount.",
    "Customer": "Customer information stored in Orders.Customer ID, Customer Name, and Segment.",
    "Product": "Product information stored in Orders.Product ID, Product Name, Category, and Sub-Category.",
    "Location": "Location information stored in Orders.Country/Region, City, State, and Region.",
    "Date": "Time information stored in Orders.Order Date and Orders.Ship Date.",
    "Region": "Business region stored in Orders.Region and People.Region.",
    "Returned Order": "Return information stored in Returns.Returned and Returns.Order ID.",
}

KG_EDGES = [
    ("Orders", "contains metric", "Sales", "Sales is stored in the Orders table."),
    ("Orders", "contains metric", "Profit", "Profit is stored in the Orders table."),
    ("Orders", "contains metric", "Quantity", "Quantity is stored in the Orders table."),
    ("Orders", "contains metric", "Discount", "Discount is stored in the Orders table."),
    ("Orders", "contains concept", "Customer", "Customer information is stored in the Orders table."),
    ("Orders", "contains concept", "Product", "Product information is stored in the Orders table."),
    ("Orders", "contains concept", "Location", "Location information is stored in the Orders table."),
    ("Orders", "contains concept", "Date", "Order and shipping dates are stored in the Orders table."),
    ("Orders", "has region", "Region", "Orders.Region identifies the business region."),
    ("People", "has region", "Region", "People.Region identifies the manager's region."),
    ("Orders", "joins People through", "Region", "Orders can be joined with People using Region."),
    ("Orders", "joins Returns through", "Returned Order", "Orders can be joined with Returns using Order ID."),
]

KEYWORD_TO_NODES = {
    "sale": ["Orders", "Sales"],
    "sales": ["Orders", "Sales"],
    "revenue": ["Orders", "Sales"],
    "profit": ["Orders", "Profit"],
    "quantity": ["Orders", "Quantity"],
    "discount": ["Orders", "Discount"],
    "customer": ["Orders", "Customer"],
    "segment": ["Orders", "Customer"],
    "product": ["Orders", "Product"],
    "category": ["Orders", "Product"],
    "sub-category": ["Orders", "Product"],
    "region": ["Orders", "People", "Region", "Location"],
    "manager": ["People", "Region"],
    "state": ["Orders", "Location"],
    "city": ["Orders", "Location"],
    "country": ["Orders", "Location"],
    "return": ["Orders", "Returns", "Returned Order"],
    "returned": ["Orders", "Returns", "Returned Order"],
    "order": ["Orders"],
    "date": ["Orders", "Date"],
    "year": ["Orders", "Date"],
    "month": ["Orders", "Date"],
    "ship": ["Orders", "Date"],
}

VALUE_TO_NODES = {
    "office supplies": ["Orders", "Product"],
    "furniture": ["Orders", "Product"],
    "technology": ["Orders", "Product"],
}

USER_FRIENDLY_MAPPINGS = {
    "Orders": "Orders table -> stores order lines, sales, profit, customers, products, locations, and dates",
    "Sales": "Sales value -> Orders.Sales",
    "Profit": "Profit value -> Orders.Profit",
    "Quantity": "Number of items sold -> Orders.Quantity",
    "Discount": "Discount value -> Orders.Discount",
    "Customer": "Customer information -> Orders.Customer ID, Orders.Customer Name, and Orders.Segment",
    "Product": "Product information -> Orders.Product ID, Orders.Product Name, Orders.Category, and Orders.Sub-Category",
    "Location": "Location information -> Orders.Country/Region, Orders.City, Orders.State, and Orders.Region",
    "Date": "Time period -> Orders.Order Date or Orders.Ship Date",
    "Region": "Business region -> Orders.Region and People.Region",
    "People": "Regional manager -> People.Regional Manager",
    "Returned Order": "Returned order -> Returns.Order ID",
    "Returns": "Return status -> Returns.Returned",
}

USER_FRIENDLY_RELATIONSHIPS = {
    ("Orders", "joins People through", "Region"): (
        "Orders and People are connected through Region, so regional sales can be linked to the responsible manager."
    ),
    ("Orders", "joins Returns through", "Returned Order"): (
        "Orders and Returns are connected through Order ID, so returned orders can be linked to their sales values."
    ),
    ("Orders", "contains metric", "Sales"): "The requested sales value is stored in the Orders table.",
    ("Orders", "contains metric", "Profit"): "The requested profit value is stored in the Orders table.",
    ("People", "has region", "Region"): "The People table uses Region to assign managers to regions.",
    ("Orders", "has region", "Region"): "The Orders table uses Region to group orders by business region.",
}


REGION_VALUES = ["central", "east", "south", "west"]


def _find_year(question_text):
    match = re.search(r"\b(19|20)\d{2}\b", question_text)
    return match.group(0) if match else None


def _find_region_value(question_text):
    for region in REGION_VALUES:
        if re.search(rf"\b{re.escape(region)}\b", question_text):
            return region.title()
    return None


def _find_product_value(question_text):
    for value in VALUE_TO_NODES:
        if value in question_text:
            return value.title()
    return None


def find_relevant_nodes(question):
    text = question.lower()
    relevant_nodes = set()

    for keyword, nodes in KEYWORD_TO_NODES.items():
        if keyword in text:
            relevant_nodes.update(nodes)

    for value, nodes in VALUE_TO_NODES.items():
        if value in text:
            relevant_nodes.update(nodes)

    if re.search(r"\b(19|20)\d{2}\b", text):
        relevant_nodes.update(["Orders", "Date"])

    if not relevant_nodes:
        relevant_nodes.update(["Orders", "Sales", "Profit"])

    return sorted(relevant_nodes)


def find_relevant_edges(nodes):
    node_set = set(nodes)
    relevant_edges = []

    for source, relation, target, explanation in KG_EDGES:
        if source in node_set and target in node_set:
            relevant_edges.append((source, relation, target, explanation))

    return relevant_edges


def get_kg_context(question):
    nodes = find_relevant_nodes(question)
    edges = find_relevant_edges(nodes)

    lines = [
        "Knowledge graph context:",
        "Relevant business concepts and database mapping:",
    ]

    for node in nodes:
        lines.append(f"- {node}: {KG_NODES[node]}")

    lines.append("")
    lines.append("Relevant graph relationships:")

    for source, relation, target, explanation in edges:
        lines.append(f"- {source} --{relation}--> {target}. {explanation}")

    lines.append("")
    lines.append("SQL guidance:")
    lines.append("- Use the Orders table for sales, profit, quantity, discount, customer, product, location, and date questions.")
    lines.append("- Join Orders with People through Region when the question asks about regional managers.")
    lines.append("- For returned-order questions, select distinct Order ID values from Returns before joining to Orders.")
    lines.append("- For returned-order count plus sales questions, use COUNT(DISTINCT r.\"Order ID\") after joining. Do not use COUNT(*), because Orders can contain multiple rows per order.")
    lines.append("- Correct returned-order pattern: WITH returned_orders AS (SELECT DISTINCT \"Order ID\" FROM Returns WHERE \"Returned\" = 'Yes') SELECT COUNT(DISTINCT r.\"Order ID\"), SUM(o.\"Sales\") FROM returned_orders r JOIN Orders o ON r.\"Order ID\" = o.\"Order ID\".")
    lines.append("- Use double quotes around column names with spaces, for example \"Order Date\" or \"Customer Name\".")

    return "\n".join(lines)


def get_kg_explanation(question):
    nodes = find_relevant_nodes(question)
    node_set = set(nodes)
    question_text = question.lower()
    year = _find_year(question_text)
    region_value = _find_region_value(question_text)
    product_value = _find_product_value(question_text)

    explanation = [
        "I used the knowledge graph to translate the question into the dataset before creating the SQL query.",
        "",
        "**1. Words from the question mapped to the dataset**",
    ]

    mappings = []

    if "Sales" in node_set:
        mappings.append(
            ":blue[sales] -> `Orders.Sales` because this column stores sales amounts."
        )
    if "Profit" in node_set:
        mappings.append(
            ":green[profit] -> `Orders.Profit` because this column stores profit amounts."
        )
    if "Quantity" in node_set:
        mappings.append(
            ":orange[quantity] -> `Orders.Quantity` because this column stores the number of sold items."
        )
    if "Discount" in node_set:
        mappings.append(
            ":orange[discount] -> `Orders.Discount` because this column stores discount values."
        )
    if "Date" in node_set:
        time_label = year if year else "time period"
        mappings.append(
            f":violet[{time_label}] -> `Orders.Order Date` because the time filter is taken from the order date."
        )
    if "Product" in node_set:
        product_label = product_value if product_value else "product or category"
        mappings.append(
            f":orange[{product_label}] -> `Orders.Category`, `Orders.Sub-Category`, or `Orders.Product Name` because product groups are stored there."
        )
    if "Region" in node_set:
        region_label = region_value if region_value else "region"
        mappings.append(
            f":violet[{region_label}] -> `Orders.Region` and `People.Region` because region is used in both tables."
        )
    if "People" in node_set:
        mappings.append(
            ":blue[regional manager] -> `People.Regional Manager` because manager names are stored in the People table."
        )
    if "Returned Order" in node_set:
        mappings.append(
            ":red[returned orders] -> `Returns.Order ID` because returned orders are identified by their order ID."
        )
    if "Returns" in node_set:
        mappings.append(
            ":red[return status] -> `Returns.Returned` because this column marks whether an order was returned."
        )

    if not mappings:
        mappings.append(
            "`Orders` table -> the main table for sales, profit, products, customers, regions, and dates."
        )

    explanation.extend(f"- {mapping}" for mapping in mappings)

    explanation.append("")
    explanation.append("**2. How the tables or columns were connected**")

    if {"Orders", "People", "Region"}.issubset(node_set):
        explanation.append(
            "- I connected `Orders.Region` with `People.Region` so the sales from a region can be linked to the responsible manager."
        )
    elif {"Orders", "Returns", "Returned Order"}.issubset(node_set):
        explanation.append(
            "- I connected `Returns.Order ID` with `Orders.Order ID` so returned orders can be linked to their sales values."
        )
    else:
        explanation.append(
            "- No table join was needed because the relevant values are already stored in the `Orders` table."
        )

    if "Returned Order" in nodes:
        explanation.append("")
        explanation.append("**3. Traceability check**")
        explanation.append(
            "- Returned orders are counted by unique `Order ID` first, so repeated order lines do not multiply the returned-order count."
        )
    elif {"People", "Region"}.issubset(node_set):
        explanation.append("")
        explanation.append("**3. Traceability check**")
        explanation.append(
            "- The same region value is used on both sides of the join, so the manager and the sales refer to the same business region."
        )
    else:
        explanation.append("")
        explanation.append("**3. Traceability check**")
        explanation.append(
            "- The answer is based on the mapped columns above, so the path from question wording to database values is visible."
        )

    explanation.append("")
    explanation.append("**Why this helps**")
    explanation.append(
        "- It shows which parts of the question were matched to exact tables and columns before the SQL query was executed."
    )

    return "\n".join(explanation)


def _dot_escape(text):
    return str(text).replace("\\", "\\\\").replace('"', '\\"')


def get_kg_graphviz(question):
    nodes = find_relevant_nodes(question)
    edges = find_relevant_edges(nodes)

    node_ids = {}
    node_defs = {}
    edge_defs = []

    def add_node(label, layer, fill="#dbeafe", shape="ellipse"):
        if label not in node_ids:
            node_id = f"n{len(node_ids)}"
            node_ids[label] = node_id
            node_defs[label] = {
                "id": node_id,
                "label": label,
                "layer": layer,
                "fill": fill,
                "shape": shape,
            }
        return node_ids[label]

    def add_edge(source, target, label):
        source_id = node_ids[source]
        target_id = node_ids[target]
        edge_defs.append((source_id, target_id, label))

    add_node("User\nquestion", "concept", fill="#ffe89a")

    concept_to_columns = {
        "Sales": ("Sales", ["Orders.Sales"]),
        "Profit": ("Profit", ["Orders.Profit"]),
        "Quantity": ("Quantity", ["Orders.Quantity"]),
        "Discount": ("Discount", ["Orders.Discount"]),
        "Customer": ("Customer", ["Orders.Customer ID", "Orders.Customer Name", "Orders.Segment"]),
        "Product": ("Product /\ncategory", ["Orders.Category", "Orders.Sub-Category", "Orders.Product Name"]),
        "Location": ("Location", ["Orders.Region", "Orders.State", "Orders.City"]),
        "Date": ("Time\nperiod", ["Orders.Order Date", "Orders.Ship Date"]),
        "Region": ("Region", ["Orders.Region", "People.Region"]),
        "People": ("Regional\nmanager", ["People.Regional Manager"]),
        "Returned Order": ("Returned\norder", ["Returns.Order ID"]),
        "Returns": ("Return\nstatus", ["Returns.Returned"]),
    }

    for node in nodes:
        if node in concept_to_columns:
            concept_label, columns = concept_to_columns[node]
            add_node(concept_label, "concept", fill="#dbeafe")
            add_edge("User\nquestion", concept_label, "asks about")
            for column in columns:
                add_node(column, "data", fill="#dff6e4")
                add_edge(concept_label, column, "mapped to")
        elif node in ["Orders", "People", "Returns"]:
            table_label = f"{node}\ntable"
            add_node(table_label, "data", fill="#d7cbb8")
            add_edge("User\nquestion", table_label, "uses")

    for source, relation, target, _ in edges:
        if source == "Orders" and relation == "joins People through" and target == "Region":
            add_node("Orders.Region", "data", fill="#dff6e4")
            add_node("People.Region", "data", fill="#dff6e4")
            add_edge("Orders.Region", "People.Region", "same region")
        elif source == "Orders" and relation == "joins Returns through" and target == "Returned Order":
            add_node("Returns.Order ID", "data", fill="#dff6e4")
            add_node("Orders.Order ID", "data", fill="#dff6e4")
            add_edge("Returns.Order ID", "Orders.Order ID", "same ID")

    if "Returned Order" in nodes:
        add_node("Distinct\nreturned orders", "data", fill="#e5f1ff")
        add_node("Total sales for\nreturned orders", "data", fill="#e5f1ff")
        add_node("Returns.Order ID", "data", fill="#dff6e4")
        add_node("Orders.Sales", "data", fill="#dff6e4")
        add_edge("Returns.Order ID", "Distinct\nreturned orders", "count unique")
        add_edge("Orders.Sales", "Total sales for\nreturned orders", "sum sales")

    if "People" in nodes and "Region" in nodes:
        add_node("Manager for\nselected region", "data", fill="#e5f1ff")
        add_node("People.Regional Manager", "data", fill="#dff6e4")
        add_edge("People.Regional Manager", "Manager for\nselected region", "retrieve")

    if "Sales" in nodes and "Returned Order" not in nodes:
        result_label = "Total sales"
        if "Region" in nodes:
            result_label = "Total sales for\nselected region"
        add_node(result_label, "data", fill="#e5f1ff")
        add_node("Orders.Sales", "data", fill="#dff6e4")
        add_edge("Orders.Sales", result_label, "sum")

    if "Profit" in nodes:
        add_node("Total profit", "data", fill="#e5f1ff")
        add_node("Orders.Profit", "data", fill="#dff6e4")
        add_edge("Orders.Profit", "Total profit", "sum")

    dot_lines = [
        "digraph KG {",
        '  graph [rankdir=TB, bgcolor="#29333c", pad="0.45", nodesep="0.9", ranksep="1.0", splines=spline, overlap=false];',
        '  node [fontname="Arial", fontsize=13, style="filled", fontcolor="#10252a", color="#4e9299", penwidth=1.8, margin="0.16,0.10"];',
        '  edge [fontname="Arial", fontsize=9, color="#568b91", fontcolor="#9cc9cd", arrowsize=0.65, penwidth=1.35, labeldistance=1.8];',
        "",
    ]

    concept_ids = [
        node["id"]
        for node in node_defs.values()
        if node["layer"] == "concept" and node["label"] != "User\nquestion"
    ]
    data_ids = [node["id"] for node in node_defs.values() if node["layer"] == "data"]
    question_id = node_ids.get("User\nquestion")

    for node in node_defs.values():
        label = node["label"]
        fill = node["fill"]
        outline = "#4e9299"
        penwidth = "1.8"
        width = "1.50"

        if node["layer"] == "concept":
            fill = "#82dce2"
        elif label.endswith("\ntable"):
            fill = "#b7a6d9"
            outline = "#7e6ca6"
        else:
            fill = "#70cdb6"

        if (
            label == "User\nquestion"
            or label.startswith("Total ")
            or label.startswith("Distinct\n")
            or label.startswith("Manager for\n")
        ):
            fill = "#9be3e7"
            outline = "#f4d34f"
            penwidth = "3.4"
            width = "1.65"

        dot_lines.append(
            f'  {node["id"]} [label="{_dot_escape(label)}", shape="{node["shape"]}", fillcolor="{fill}", color="{outline}", penwidth={penwidth}, width={width}, height=0.86];'
        )

    dot_lines.append("")
    if question_id:
        dot_lines.append(f"  {{ rank=same; {question_id}; }}")
    if concept_ids:
        dot_lines.append(f"  {{ rank=same; {'; '.join(concept_ids)}; }}")
    if data_ids:
        dot_lines.append(f"  {{ rank=same; {'; '.join(data_ids[:4])}; }}")

    for source_id, target_id, label in edge_defs:
        dot_lines.append(
            f'  {source_id} -> {target_id} [xlabel="{_dot_escape(label)}"];'
        )

    if concept_ids and question_id:
        dot_lines.append(f"  {question_id} -> {concept_ids[0]} [style=invis];")
    if concept_ids and data_ids:
        dot_lines.append(f"  {concept_ids[0]} -> {data_ids[0]} [style=invis];")
    elif question_id and data_ids:
        dot_lines.append(f"  {question_id} -> {data_ids[0]} [style=invis];")

    dot_lines.append("}")
    return "\n".join(dot_lines)


def get_kg_animation_html(question):
    relevant_nodes = set(find_relevant_nodes(question))
    graph_nodes = []
    graph_edges = []
    node_index = {}
    edge_index = set()

    def add_node(label, level, step, kind="data", highlight=False):
        if label in node_index:
            existing = graph_nodes[node_index[label]]
            existing["step"] = min(existing["step"], step)
            existing["highlight"] = existing["highlight"] or highlight
            return existing["id"]

        node_id = f"node_{len(graph_nodes)}"
        node_index[label] = len(graph_nodes)
        graph_nodes.append(
            {
                "id": node_id,
                "label": label,
                "level": level,
                "step": step,
                "kind": kind,
                "highlight": highlight,
            }
        )
        return node_id

    def add_edge(source_label, target_label, label, step):
        edge_key = (source_label, target_label, label)
        if edge_key in edge_index:
            return
        edge_index.add(edge_key)
        graph_edges.append(
            {
                "source": graph_nodes[node_index[source_label]]["id"],
                "target": graph_nodes[node_index[target_label]]["id"],
                "label": label,
                "step": step,
            }
        )

    add_node("User question", 0, 0, kind="question", highlight=True)

    concept_mapping = {
        "Sales": ("Sales", ["Orders.Sales"]),
        "Profit": ("Profit", ["Orders.Profit"]),
        "Quantity": ("Quantity", ["Orders.Quantity"]),
        "Discount": ("Discount", ["Orders.Discount"]),
        "Customer": ("Customer", ["Orders.Customer Name", "Orders.Segment"]),
        "Product": ("Product / category", ["Orders.Category"]),
        "Location": ("Location", ["Orders.Region"]),
        "Date": ("Time period", ["Orders.Order Date"]),
        "Region": ("Region", ["Orders.Region", "People.Region"]),
        "People": ("Regional manager", ["People.Regional Manager"]),
        "Returned Order": ("Returned order", ["Returns.Order ID"]),
        "Returns": ("Return status", ["Returns.Returned"]),
    }

    concept_order = [
        "Returned Order",
        "Returns",
        "Sales",
        "Profit",
        "People",
        "Region",
        "Product",
        "Date",
        "Customer",
        "Quantity",
        "Discount",
        "Location",
    ]

    if "Region" in relevant_nodes:
        relevant_nodes.discard("Location")

    for concept_key in concept_order:
        if concept_key not in relevant_nodes:
            continue

        concept_label, columns = concept_mapping[concept_key]
        add_node(concept_label, 1, 1, kind="concept")
        add_edge("User question", concept_label, "asks about", 1)

        for column in columns:
            table_label = f"{column.split('.', 1)[0]} table"
            add_node(table_label, 2, 2, kind="table")
            add_edge(concept_label, table_label, "found in", 2)
            add_node(column, 3, 3, kind="mapping")
            add_edge(table_label, column, "column", 3)

    if {"Orders", "People", "Region"}.issubset(relevant_nodes):
        add_node("Orders.Region", 3, 3, kind="mapping")
        add_node("People.Region", 3, 3, kind="mapping")
        add_edge("Orders.Region", "People.Region", "same region", 3)
        add_node("Manager for selected region", 4, 4, kind="result", highlight=True)
        add_node("People.Regional Manager", 3, 3, kind="mapping")
        add_edge(
            "People.Regional Manager",
            "Manager for selected region",
            "retrieve",
            4,
        )

    if {"Orders", "Returns", "Returned Order"}.issubset(relevant_nodes):
        add_node("Returns.Order ID", 3, 3, kind="mapping")
        add_node("Orders.Order ID", 3, 3, kind="mapping")
        add_edge("Returns.Order ID", "Orders.Order ID", "same ID", 3)
        add_node("Distinct returned orders", 4, 4, kind="result", highlight=True)
        add_edge(
            "Returns.Order ID",
            "Distinct returned orders",
            "count unique",
            4,
        )

    if "Sales" in relevant_nodes:
        result_label = "Total sales"
        if "Returned Order" in relevant_nodes:
            result_label = "Total sales for returned orders"
        elif "Region" in relevant_nodes:
            result_label = "Total sales for selected region"

        add_node("Orders.Sales", 3, 3, kind="mapping")
        add_node(result_label, 4, 4, kind="result", highlight=True)
        add_edge("Orders.Sales", result_label, "sum sales", 4)

    if "Profit" in relevant_nodes:
        add_node("Orders.Profit", 3, 3, kind="mapping")
        add_node("Total profit", 4, 4, kind="result", highlight=True)
        add_edge("Orders.Profit", "Total profit", "sum profit", 4)

    nodes_json = json.dumps(graph_nodes).replace("</", "<\\/")
    edges_json = json.dumps(graph_edges).replace("</", "<\\/")

    return f"""
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root {{
    color-scheme: dark;
    font-family: Arial, sans-serif;
  }}

  * {{ box-sizing: border-box; }}

  body {{
    margin: 0;
    background: transparent;
    color: #d9f4f5;
  }}

  .shell {{
    background: #29333c;
    border: 1px solid #3e4d57;
    border-radius: 8px;
    overflow: hidden;
  }}

  .toolbar {{
    display: flex;
    align-items: center;
    gap: 10px;
    min-height: 52px;
    padding: 10px 14px;
    border-bottom: 1px solid #3e4d57;
    background: #242d35;
  }}

  button {{
    appearance: none;
    border: 1px solid #5b737c;
    border-radius: 6px;
    padding: 8px 13px;
    background: #33414b;
    color: #e8ffff;
    font: inherit;
    cursor: pointer;
  }}

  button:hover {{ background: #3d4d58; }}
  button:focus-visible {{ outline: 2px solid #f4d34f; outline-offset: 2px; }}

  .status {{
    margin-left: auto;
    color: #a9cdd0;
    font-size: 13px;
    text-align: right;
  }}

  .legend {{
    display: flex;
    gap: 16px;
    padding: 10px 16px 0;
    color: #a9cdd0;
    font-size: 12px;
  }}

  .legend span {{ display: inline-flex; align-items: center; gap: 6px; }}
  .swatch {{ width: 10px; height: 10px; border-radius: 50%; }}
  .swatch.concept {{ background: #82dce2; }}
  .swatch.mapping {{ background: #70cdb6; }}
  .swatch.result {{ background: #9be3e7; border: 2px solid #f4d34f; }}

  #canvas {{
    position: relative;
    width: 100%;
    height: 610px;
    overflow: hidden;
  }}

  svg {{
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    pointer-events: none;
  }}

  .node {{
    position: absolute;
    z-index: 2;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 132px;
    min-height: 62px;
    padding: 10px 13px;
    border: 2px solid #4e9299;
    border-radius: 50%;
    background: #70cdb6;
    color: #10252a;
    font-size: 13px;
    font-weight: 600;
    line-height: 1.2;
    text-align: center;
    opacity: 0.12;
    transform: translate(-50%, -50%) scale(0.82);
    transition: opacity 420ms ease, transform 420ms ease, box-shadow 420ms ease;
  }}

  .node.concept {{ background: #82dce2; }}
  .node.table {{ background: #b7a6d9; border-color: #8d7bb8; }}
  .node.question, .node.result {{
    width: 158px;
    background: #9be3e7;
    border: 4px solid #f4d34f;
  }}

  .node.visible {{
    opacity: 1;
    transform: translate(-50%, -50%) scale(1);
  }}

  .node.current {{
    box-shadow: 0 0 0 8px rgba(244, 211, 79, 0.12), 0 0 24px rgba(130, 220, 226, 0.36);
  }}

  .edge {{
    fill: none;
    stroke: #5b9298;
    stroke-width: 2;
    stroke-dasharray: 8 8;
    opacity: 0.06;
    transition: opacity 350ms ease;
  }}

  .edge.visible {{
    opacity: 0.9;
    animation: flow 850ms linear infinite;
  }}

  .edge-label {{
    position: absolute;
    z-index: 3;
    padding: 3px 6px;
    border-radius: 4px;
    background: rgba(41, 51, 60, 0.94);
    color: #a9cdd0;
    font-size: 11px;
    opacity: 0;
    transform: translate(-50%, -50%);
    transition: opacity 350ms ease;
    white-space: nowrap;
  }}

  .edge-label.visible {{ opacity: 1; }}
  .paused .edge.visible {{ animation-play-state: paused; }}

  @keyframes flow {{
    to {{ stroke-dashoffset: -32; }}
  }}

  @media (max-width: 760px) {{
    #canvas {{ transform-origin: top left; }}
    .status {{ display: none; }}
  }}

  @media (prefers-reduced-motion: reduce) {{
    .edge.visible {{ animation: none; }}
    .node, .edge, .edge-label {{ transition: none; }}
  }}
</style>
</head>
<body>
  <div class="shell">
    <div class="toolbar">
      <button id="playPause" type="button">Pause</button>
      <button id="replay" type="button">Replay</button>
      <div id="status" class="status">Understanding the question</div>
    </div>
    <div class="legend" aria-hidden="true">
      <span><i class="swatch concept"></i>Business concept</span>
      <span><i class="swatch mapping"></i>Database mapping</span>
      <span><i class="swatch result"></i>Answer evidence</span>
    </div>
    <div id="canvas" aria-label="Animated knowledge graph reasoning path">
      <svg id="edges" aria-hidden="true">
        <defs>
          <marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
            <path d="M0,0 L8,4 L0,8 z" fill="#82dce2"></path>
          </marker>
        </defs>
      </svg>
    </div>
  </div>

<script>
  const nodes = {nodes_json};
  const edges = {edges_json};
  const canvas = document.getElementById("canvas");
  const svg = document.getElementById("edges");
  const status = document.getElementById("status");
  const playPause = document.getElementById("playPause");
  const replay = document.getElementById("replay");
  const stepText = [
    "Understanding the question",
    "Identifying relevant business concepts",
    "Mapping concepts to tables and columns",
    "Following relationships between the data",
    "Revealing the answer evidence"
  ];

  let currentStep = -1;
  let timer = null;
  let playing = false;

  function groupPositions() {{
    const levels = [...new Set(nodes.map(node => node.level))].sort((a, b) => a - b);
    const yByLevel = {{0: 58, 1: 165, 2: 278, 3: 410, 4: 560}};

    for (const level of levels) {{
      const group = nodes.filter(node => node.level === level);

      if (level === 3) {{
        const preferredOrder = [
          "Returns.Order ID",
          "Orders.Order ID",
          "Returns.Returned",
          "Orders.Sales",
          "Orders.Region",
          "People.Region",
          "People.Regional Manager",
          "Orders.Profit"
        ];
        group.sort((a, b) => {{
          const aIndex = preferredOrder.indexOf(a.label);
          const bIndex = preferredOrder.indexOf(b.label);
          const aRank = aIndex === -1 ? preferredOrder.length : aIndex;
          const bRank = bIndex === -1 ? preferredOrder.length : bIndex;
          return aRank - bRank;
        }});
      }}

      if (level === 3 && group.length > 4) {{
        const splitAt = Math.ceil(group.length / 2);
        const rows = [group.slice(0, splitAt), group.slice(splitAt)];
        rows.forEach((row, rowIndex) => {{
          row.forEach((node, index) => {{
            node.x = ((index + 1) / (row.length + 1)) * canvas.clientWidth;
            node.y = rowIndex === 0 ? 380 : 465;
          }});
        }});
        continue;
      }}

      group.forEach((node, index) => {{
        node.x = ((index + 1) / (group.length + 1)) * canvas.clientWidth;
        node.y = yByLevel[level] || 485;
      }});
    }}
  }}

  function createNodes() {{
    groupPositions();
    for (const node of nodes) {{
      const el = document.createElement("div");
      el.id = node.id;
      el.className = `node ${{node.kind}}`;
      el.dataset.step = node.step;
      el.textContent = node.label;
      el.style.left = `${{node.x}}px`;
      el.style.top = `${{node.y}}px`;
      canvas.appendChild(el);
    }}
  }}

  function nodeCenter(id) {{
    const element = document.getElementById(id);
    const rect = element.getBoundingClientRect();
    const canvasRect = canvas.getBoundingClientRect();
    return {{
      x: rect.left - canvasRect.left + rect.width / 2,
      y: rect.top - canvasRect.top + rect.height / 2,
      width: rect.width,
      height: rect.height
    }};
  }}

  function edgePath(start, end) {{
    const startPad = Math.min(start.height / 2, 36);
    const endPad = Math.min(end.height / 2, 36);
    const y1 = start.y + (end.y >= start.y ? startPad : -startPad);
    const y2 = end.y + (end.y >= start.y ? -endPad : endPad);

    if (Math.abs(start.y - end.y) < 35) {{
      const curve = Math.max(36, Math.abs(end.x - start.x) * 0.16);
      return `M ${{start.x}} ${{start.y}} Q ${{(start.x + end.x) / 2}} ${{start.y - curve}} ${{end.x}} ${{end.y}}`;
    }}

    const middleY = (y1 + y2) / 2;
    return `M ${{start.x}} ${{y1}} C ${{start.x}} ${{middleY}}, ${{end.x}} ${{middleY}}, ${{end.x}} ${{y2}}`;
  }}

  function createEdges() {{
    document.querySelectorAll(".edge, .edge-label").forEach(el => el.remove());

    edges.forEach((edge, index) => {{
      const start = nodeCenter(edge.source);
      const end = nodeCenter(edge.target);
      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.id = `edge_${{index}}`;
      path.setAttribute("d", edgePath(start, end));
      path.setAttribute("marker-end", "url(#arrow)");
      path.setAttribute("class", "edge");
      path.dataset.step = edge.step;
      svg.appendChild(path);

      const label = document.createElement("div");
      label.id = `edge_label_${{index}}`;
      label.className = "edge-label";
      label.dataset.step = edge.step;
      label.textContent = edge.label;
      label.style.left = `${{(start.x + end.x) / 2}}px`;
      const sameLevel = Math.abs(start.y - end.y) < 35;
      label.style.top = `${{(start.y + end.y) / 2 - (sameLevel ? 38 : 0)}}px`;
      canvas.appendChild(label);
    }});
  }}

  function showStep(step) {{
    currentStep = step;
    status.textContent = stepText[Math.min(step, stepText.length - 1)];

    document.querySelectorAll("[data-step]").forEach(el => {{
      const elementStep = Number(el.dataset.step);
      el.classList.toggle("visible", elementStep <= step);
      if (el.classList.contains("node")) {{
        el.classList.toggle("current", elementStep === step);
      }}
    }});
  }}

  function reset() {{
    clearTimeout(timer);
    currentStep = -1;
    playing = false;
    canvas.classList.remove("paused");
    document.querySelectorAll("[data-step]").forEach(el => {{
      el.classList.remove("visible", "current");
    }});
  }}

  function tick() {{
    if (!playing) return;
    const nextStep = currentStep + 1;
    if (nextStep > 4) {{
      playing = false;
      playPause.textContent = "Play";
      status.textContent = "Reasoning path complete";
      return;
    }}

    showStep(nextStep);
    timer = setTimeout(tick, 1150);
  }}

  function play() {{
    if (currentStep >= 4) reset();
    playing = true;
    canvas.classList.remove("paused");
    playPause.textContent = "Pause";
    tick();
  }}

  function pause() {{
    playing = false;
    clearTimeout(timer);
    canvas.classList.add("paused");
    playPause.textContent = "Play";
    status.textContent = "Reasoning path paused";
  }}

  playPause.addEventListener("click", () => playing ? pause() : play());
  replay.addEventListener("click", () => {{
    reset();
    play();
  }});

  window.addEventListener("resize", () => {{
    groupPositions();
    nodes.forEach(node => {{
      const el = document.getElementById(node.id);
      el.style.left = `${{node.x}}px`;
      el.style.top = `${{node.y}}px`;
    }});
    createEdges();
    showStep(Math.max(currentStep, 0));
  }});

  createNodes();
  createEdges();
  play();
</script>
</body>
</html>
"""
