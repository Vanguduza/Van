# VAN Gateway

Secure owner-authority layer in front of Hermes profile `van`.

## Run

```bash
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
pytest
uvicorn van_gateway.app:app --port 8787
```

## Environment

| Variable | Purpose |
|---|---|
| `VAN_DATABASE_PATH` | SQLite path |
| `VAN_HERMES_BASE_URL` | Hermes gateway |
| `VAN_HERMES_BEARER_TOKEN` | Hermes API token |
| `VAN_GOOGLE_TOKEN_FERNET_KEY` | Fernet key for OAuth token encryption |

Google OAuth tokens never enter LLM prompts. Gemini uses a separate Hermes runtime credential.
