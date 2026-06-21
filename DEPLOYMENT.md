# Deployment guide for the thesis study app

This app can still run locally exactly as before. For the real online study, deploy it with Streamlit Community Cloud and store participant results in a hosted database.

## Recommended setup

Use:

- **Streamlit Community Cloud** for the public participant link.
- **Streamlit secrets** for the API key and database URL.
- **Hosted Postgres/Supabase** for study results.

Do not rely on `interactions.db` for the final online study. It is fine locally, but a hosted app can restart and local files are not a safe place for participant data.

## Files to deploy

Deploy one of these entrypoint files:

- Version A: `streamlit_agent/data_assistant_thesis_prototype.py`
- Version B: `streamlit_agent/data_assistant_thesis_prototype_kg.py`

For a clean study, you can create two Streamlit apps from the same GitHub repository: one for Version A and one for Version B.

## Streamlit secrets

In Streamlit Community Cloud, open your app settings and paste secrets like this:

```toml
openai_api_key = "YOUR_KEY_HERE"
model_name = "gpt-4o-mini"
study_database_url = "postgresql://USER:PASSWORD@HOST:PORT/DATABASE"
```

If you use Groq or another OpenAI-compatible provider, also add:

```toml
openai_base_url = "https://api.groq.com/openai/v1"
```

Never upload `.streamlit/secrets.toml` to GitHub.

## Hosted database

The app automatically creates these tables:

- `study_sessions`
- `questionnaire_responses`
- `interactions`

The app uses local SQLite when `study_database_url` is missing, and hosted Postgres when it is present.

## Running locally

From the project folder:

```powershell
streamlit run streamlit_agent/data_assistant_thesis_prototype.py
streamlit run streamlit_agent/data_assistant_thesis_prototype_kg.py
```

## Exporting results

Local SQLite:

```powershell
python streamlit_agent/analyze_study_results.py
```

Hosted database:

```powershell
python streamlit_agent/analyze_study_results.py --database-url "postgresql://USER:PASSWORD@HOST:PORT/DATABASE"
```

The workbook is created in `analysis_outputs/study_analysis.xlsx`.
