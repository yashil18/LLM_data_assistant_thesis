"""
Data Assistant Streamlit App

This app provides an LLM-powered data assistant for querying a sample Superstore sales database via natural language.
- Uses Streamlit for the chat UI.
- Uses LangChain for SQL query generation via an LLM (OpenAI GPT).
- User interactions and metadata are logged to an SQLite database called interactions.db.
- You can set `treatment` to 1 (automatic explanation) or 2 (user-invoked explanation button).

To use: Install requirements, provide a valid OpenAI API key in `.streamlit/secrets.toml`, and run the app with `streamlit run streamlit_agent/data_assistant_thesis_prototype.py`.

How to run:
- Make sure your Excel data file is present at streamlit_agent/(US)Sample-Superstore.xlsx
- Set your OpenAI API key in .streamlit/secrets.toml
- In the terminal, run: streamlit run streamlit_agent/data_assistant_prototype.py
- Open the local web address (http://localhost:8501) in your browser

What to expect:
- Type questions in the chat (e.g., "Show total sales in 2021")
- The assistant will analyze your question, query the database, and display answers
- Explanations of how answers were obtained are shown according to the treatment value
- All interactions are saved in the interactions.db file
"""

import streamlit as st
import pandas as pd
import sqlite3
from pathlib import Path
from sqlalchemy import create_engine
from langchain_core.prompts.chat import (
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    SystemMessagePromptTemplate,
    AIMessagePromptTemplate,
    MessagesPlaceholder,
)
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_openai import ChatOpenAI
from langchain_community.utilities import SQLDatabase
from langchain_community.chat_message_histories import StreamlitChatMessageHistory
from langchain_community.agent_toolkits import create_sql_agent, SQLDatabaseToolkit

# from langchain.agents.agent_types import AgentType
import tiktoken
import subprocess
import sys
import uuid
import openai
from study_questionnaire import (
    apply_soft_theme,
    render_dataset_viewer,
    render_guided_exploration_guide,
    render_questionnaire_flow,
    render_study_progress_footer,
)
from study_storage import (
    initialize_interactions_database,
    insert_interaction,
    update_explanation_clicked as mark_explanation_clicked,
)


# Ensure necessary packages are installed
def install_package(package):
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])


try:
    import openpyxl
except ImportError:
    install_package("openpyxl")

# === 1. DATABASE SETUP ===
# Connects to SQLite, creates the interactions table if needed, and handles schema updates.
# You can create your own database

initialize_interactions_database()


# Function to save interaction
def save_interaction(
    session_id: object,
    question_id: object,
    participant_id: object,
    treatment: object,
    assistant_version: object,
    user_query: object,
    assistant_response: object,
    intermediate_steps: object,
    simplified_intermediate_steps: object,
    user_query_sent_time: object,
    response_displayed_time: object,
    explanation_button_displayed_time: object,
    explanation_clicked_time: object,
    explanation_clicked: object,
    explanation_displayed_time: object,
) -> object:
    insert_interaction(
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
    )


# Function to update explanation clicked
def update_explanation_clicked(session_id, interaction_id):
    mark_explanation_clicked(session_id, interaction_id)
# === 2. STREAMLIT APP STATE ===
# Sets up session state: session_id, participant_id, question counter.
# Streamlit app setup
st.set_page_config(page_title="Data Assistant")
apply_soft_theme()
st.title("Data Assistant 📈")
st.caption("Version A: Baseline assistant")
st.info("This version answers questions using the database schema and SQL reasoning.")

# Assign a unique session ID if it doesn't exist
if "session_id" not in st.session_state:
    st.session_state["session_id"] = str(uuid.uuid4())

# Initialize question counter for the session
if "question_counter" not in st.session_state:
    st.session_state["question_counter"] = 0

session_id = st.session_state["session_id"]

if "participant_id" not in st.session_state:
    st.session_state["participant_id"] = str(uuid.uuid4())

render_questionnaire_flow(
    assistant_version="baseline",
    session_id=session_id,
    question_count=st.session_state["question_counter"],
)
participant_id = st.session_state["participant_id"]
st.caption("Use the assistant to complete the data-analysis tasks provided by the researcher.")
render_dataset_viewer()
render_guided_exploration_guide()

