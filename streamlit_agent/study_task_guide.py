"""Assigned-task guide shown during the study interaction phase."""

import streamlit as st


def render_assigned_tasks_guide():
    """Show the required study tasks and acceptable rephrasings."""
    st.markdown(
        """
        <style>
        .st-key-assigned_tasks_control button {
            background: #14532d !important;
            border: 1px solid #22c55e !important;
            color: #ffffff !important;
            font-weight: 700 !important;
            min-height: 2.75rem !important;
            padding-left: 1rem !important;
            padding-right: 1rem !important;
        }
        .st-key-assigned_tasks_control button:hover {
            background: #166534 !important;
            border-color: #4ade80 !important;
            color: #ffffff !important;
        }
        .task-card {
            border: 1px solid rgba(148, 163, 184, 0.35);
            border-radius: 0.65rem;
            padding: 1rem;
            margin: 0.85rem 0;
            background: rgba(15, 23, 42, 0.28);
        }
        .task-card-title {
            font-weight: 800;
            margin-bottom: 0.4rem;
        }
        .task-chip {
            display: inline-block;
            border: 1px solid rgba(34, 197, 94, 0.65);
            border-radius: 999px;
            padding: 0.08rem 0.45rem;
            margin: 0.08rem;
            background: rgba(20, 83, 45, 0.35);
            color: #bbf7d0;
            font-weight: 700;
            white-space: nowrap;
        }
        .task-chip-blue {
            border-color: rgba(96, 165, 250, 0.7);
            background: rgba(30, 64, 175, 0.28);
            color: #bfdbfe;
        }
        .task-chip-purple {
            border-color: rgba(167, 139, 250, 0.75);
            background: rgba(76, 29, 149, 0.26);
            color: #ddd6fe;
        }
        .task-example {
            color: rgba(226, 232, 240, 0.9);
            margin-top: 0.55rem;
            line-height: 1.65;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    if "show_assigned_tasks" not in st.session_state:
        st.session_state["show_assigned_tasks"] = False

    with st.container(key="assigned_tasks_control"):
        if st.button("Assigned tasks", key="toggle_assigned_tasks"):
            st.session_state["show_assigned_tasks"] = not st.session_state[
                "show_assigned_tasks"
            ]

    if not st.session_state["show_assigned_tasks"]:
        return

    with st.container(border=True):
        st.markdown("**Assigned tasks**")
        st.write(
            "Please complete these three tasks. You may rephrase the wording, "
            "but keep the same meaning so the answers can be compared fairly."
        )

        st.markdown(
            """
            <div class="task-card">
                <div class="task-card-title">Task 1: Category performance</div>
                <div>Ask about total sales and total profit for Office Supplies in 2021.</div>
                <div class="task-example">
                    Example: What are the <span class="task-chip">total sales</span>
                    and <span class="task-chip">total profit</span> for
                    <span class="task-chip-blue">Office Supplies</span> in
                    <span class="task-chip-purple">2021</span>?
                </div>
                <div class="task-example">
                    You can also write: Show me sales and profit for Office Supplies in 2021.
                </div>
            </div>

            <div class="task-card">
                <div class="task-card-title">Task 2: Region and manager relationship</div>
                <div>Ask who manages the West region and what the total sales are there.</div>
                <div class="task-example">
                    Example: Who is the <span class="task-chip">regional manager</span>
                    for the <span class="task-chip-blue">West region</span>, and what are
                    the <span class="task-chip">total sales</span> there?
                </div>
                <div class="task-example">
                    You can also write: Which manager is responsible for West, and how much sales did West have?
                </div>
            </div>

            <div class="task-card">
                <div class="task-card-title">Task 3: Returned orders relationship</div>
                <div>Ask how many distinct returned orders there are and their total sales value.</div>
                <div class="task-example">
                    Example: How many <span class="task-chip">distinct returned orders</span>
                    are there, and what are the <span class="task-chip">total sales</span>
                    for those returned orders?
                </div>
                <div class="task-example">
                    You can also write: Count the unique returned orders and calculate their total sales.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.info(
            "For these required tasks, please avoid changing the dataset values "
            "such as Office Supplies, West, returned orders, or 2021. You can "
            "use the guided exploration section afterwards for more freedom."
        )
