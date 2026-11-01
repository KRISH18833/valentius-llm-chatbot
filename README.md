# 🎓 StudyBuddy — AI Chatbot for Engineering Students

A multi-turn LLM chatbot powered by **Google Gemini** via FastAPI. StudyBuddy helps engineering students with maths, physics, programming, circuits, thermodynamics, and more — with answers kept under 150 words for quick, focused help.

---

## ✨ Features

| Feature | Details |
|---|---|
| Multi-turn conversations | Per-conversation history stored in memory |
| Context management | Truncates to last 10 messages; always starts with a user turn |
| System prompt | "StudyBuddy" persona — concise, under-150-word answers |
| Error handling | 30 s timeout · 429 rate limit · empty response · generic failure |
| Frontend | Single `index.html` — dark glassmorphism UI, suggestion chips, typing indicator |
| Config | `GEMINI_API_KEY` and `GEMINI_MODEL` loaded from `.env` via python-dotenv |

---

## 🚀 Quick Start

### 1. Clone & enter the project

```bash
git clone <repo-url>
cd valentius-llm-chatbot
```

### 2. Set up your API key

```bash
# Windows PowerShell
copy .env.example .env

# macOS / Linux
cp .env.example .env
```

Open `.env` and fill in your key:

```env
GEMINI_API_KEY=YOUR_KEY_HERE
GEMINI_MODEL=gemini-3.5-flash-lite
```

> **Never commit `.env`** — it is already in `.gitignore`.

### 3. Create a virtual environment & install dependencies

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
```

### 4. Run the app

```bash
uvicorn main:app --reload
```

Open **http://localhost:8000** in your browser.

---

## 🗂️ Project Structure

```
valentius-llm-chatbot/
├── main.py            # FastAPI backend (POST /chat, GET /, GET /health)
├── index.html         # Single-page frontend
├── requirements.txt   # Python dependencies
├── .env.example       # Template — copy to .env and add your key
├── .gitignore         # Ignores .env, venv/, __pycache__/
└── README.md
```

---

## 📡 API Reference

### `POST /chat`

```json
// Request
{
  "message": "Explain Ohm's Law",
  "conversation_id": null        // omit or null to start a new conversation
}

// Response
{
  "reply": "Ohm's Law states that V = IR ...",
  "conversation_id": "uuid-here"
}
```

**Error responses:**

| HTTP | Meaning |
|---|---|
| `422` | Empty or invalid message |
| `429` | Gemini rate limit hit |
| `504` | 30-second timeout |
| `502` | Gemini API error or empty response |

### `GET /health`

```json
{ "status": "ok", "model": "gemini-3.5-flash-lite" }
```

---

## ⚙️ Configuration

| Variable | Default | Description |
|---|---|---|
| `GEMINI_API_KEY` | *(required)* | Your Google AI Studio API key |
| `GEMINI_MODEL` | `gemini-3.5-flash-lite` | Gemini model to use |

---

## 🔒 Security Notes

- API key is **never** hardcoded — always loaded from `.env`.
- `.env` is listed in `.gitignore` and will never be committed.
- History is stored **in-memory** only; restarting the server clears all conversations.

---

## 📦 Dependencies

| Package | Purpose |
|---|---|
| `fastapi` | Web framework |
| `uvicorn` | ASGI server |
| `google-genai` | Official Gemini SDK |
| `python-dotenv` | Load `.env` variables |
| `httpx` | HTTP client (used by google-genai) |

---

## 📝 License

MIT