# ======== CHANGE THIS PARAMETER IF NEEDED ========
# Manually set the treatment condition for the chat interface.
# 1 = Show explanation always, 2 = Show explanation only after clicking a buttontreatment = 2  #  treatment value (1 or 2), 1 for automatic, 2 for user-invoked (See Explanation Button)
treatment = 2


# === 3. LLM AND TOOLKIT SETUP ===
# Loads the Excel file into a SQLite database and configures the LLM agent.
# You can ajust the LLM, for OpenAI you would have to pay a bit (i do not think much because the model 4o-mini is pretty cheap), maybe there are other LLMs with fre API keys that do the job
# Add your API key in secrets.toml
# Get an OpenAI API Key from secrets.toml
if "openai_api_key" in st.secrets:
    openai_api_key = st.secrets["openai_api_key"]
else:
    st.info("Enter an OpenAI API Key in the secrets.toml file to continue")
    st.stop()

# Set up memory
msgs = StreamlitChatMessageHistory(key="langchain_messages")
if len(msgs.messages) == 0:
    msgs.add_ai_message(
        "Hello! I am the new LLM-based data assistant designed by Superstore. How may I help you?"
    )


# Function to count tokens using tiktoken
def count_tokens(messages):
    encoding = tiktoken.encoding_for_model("gpt-4o-mini")
    total_tokens = sum([len(encoding.encode(msg.content)) for msg in messages])
    return total_tokens


# Truncate conversation history to fit within token limit
def truncate_messages(messages, max_tokens):
    total_tokens = 0
    truncated_messages = []
    for message in reversed(messages):
        message_tokens = count_tokens([message])
        if total_tokens + message_tokens > max_tokens:
            break
        truncated_messages.append(message)
        total_tokens += message_tokens
    return list(reversed(truncated_messages))


