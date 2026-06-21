# LLM Data Assistant Thesis Prototype

This repository contains two Streamlit prototype versions for a bachelor thesis study about LLM-based data assistants and knowledge graph support.

## Prototype Versions

- **Version A: Baseline assistant**  
  Answers questions using the database schema and SQL reasoning.

- **Version B: Knowledge graph-supported assistant**  
  Adds knowledge graph context, written explanations, and an animated reasoning path to show how business concepts connect to tables, columns, and joins.

## Run Locally

Install dependencies:

```powershell
pip install -r requirements.txt
```

Add your API key in `.streamlit/secrets.toml`. Use `.streamlit/secrets.example.toml` as a template.

Run Version A:

```powershell
streamlit run streamlit_agent/data_assistant_thesis_prototype.py
```

Run Version B:

```powershell
streamlit run streamlit_agent/data_assistant_thesis_prototype_kg.py
```

## Study Data

Locally, study results are saved to `interactions.db`.

For online deployment, configure `study_database_url` in Streamlit secrets so participant data is stored in a hosted Postgres/Supabase database instead of a local file.

See [DEPLOYMENT.md](DEPLOYMENT.md) for the deployment steps.
