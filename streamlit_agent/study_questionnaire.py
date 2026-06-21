"""Shared study onboarding and questionnaire flow for both prototype conditions."""

from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from study_storage import (
    has_previous_pre_questionnaire,
    initialize_questionnaire_database,
    insert_questionnaire_responses,
    update_study_session,
    upsert_study_session,
)

DATASET_PATH = Path("streamlit_agent/(US)Sample-Superstore.xlsx")
CONSENT_VERSION = "2026-06-21"

TASK_OVERVIEW = [
    "Answer a question about sales and profit for a product category.",
    "Answer a question that connects regions with regional managers.",
    "Answer a question about returned orders and their sales value.",
    "Optionally explore the dataset with one additional question.",
]


def apply_soft_theme():
    """Keep Streamlit's configured theme unchanged."""
    _apply_action_button_styles()


def _apply_action_button_styles():
    """Style the optional study helper buttons without changing the page theme."""
    st.markdown(
        """
        <style>
        .st-key-dataset_viewer_control button {
            background: #17324d !important;
            border: 1px solid #3b82f6 !important;
            color: #ffffff !important;
        }
        .st-key-dataset_viewer_control button:hover {
            background: #1f4568 !important;
            border-color: #60a5fa !important;
            color: #ffffff !important;
        }
        .st-key-guided_exploration_control button {
            background: #3a2b59 !important;
            border: 1px solid #a78bfa !important;
            color: #ffffff !important;
        }
        .st-key-guided_exploration_control button:hover {
            background: #4a3672 !important;
            border-color: #c4b5fd !important;
            color: #ffffff !important;
        }
        .st-key-dataset_viewer_control button,
        .st-key-guided_exploration_control button {
            font-weight: 700 !important;
            min-height: 2.75rem !important;
            padding-left: 1rem !important;
            padding-right: 1rem !important;
        }
        [class*="st-key-explanation_controls_"] button {
            background: #174a4d !important;
            border: 1px solid #2dd4bf !important;
            color: #ffffff !important;
            font-weight: 700 !important;
        }
        [class*="st-key-explanation_controls_"] button:hover {
            background: #1f6266 !important;
            border-color: #5eead4 !important;
            color: #ffffff !important;
        }
        .st-key-finish_assistant_control div[data-testid="stExpander"] {
            background: rgba(120, 53, 15, 0.18);
            border-color: #f59e0b;
        }
        .st-key-finish_assistant_control div[data-testid="stExpander"] summary,
        .st-key-finish_assistant_control div[data-testid="stExpander"] summary p {
            color: #fed7aa !important;
            font-weight: 700 !important;
        }
        .st-key-finish_assistant_control button {
            background: #9a3412 !important;
            border: 1px solid #fb923c !important;
            color: #ffffff !important;
            font-weight: 700 !important;
        }
        .st-key-finish_assistant_control button:hover {
            background: #c2410c !important;
            border-color: #fdba74 !important;
            color: #ffffff !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

TRUST_ITEMS = {
    "TBB1": (
        "benevolence",
        "I believe that the data assistant would act in my best interest.",
    ),
    "TBB2": (
        "benevolence",
        "If I required help, the data assistant would do its best to help me.",
    ),
    "TBB3": (
        "benevolence",
        "The data assistant is interested in supporting my analysis goals, not just in providing generic answers.",
    ),
    "TBI1": (
        "integrity",
        "The data assistant is truthful in its interactions with me.",
    ),
    "TBI2": ("integrity", "I would characterize the data assistant as honest."),
    "TBI3": (
        "integrity",
        "The data assistant would keep its commitments when providing information.",
    ),
    "TBI4": ("integrity", "The data assistant is sincere and genuine."),
    "TBC1": (
        "competence",
        "The data assistant is competent and effective in answering questions about the dataset.",
    ),
    "TBC2": (
        "competence",
        "The data assistant performs its role of supporting data analysis very well.",
    ),
    "TBC3": (
        "competence",
        "Overall, the data assistant is a capable and proficient data-analysis assistant.",
    ),
    "TBC4": (
        "competence",
        "The data assistant is knowledgeable about the dataset and its relationships.",
    ),
}

SATISFACTION_ITEMS = {
    "SAT1": ("Very dissatisfied", "Very satisfied"),
    "SAT2": ("Very displeased", "Very pleased"),
    "SAT3": ("Very frustrated", "Very contented"),
    "SAT4": ("Absolutely terrible", "Absolutely delighted"),
}

GUIDED_EXPLORATION_ITEMS = {
    "GE1": "I enjoyed using the assistant during the guided exploration.",
    "GE2": "I felt comfortable asking my own question about the dataset.",
    "GE3": "The assistant gave me enough freedom to explore the dataset.",
    "GE4": "The dataset viewer helped me formulate my own question.",
    "GE5": "The assistant supported me in exploring the data beyond the required tasks.",
}

OPEN_QUESTIONS = {
    "OPEN_TRUST": "What specifically made you trust or distrust the assistant's answers?",
    "OPEN_UNCERTAINTY": "Describe a moment when you were uncertain whether to rely on an answer.",
    "OPEN_SATISFACTION": "What contributed most to your satisfaction or dissatisfaction?",
    "OPEN_EXPLANATION_FEATURE": (
        "Which specific part of the explanation did you find most helpful, and why? "
        "For example, you may refer to the written explanation, SQL reasoning, or animated reasoning path if it was available."
    ),
    "OPEN_TRUST_FEATURE": (
        "Which specific feature or part of the explanation influenced your trust in the answer the most, and why?"
    ),
    "OPEN_GUIDED_EXPLORATION": (
        "What did you like or dislike about the guided exploration part of the study?"
    ),
    "OPEN_EXPLORATION_FREEDOM": (
        "Did you feel limited when asking your own question? If yes, in what way?"
    ),
    "OPEN_OWN_QUESTION": (
        "What kind of question did you choose to ask during guided exploration, and why?"
    ),
    "OPEN_IMPROVEMENT": "What would need to change before you would use this assistant for a real data-analysis task?",
}


@st.cache_data(show_spinner=False)
def _load_dataset_preview():
    preview = {}
    facts = {
        "Orders": "Main table with order lines, customers, products, dates, sales, quantity, discount, and profit.",
        "People": "Regional manager table. It connects each business region to one regional manager.",
        "Returns": "Returned-order table. It marks returned orders by Order ID.",
    }

    try:
        xls = pd.ExcelFile(DATASET_PATH)
        for sheet_name in xls.sheet_names:
            df = pd.read_excel(DATASET_PATH, sheet_name=sheet_name)
            preview[sheet_name] = {
                "description": facts.get(sheet_name, "Dataset table."),
                "rows": len(df),
                "columns": list(df.columns),
                "sample": df.head(5),
                "data": df,
            }
    except Exception as error:
        preview["Dataset"] = {
            "description": f"The dataset preview could not be loaded: {error}",
            "rows": 0,
            "columns": [],
            "sample": pd.DataFrame(),
            "data": pd.DataFrame(),
        }

    return preview


def _render_dataset_preview_content(interactive=False):
    preview = _load_dataset_preview()

    if interactive:
        selected_table = st.selectbox(
            "Choose a table",
            list(preview.keys()),
            key="dataset_viewer_table",
        )
        sheet_preview = preview[selected_table]
        df = sheet_preview["data"]

        st.markdown(f"**{selected_table}**")
        st.caption(sheet_preview["description"])
        st.write(f"{sheet_preview['rows']} rows, {len(sheet_preview['columns'])} columns")

        if df.empty:
            st.info("No data is available for this table.")
            return

        default_columns = sheet_preview["columns"][: min(8, len(sheet_preview["columns"]))]
        selected_columns = st.multiselect(
            "Columns to display",
            sheet_preview["columns"],
            default=default_columns,
            key=f"dataset_columns_{selected_table}",
        )
        search_text = st.text_input(
            "Search in the selected columns",
            placeholder="For example: West, Office Supplies, returned, Sadie",
            key=f"dataset_search_{selected_table}",
        )

        if not selected_columns:
            st.warning("Please select at least one column.")
            return

        visible_df = df[selected_columns].copy()
        if search_text.strip():
            search_lower = search_text.strip().lower()
            row_matches = visible_df.astype(str).apply(
                lambda row: row.str.lower().str.contains(search_lower, na=False).any(),
                axis=1,
            )
            visible_df = visible_df[row_matches]

        st.dataframe(
            visible_df.head(100),
            hide_index=True,
            use_container_width=True,
        )
        st.caption(
            f"Showing {min(len(visible_df), 100)} of {len(visible_df)} matching rows."
        )
        return

    tabs = st.tabs(list(preview.keys()))
    for tab, (sheet_name, sheet_preview) in zip(tabs, preview.items()):
        with tab:
            st.markdown(f"**{sheet_name}**")
            st.caption(sheet_preview["description"])
            st.write(
                f"{sheet_preview['rows']} rows, "
                f"{len(sheet_preview['columns'])} columns"
            )
            if sheet_preview["columns"]:
                st.caption(", ".join(sheet_preview["columns"]))
            if not sheet_preview["sample"].empty:
                st.dataframe(
                    sheet_preview["sample"],
                    hide_index=True,
                    use_container_width=True,
                )


def render_dataset_viewer():
    """Render an optional dataset viewer during the interaction phase."""
    _apply_action_button_styles()

    if "show_dataset_viewer" not in st.session_state:
        st.session_state["show_dataset_viewer"] = False

    with st.container(key="dataset_viewer_control"):
        if st.button("View dataset", key="toggle_dataset_viewer"):
            st.session_state["show_dataset_viewer"] = not st.session_state[
                "show_dataset_viewer"
            ]

    if st.session_state["show_dataset_viewer"]:
        with st.expander("Dataset viewer", expanded=True):
            st.write(
                "Use this view to understand what information exists in the "
                "Superstore dataset before asking your own exploration question."
            )
            _render_dataset_preview_content(interactive=True)


def render_guided_exploration_guide():
    """Show examples that help participants formulate their own dataset questions."""
    _apply_action_button_styles()

    if "show_guided_exploration" not in st.session_state:
        st.session_state["show_guided_exploration"] = False

    with st.container(key="guided_exploration_control"):
        if st.button("Guided exploration ideas", key="toggle_guided_exploration"):
            st.session_state["show_guided_exploration"] = not st.session_state[
                "show_guided_exploration"
            ]

    if st.session_state["show_guided_exploration"]:
        with st.container(border=True):
            st.markdown("**Guided exploration ideas**")
            st.write(
                "After the required tasks, you may ask one or two questions of your own. "
                "You can change parts of the examples below, but your question should use "
                "information that exists in the Superstore dataset."
            )

            st.markdown("**Example 1**")
            st.code("Which region had the highest sales in 2021?", language="text")
            st.markdown(
                """
                You can change:
                - **highest** -> lowest
                - **sales** -> profit, quantity, discount
                - **region** -> category, sub-category, segment
                - **2021** -> 2019, 2020, 2021, 2022
                """
            )

            st.markdown("**Example 2**")
            st.code(
                "Compare sales and profit for Technology and Furniture.",
                language="text",
            )
            st.markdown(
                """
                You can change:
                - **sales and profit** -> sales, profit, quantity, discount
                - **Technology and Furniture** -> Office Supplies, Technology, Furniture
                - **categories** -> regions, segments, sub-categories
                """
            )

            st.info(
                "Tip: use the dataset viewer to check which years, columns, regions, "
                "and categories are available. For example, the dataset has years "
                "2019-2022 and categories Furniture, Office Supplies, and Technology."
            )


def render_study_progress_footer(session_id, question_count):
    """Render a compact task-completion control in the main page."""
    participant_id = st.session_state.get("participant_id", "unknown")

    with st.container(key="finish_assistant_control"):
        st.divider()
        with st.expander("Finished with this assistant version?", expanded=False):
            st.write(f"Participant: `{participant_id}`")
            st.caption(
                "When you have completed the required tasks and optional exploration, "
                "continue to the final questionnaire."
            )
            if question_count == 0:
                st.info("No questions have been sent to the assistant yet.")

            if st.button(
                "Finish tasks and continue",
                type="primary",
                use_container_width=True,
                key="finish_tasks_main",
            ):
                _update_session(
                    session_id,
                    tasks_completed_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                )
                st.session_state["study_phase"] = "post"
                st.rerun()


def _render_study_information():
    st.subheader("Study information")
    st.write(
        "In this study, you will use a data assistant to answer questions about a "
        "fictional Superstore sales dataset. Imagine that you are supporting a "
        "business team that wants quick answers about sales, profit, regions, "
        "managers, products, and returned orders."
    )

    st.info(
        "Some answers may take a little time to load. If the assistant does not "
        "respond after a longer wait, please reload the page and continue with "
        "the same participant code."
    )

    with st.expander("How the study is structured", expanded=True):
        st.markdown(
            """
            1. **Consent and participant code**: You confirm that you agree to participate.
            2. **Pre-interaction questionnaire**: You answer short questions about your background and prior experience.
            3. **Assistant tasks**: You ask the assistant the assigned data-analysis questions.
            4. **Post-interaction questionnaire**: You rate your trust, satisfaction, and experience with the assistant.
            """
        )
        st.markdown("**Task overview**")
        for task in TASK_OVERVIEW:
            st.markdown(f"- {task}")

    with st.expander("What data will be saved"):
        st.markdown(
            """
            The study stores an anonymous participant code, questionnaire answers,
            the questions you ask the assistant, the assistant's answers, clicked
            explanation buttons, timestamps, and the assistant version used.

            Please do not enter your real name, email address, student ID, or other
            personal identifying information into the assistant. The stored data is
            used only for the thesis analysis.
            """
        )

    with st.expander("Dataset preview"):
        st.write(
            "The assistant works with a sample Superstore dataset. The preview below "
            "shows the tables and a few example rows so you know what kind of data "
            "the assistant can use."
        )
        _render_dataset_preview_content()


def _save_responses(
    session_id,
    participant_id,
    assistant_version,
    phase,
    responses,
):
    insert_questionnaire_responses(
        session_id,
        participant_id,
        assistant_version,
        phase,
        responses,
    )


def _update_session(session_id, **fields):
    if not fields:
        return

    update_study_session(session_id, **fields)


def _render_identification(session_id, assistant_version):
    _render_study_information()

    with st.form("participant_identification"):
        st.markdown("### Consent")
        participant_code = st.text_input(
            "Anonymous participant code",
            placeholder="For example: P001",
            help="Use the code provided by the researcher. Do not enter your name or email address.",
        )
        consent_information = st.checkbox(
            "I have read and understood the study information above."
        )
        consent_data = st.checkbox(
            "I understand that my anonymous study data will be stored for thesis analysis."
        )
        consent_voluntary = st.checkbox(
            "I voluntarily agree to participate in this study."
        )
        submitted = st.form_submit_button("Continue")

    if submitted:
        normalized_code = participant_code.strip().upper()
        if not normalized_code:
            st.error("Please enter your participant code.")
        elif not (consent_information and consent_data and consent_voluntary):
            st.error("Please confirm all consent statements before continuing.")
        else:
            st.session_state["participant_id"] = normalized_code
            upsert_study_session(
                session_id,
                normalized_code,
                assistant_version,
                CONSENT_VERSION,
            )

            if has_previous_pre_questionnaire(normalized_code):
                _update_session(
                    session_id,
                    pre_completed_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                )
                st.session_state["study_phase"] = "interaction"
            else:
                st.session_state["study_phase"] = "pre"
            st.rerun()


def _required_choice(label, key, options):
    return st.radio(label, options=options, index=None, key=key, horizontal=True)


def _render_pre_questionnaire(session_id, participant_id, assistant_version):
    st.subheader("Pre-interaction questionnaire")
    st.caption(
        "These questions describe your background. They are not a test, and there are no correct answers."
    )

    with st.form("pre_questionnaire"):
        age_group = st.selectbox(
            "Age group",
            [
                "18-24",
                "25-34",
                "35-44",
                "45-54",
                "55-64",
                "65 or older",
                "Prefer not to say",
            ],
            index=None,
        )
        gender = st.selectbox(
            "Gender",
            ["Woman", "Man", "Non-binary", "Self-describe", "Prefer not to say"],
            index=None,
        )
        education = st.selectbox(
            "Highest completed level of education",
            [
                "Secondary school",
                "Vocational qualification",
                "Bachelor's degree",
                "Master's degree",
                "Doctorate",
                "Other",
                "Prefer not to say",
            ],
            index=None,
        )

        st.markdown("**Prior experience**")
        st.caption("1 = none, 5 = extensive")
        ai_experience = _required_choice(
            "Experience using AI or LLM tools",
            "pre_ai_experience",
            [1, 2, 3, 4, 5],
        )
        data_experience = _required_choice(
            "Experience with data analysis",
            "pre_data_experience",
            [1, 2, 3, 4, 5],
        )
        sql_experience = _required_choice(
            "Experience with SQL or relational databases",
            "pre_sql_experience",
            [1, 2, 3, 4, 5],
        )
        business_experience = _required_choice(
            "Familiarity with sales and business-reporting concepts",
            "pre_business_experience",
            [1, 2, 3, 4, 5],
        )

        submitted = st.form_submit_button("Start the tasks")

    values = [
        age_group,
        gender,
        education,
        ai_experience,
        data_experience,
        sql_experience,
        business_experience,
    ]
    if submitted:
        if any(value is None for value in values):
            st.error("Please answer every pre-interaction question.")
            return

        _save_responses(
            session_id,
            participant_id,
            assistant_version,
            "pre",
            {
                "AGE_GROUP": {"construct": "demographic", "value": age_group},
                "GENDER": {"construct": "demographic", "value": gender},
                "EDUCATION": {"construct": "demographic", "value": education},
                "AI_EXPERIENCE": {"construct": "control", "value": ai_experience},
                "DATA_EXPERIENCE": {"construct": "control", "value": data_experience},
                "SQL_EXPERIENCE": {"construct": "control", "value": sql_experience},
                "BUSINESS_EXPERIENCE": {
                    "construct": "control",
                    "value": business_experience,
                },
            },
        )
        _update_session(
            session_id,
            pre_completed_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
        st.session_state["study_phase"] = "interaction"
        st.rerun()


def _render_post_questionnaire(session_id, participant_id, assistant_version):
    st.subheader("Post-interaction questionnaire")
    st.caption("Please answer based only on the assistant version you have just used.")

    with st.form("post_questionnaire"):
        st.markdown("### Trust")
        st.caption("1 = strongly disagree, 7 = strongly agree")
        trust_answers = {}
        for question_id, (_, item) in TRUST_ITEMS.items():
            trust_answers[question_id] = _required_choice(
                item,
                f"post_{question_id}",
                [1, 2, 3, 4, 5, 6, 7],
            )

        st.markdown("### Satisfaction")
        st.caption(
            "For each pair, choose the number that best describes your overall experience."
        )
        satisfaction_answers = {}
        for question_id, (left_anchor, right_anchor) in SATISFACTION_ITEMS.items():
            satisfaction_answers[question_id] = _required_choice(
                f"{left_anchor} (1) to {right_anchor} (7)",
                f"post_{question_id}",
                [1, 2, 3, 4, 5, 6, 7],
            )

        st.markdown("### Guided exploration")
        st.caption("1 = strongly disagree, 7 = strongly agree")
        guided_exploration_answers = {}
        for question_id, item in GUIDED_EXPLORATION_ITEMS.items():
            guided_exploration_answers[question_id] = _required_choice(
                item,
                f"post_{question_id}",
                [1, 2, 3, 4, 5, 6, 7],
            )

        st.markdown("### Your experience")
        st.caption("All comment fields are mandatory. A short answer is enough.")
        open_answers = {}
        for question_id, question in OPEN_QUESTIONS.items():
            open_answers[question_id] = st.text_area(
                question,
                key=f"post_{question_id}",
                height=100,
            )

        submitted = st.form_submit_button("Submit questionnaire")

    if submitted:
        all_ratings = list(trust_answers.values()) + list(
            satisfaction_answers.values()
        ) + list(
            guided_exploration_answers.values()
        )
        if any(answer is None for answer in all_ratings):
            st.error(
                "Please complete every trust, satisfaction, and guided exploration rating."
            )
            return
        if any(not answer.strip() for answer in open_answers.values()):
            st.error("Please provide a brief response to every open question.")
            return

        responses = {}
        for question_id, value in trust_answers.items():
            responses[question_id] = {
                "construct": TRUST_ITEMS[question_id][0],
                "value": value,
            }
        for question_id, value in satisfaction_answers.items():
            responses[question_id] = {
                "construct": "satisfaction",
                "value": value,
            }
        for question_id, value in guided_exploration_answers.items():
            responses[question_id] = {
                "construct": "guided_exploration",
                "value": value,
            }
        for question_id, value in open_answers.items():
            responses[question_id] = {
                "construct": "qualitative_feedback",
                "value": value.strip(),
            }

        _save_responses(
            session_id,
            participant_id,
            assistant_version,
            "post",
            responses,
        )
        _update_session(
            session_id,
            post_completed_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
        st.session_state["study_phase"] = "complete"
        st.rerun()


def _render_completion():
    st.success("Thank you. Your responses have been recorded.")
    st.write("You have completed this part of the study.")


def render_questionnaire_flow(assistant_version, session_id, question_count):
    """Render the current study phase and return only while interaction is active."""
    initialize_questionnaire_database()

    if "study_phase" not in st.session_state:
        st.session_state["study_phase"] = "identify"

    phase = st.session_state["study_phase"]
    participant_id = st.session_state.get("participant_id")

    if phase == "identify":
        _render_identification(session_id, assistant_version)
        st.stop()

    if phase == "pre":
        _render_pre_questionnaire(session_id, participant_id, assistant_version)
        st.stop()

    if phase == "post":
        _render_post_questionnaire(session_id, participant_id, assistant_version)
        st.stop()

    if phase == "complete":
        _render_completion()
        st.stop()