# Detailed instructions for the AI on how to interact with the SQL database
prefix = """
You are an agent designed to interact with a SQL database.
Given an input question, create a syntactically correct SQLite query to run, then look at the results of the query and return the answer.

You can order the results by a relevant column to return the most interesting examples in the database.
Never query for all the columns from a specific table, only ask for the relevant columns given the question.
You have access to tools for interacting with the database.
Only use the below tools. Only use the information returned by the below tools to construct your final answer.
You MUST double check your query before executing it. If you get an error while executing a query, rewrite the query and try again.

DO NOT make any DML statements (INSERT, UPDATE, DELETE, DROP etc.) to the database.
To start you should ALWAYS look at the tables in the database to see what you can query.
Do NOT skip this step.
Then you should query the schema of the most relevant tables.

When reacting to basic conversation:
- Respond to greetings such as "Hello" or "Hi".
- Answer basic questions like "How are you?" with a friendly tone.
- Remind the user that you are an SQL agent and that you can help them interact with the database.
- Present the database schema to the user.
- Invite the user to ask questions based on the schema.
Example of a basic interaction:

User: Hello 
SQL Agent: Hi there! How can I help you today? Remember, I'm an SQL agent trained to interact with our database. Feel free to ask me anything about it.

User: How are you?
SQL Agent: I'm doing great, thank you! How can I assist you with the database today? Here's the schema for your reference:
- **Orders**: ("Row ID," "Order ID," "Order Date," "Ship Date," "Sales," "Profit," and more)
- **People**: ("Regional Manager," "Region")
- **Returns**: ("Returned," "Order ID")
Feel free to ask any question you have about the data!

When generating SQL queries for the SQLite database, ensure the following:
- Use double quotes or square brackets for column names that contain spaces.
- Do not enclose column names in single quotes.
- Use functions like strftime correctly by applying them directly to column names.
For example:
To query the total sales and profit for the year 2021 where the category is 'Office Supplies', use the following format:
SELECT SUM(Sales) AS Total_Sales, SUM(Profit) AS Total_Profit FROM Orders WHERE Category = 'Office Supplies' AND strftime('%Y', "Order Date") = '2021';

When generating responses, please use the word "dollars" instead of the dollar sign "$". For example, if the total sales amount is 183,939.98, the response should be "183,939.98 dollars" instead of "$183,939.98$".

When Formatting Responses:
- Provide paragraph texts that are easy to understand for humans as your response
- Use a clear , user friendly way to visualize the response.
- If the user asks for a summary or a count, provide a single answer.
- If the user asks for a list of items (e.g., "List all categories" or "Show all orders from 2021"), format the response as a list.
- Remember use the word "dollars" instead of the dollar sign "$".
- Clearly format financial figures on separate lines for readability using new lines.
- If the output is too large, display only the first 5 entries by default and inform the user.
- If the question does not seem related to the database, just return "The query does not relate to the database" as the answer.
For example:
User: What are the total sales and profit for the "Office Supplies" category in 2021?
SQL Agent: The total sales for the "Office Supplies" category in 2021 is 183,939.98 dollars.
The total profit for the "Office Supplies" category in 2021 is 35,061.23 dollars.

Another example:
User: Find the orders from the "West" region along with the name of the regional manager.
SQL Agent: Here are the first 5 orders from the "West" region along with the name of the regional manager:

Order ID: CA-2021-138688
Product Name: Self-Adhesive Address Labels for Typewriters by Universal
Sales: 14.62 dollars
Profit: 6.87 dollars
Regional Manager: Sadie Pawthorne

Order ID: CA-2019-115812
Product Name: Eldon Expressions Wood and Plastic Desk Accessories, Cherry Wood
Sales: 48.86 dollars
Profit: 14.17 dollars
Regional Manager: Sadie Pawthorne

Order ID: CA-2019-115812
Product Name: Newell 322
Sales: 7.28 dollars
Profit: 1.97 dollars
Regional Manager: Sadie Pawthorne

Order ID: CA-2019-115812
Product Name: Mitel 5320 IP Phone VoIP phone
Sales: 907.15 dollars
Profit: 90.72 dollars
Regional Manager: Sadie Pawthorne

Order ID: CA-2019-115812
Product Name: DXL Angle-View Binders with Locking Rings by Samsill
Sales: 18.50 dollars
Profit: 5.78 dollars
Regional Manager: Sadie Pawthorne

If you need more entries, please specify the number of entries you want to retrieve.

Additionally, provide clear and concise natural language explanations only in the intermediate_steps and not in the answer for each step you take and the reasons behind those actions. This will help non-programmers understand your thought process and how you arrived at the final answer.
"""

# Additional instructions for the AI on the next steps after receiving the input question
suffix = """I should look at the tables in the database to see what I can query. Then I should query the schema of the most relevant tables.
For each step I take, I should explain in simple, natural language why I am taking that step and how it helps in answering the question.
"""

# Creating the prompt structure with system, human, and AI messages, and incorporating prefix and suffix
messages = [
    SystemMessagePromptTemplate.from_template(prefix),
    MessagesPlaceholder(variable_name="history"),
    HumanMessagePromptTemplate.from_template("{input}"),
    AIMessagePromptTemplate.from_template(suffix),
    MessagesPlaceholder(variable_name="agent_scratchpad"),
]

prompt = ChatPromptTemplate.from_messages(messages)

# Specify the model name gpt-4o-mini in ChatOpenAI
openai_base_url = st.secrets.get("openai_base_url", None)
model_name = st.secrets.get("model_name", "gpt-4o-mini")
chain = prompt | ChatOpenAI(api_key=openai_api_key, base_url=openai_base_url, model=model_name)
chain_with_history = RunnableWithMessageHistory(
    chain,
    lambda session_id: msgs,
    input_messages_key="input",
    history_messages_key="history",
)

# Setup agent for SQL
llm = ChatOpenAI(api_key=openai_api_key, base_url=openai_base_url, model=model_name, temperature=0, streaming=True)

