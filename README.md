"""
# 🔍 Convergence

Multi-Agent Pull Request Review System

## Quick Start

```bash
# 1. Clone and install
git clone <your-repo>
cd convergence
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env with your credentials

# 3. Run
uvicorn app.main:app --reload --port 8000

# 4. Open dashboard
open http://localhost:8000/dashboard
```

## Features

- 🤖 **Multi-Agent Analysis**: Security, Performance, and Testing agents work in parallel
- 🔄 **Convergence Algorithm**: Merges findings, boosts severity on agreement
- 📊 **Real-time Dashboard**: Watch agents analyze code live
- 🐙 **GitHub Integration**: Fetches PRs and posts reviews automatically

## Architecture

```
GitHub PR → Webhook → Orchestrator → [Agents in Parallel] → Convergence → GitHub Review
                           ↓                    ↓                ↓
                        MongoDB             MongoDB          MongoDB
                    (create session)    (store findings)  (final review)
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/dashboard` | Web UI |
| POST | `/webhook/github` | GitHub webhook receiver |
| POST | `/webhook/test-pr` | Create session manually |
| POST | `/webhook/sessions/{id}/review` | Run full pipeline |
| GET | `/webhook/sessions/{id}/findings` | Get findings |

## Tech Stack

- **Backend**: FastAPI, Python 3.11
- **Database**: MongoDB Atlas
- **AI**: Google Gemini (gemini-1.5-flash)
- **Frontend**: React (CDN), Tailwind CSS

## License

MIT
"""