# Function to read Excel file into SQLite file-based database
@st.cache_resource(ttl="2h")
def excel_to_sqlite(file_path):
    db_path = "database.db"

    # Create a writable SQLite database connection first
    con = sqlite3.connect(db_path, check_same_thread=False)
    xls = pd.ExcelFile(file_path)
    for sheet_name in xls.sheet_names:
        df = xls.parse(sheet_name)

        df.to_sql(sheet_name, con, index=False, if_exists="replace")  # Load each sheet into SQLite
    con.close()

    # Change the database to read-only mode
    con_read_only = sqlite3.connect(
        f"file:{db_path}?mode=ro", uri=True, check_same_thread=False
    )  # Create a read-only SQLite database connection
    return SQLDatabase(create_engine("sqlite:///database.db", creator=lambda: con_read_only))


# Read the Excel file from the project folder
file_path = Path("streamlit_agent/(US)Sample-Superstore.xlsx")
db = excel_to_sqlite(file_path)  # Load the Excel file into the SQLite file-based database

toolkit = SQLDatabaseToolkit(db=db, llm=llm)
agent = create_sql_agent(
    llm=llm,
    toolkit=toolkit,
    verbose=True,
    agent_type="openai-tools",
    prompt=prompt,
    agent_executor_kwargs={"return_intermediate_steps": True},
)


def clear_message_history():
    st.session_state.pop("messages", None)
    st.session_state["question_counter"] = 0
    msgs.clear()


# Check if 'messages' exists in the session state or if the 'Clear chat history' button is pressed
if "messages" not in st.session_state:
    st.session_state["messages"] = [
        {
            "role": "assistant",
            "content": "Hello! I am the new LLM-based data assistant designed by Superstore. How may I help you?",
        }
    ]


# Function to handle explanation click event
def handle_explanation_click(interaction_id):
    update_explanation_clicked(session_id, interaction_id)
    st.session_state[f"expander_{interaction_id}"] = True


# === 4. CHAT INTERFACE LOGIC ===
# Handles user input, invokes the agent, and displays responses.

# Display all messages from the session state


if treatment == 2:    # Show explanation button
    for msg in st.session_state.get("messages", []):
        if "expander" in msg:
            interaction_id = msg.get("interaction_id")
            if st.session_state.get(f"expander_{interaction_id}", False):
                with st.expander(msg["expander"], expanded=True):
                    st.write(msg["content"])
            else:
                if st.button(
                    "See explanation",
                    key=f"button_{interaction_id}",
                    on_click=lambda id=interaction_id: handle_explanation_click(id),
                ):
                    st.session_state[f"expander_{interaction_id}"] = True
                    with st.expander(msg["expander"], expanded=True):
                        st.write(msg["content"])
        else:
            st.chat_message(msg["role"]).write(msg["content"])
else:  # Show explanation always expanded
    for msg in st.session_state.get("messages", []):
        if "expander" in msg:
            with st.expander(msg.get("expander", "See explanation"), expanded=False):
                st.write(msg["content"])
        else:
            st.chat_message(msg["role"]).write(msg["content"])


# Function to execute SQL queries every time
def execute_sql_query(query):
    with sqlite3.connect("database.db") as con:
        cur = con.cursor()
        cur.execute(query)
        results = cur.fetchall()
    return results


# Function to process user query
def process_user_query(query):
    # This function would typically be more complex, integrating logic to form SQL queries based on user input
    sql_query = f"SELECT * FROM interactions WHERE user_query LIKE '%{query}%'"
    results = execute_sql_query(sql_query)
    return results

# === FUNCTION: Prettify Intermediate Steps See line 493===
# This function takes the sequence of actions (steps) the AI agent took to answer the user’s question
# and formats them into easy-to-read, human-friendly text by sending the initial intermediate steps to ChatGPT (See Line 539).
# ChatGPT rewrites in plain language, what the agent did and why (e.g., which tables it checked, which queries it ran).
# The prettified steps are shown as explanations in the chat interface.
# So prettified steps mean the Chain of Thought of the model in nicer words (not os technical)

# Action descriptions for prettifying intermediate steps
action_descriptions = {
    "sql_db_list_tables": "I have to check the list of available tables in the database.",
    "sql_db_schema": "I have to look at the schema of the '{}' table to understand its structure and the available columns.",
    "sql_db_query": "Now I have to execute a query to get the required data from the '{}' table.",
}

def prettify_intermediate_steps(steps):
    prettified_steps = []
    num_steps = len(steps)
    for i, step in enumerate(steps, 1):
        action, result = step
        tool = action.tool
        tool_input = action.tool_input
        log = action.log

        # Determine the description based on the action type
        if tool in action_descriptions:
            if tool == "sql_db_schema" or tool == "sql_db_query":
                # Use the table name in the description
                table_name = (
                    tool_input.get("table_names")
                    if tool == "sql_db_schema"
                    else tool_input.get("query").split("FROM")[1].split()[0]
                )
                if num_steps > 1:
                    description = (
                        f"**Step {i}:** \n\n **{action_descriptions[tool].format(table_name)}**"
                    )
                else:
                    description = f"**{action_descriptions[tool].format(table_name)}**"
                if tool == "sql_db_query":
                    query_description = (
                        f"**Now the following SQL query has been run:** `{tool_input.get('query')}`"
                    )
            else:
                if num_steps > 1:
                    description = f"**Step {i}:** \n\n **{action_descriptions[tool]}**"
                else:
                    description = f"**{action_descriptions[tool]}**"
        else:
            if num_steps > 1:
                description = f"**Step {i}: ** \n\n **Performed an action.**"

        prettified_steps.append(
            f"{description}\n\n{query_description if tool == 'sql_db_query' else ''}\n\n**The result of this action returns:** {result}"
        )
    return "\n\n".join(prettified_steps)

# Ensure the OpenAI client is correctly instantiated
client = openai.OpenAI(
    api_key=openai_api_key,
    base_url=openai_base_url
)

# The final natural-language explanation is generated by ChatGPT (the LLM gpt-4o-mini) and shown in the chat interface.
def explain_intermediate_steps(intermediate_steps):
    prompt = (
        "Explain the following steps in simple, natural language for a non-technical user. Start your answer directly with the response and do not interact with the prompt. Do not start with sentences like: Sure! Here are the steps explained in simple language:"
        "Use the first person when explaining like for example: I checked the databases available. Before every step, write the step and its corresponding number."
        "Also, only if the following steps contain SQL query, please provide it in a code block format that users can try out themselves. Do not provide any SQL statements starting with CREATE TABLE:\n\n"
        f"{intermediate_steps}"
    )
    response = client.chat.completions.create(
    model=model_name,
        messages=[
            {
                "role": "system",
                "content": "You are a helpful assistant. You explain the steps in simple, natural language for a non-technical user. Start your answer directly with the response and do not interact with the prompt. Do not start with sentences like: Sure! Here are the steps explained in simple language:"
                "Use the first person when explaining like for example: I checked the databases available. Before every step, write the step and its corresponding number."
                "Also, only if the following steps contain SQL query, please provide it in a code block format that users can try. Do not display any SQL statements starting with CREATE TABLE, write only the ones starting with SELECT",
            },
            {"role": "user", "content": prompt},
        ],
        max_tokens=1000,
        temperature=0.1,  # Set the temperature to a low value for precise responses
    )
    message = response.choices[0].message.content.strip()
    return message


# Get user query from the chat input
user_query = st.chat_input(placeholder="Ask me anything from the database!")

if user_query:
    # Record timestamp for when the user query is sent
    user_query_sent_time = pd.Timestamp.now()

    # Increment the question counter for the session
    st.session_state["question_counter"] += 1
    question_id = st.session_state["question_counter"]

    # Append user query to the session state
    st.session_state.messages.append({"role": "user", "content": user_query})
    st.chat_message("user").write(user_query)

    # Save user query in history
    msgs.add_user_message(user_query)

    # Calculate current tokens and truncate message history if necessary
    max_total_tokens = 14600  # Maximum tokens allowed by the model
    reserved_tokens = 1000  # Reserve tokens for the current query and response
    prompt_tokens = count_tokens(
        msgs.messages + [type("msg", (object,), {"content": user_query})()]
    )
    max_history_tokens = max_total_tokens - reserved_tokens

    # Ensure prompt_tokens does not exceed max_total_tokens
    if prompt_tokens > max_total_tokens:
        max_history_tokens = max_total_tokens - reserved_tokens
        truncated_history = truncate_messages(msgs.messages, max_history_tokens)
    else:
        truncated_history = msgs.messages

    with st.spinner(text="Analyzing the database..."):
        # Get the assistant's response using your agent
        try:
            response = agent.invoke({"input": user_query, "history": truncated_history})
        except Exception as e:
            st.error(f"Error: {e}")
            response = {"output": str(e), "intermediate_steps": []}

    # Extract response content
    response_content = response["output"]

    # Record timestamp for when the response is displayed
    response_displayed_time = pd.Timestamp.now()

    # Append the assistant's response to the session state
    st.session_state.messages.append({"role": "assistant", "content": response_content})
    st.chat_message("assistant").write(response_content)

    # Save AI response in history
    msgs.add_ai_message(response_content)

    # Prettify intermediate steps
    inter_steps = response["intermediate_steps"]
    prettified_inter_steps = prettify_intermediate_steps(inter_steps)

    # Add a spinner for generating explanation
    with st.spinner(text="Generating explanation..."):
        simplified_intermediate_steps = explain_intermediate_steps(prettified_inter_steps)

    explanation_button_displayed_time = None
    explanation_clicked = None
    explanation_clicked_time = None
    explanation_displayed_time = None


    if treatment == 2:
        explanation_button_displayed_time = pd.Timestamp.now()
        if inter_steps:
            # Update session state with simplified steps
            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "expander": "See explanation",
                    "content": simplified_intermediate_steps,
                    "interaction_id": question_id,
                }
            )

            # Display intermediate steps with a button to see the explanation
            if st.button(
                "See explanation",
                key=f"button_{question_id}",
                on_click=lambda id=question_id: handle_explanation_click(id),
            ):
                st.session_state[f"expander_{question_id}"] = True
                with st.expander("See explanation", expanded=True):
                    st.write(simplified_intermediate_steps)
        else:
            # Display message if no intermediate steps are provided
            no_explanation_message = (
                "**The agent does not provide any further explanation for its response.**"
            )
            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "expander": "See explanation",
                    "content": no_explanation_message,
                    "interaction_id": question_id,
                }
            )
            if st.button(
                "See explanation",
                key=f"button_{question_id}",
                on_click=lambda id=question_id: handle_explanation_click(id),
            ):
                st.session_state[f"expander_{question_id}"] = True
                with st.expander("See explanation", expanded=True):
                    st.write(no_explanation_message)
    else:
        if inter_steps:
            # Update session state with simplified steps
            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "expander": "See explanation",
                    "content": simplified_intermediate_steps,
                    "interaction_id": question_id,
                }
            )

            explanation_displayed_time = pd.Timestamp.now()

            # Display intermediate steps with expander
            with st.expander("See explanation", expanded=True):
                st.write(simplified_intermediate_steps)
        else:
            # Display message if no intermediate steps are provided
            no_explanation_message = (
                "**The agent does not provide any further explanation for its response.**"
            )
            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "expander": "See explanation",
                    "content": no_explanation_message,
                    "interaction_id": question_id,
                }
            )

            explanation_displayed_time = pd.Timestamp.now()

            with st.expander("See explanation", expanded=True):
                st.write(no_explanation_message)

    # === 5. LOGGING INTERACTIONS ===
    # Saves all user and assistant interactions to the database for later analysis
    save_interaction(
        session_id,
        question_id,
        participant_id,
        treatment,
        "baseline",
        user_query,
        response_content,
        prettified_inter_steps,
        simplified_intermediate_steps if inter_steps else no_explanation_message,
        user_query_sent_time,
        response_displayed_time,
        explanation_button_displayed_time,
        explanation_clicked_time,
        explanation_clicked,
        explanation_displayed_time,
    )

render_study_progress_footer(session_id, st.session_state["question_counter"])
