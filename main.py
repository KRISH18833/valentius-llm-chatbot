"""
StudyBuddy - Multi-turn LLM Chatbot powered by Google Gemini.
"""

import asyncio
import os
import uuid
from collections import defaultdict
from typing import Optional

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

load_dotenv()

GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
MAX_HISTORY_MESSAGES: int = 10   # keep last N messages; must start with a user turn
CHAT_TIMEOUT_SECONDS: int = 30
MAX_RETRIES: int = 3
RETRY_BACKOFF_SECONDS: list[float] = [2.0, 4.0]  # waits before attempt 2 and 3

if not GEMINI_API_KEY:
    raise RuntimeError(
        "GEMINI_API_KEY is not set. Copy .env.example → .env and add your key."
    )

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "You are StudyBuddy, a friendly and knowledgeable study assistant designed "
    "specifically for engineering students. You help with concepts from subjects "
    "like mathematics, physics, programming, circuits, thermodynamics, and more. "
    "Always keep your answers concise — under 150 words — and use simple language. "
    "When helpful, use bullet points or short numbered steps. "
    "If a question is outside engineering/academics, politely redirect the student."
)

# ---------------------------------------------------------------------------
# Gemini client
# ---------------------------------------------------------------------------

client = genai.Client(
    api_key=GEMINI_API_KEY,
    http_options=types.HttpOptions(timeout=30_000),  # 30 000 ms = 30 s
)

# ---------------------------------------------------------------------------
# In-memory conversation store
# { conversation_id: [ {"role": "user"|"model", "parts": [{"text": "..."}]} ] }
# ---------------------------------------------------------------------------

conversation_store: dict[str, list[dict]] = defaultdict(list)


def _truncate_history(history: list[dict]) -> list[dict]:
    """
    Keep at most MAX_HISTORY_MESSAGES messages.
    After slicing, ensure the list starts with a user message
    (Gemini requires history to begin with a user turn).
    """
    if len(history) <= MAX_HISTORY_MESSAGES:
        return history

    truncated = history[-MAX_HISTORY_MESSAGES:]

    # Advance until we find a user-role message at index 0
    while truncated and truncated[0]["role"] != "user":
        truncated = truncated[1:]

    return truncated


async def _call_with_retry(
    contents: list,
    config: types.GenerateContentConfig,
) -> object:
    """
    Call Gemini with a per-request timeout and automatic retry on 503/UNAVAILABLE.
    Retries up to MAX_RETRIES times, waiting RETRY_BACKOFF_SECONDS between attempts.
    Raises:
        asyncio.TimeoutError  – if a single attempt exceeds CHAT_TIMEOUT_SECONDS.
        HTTPException 429     – on rate-limit errors.
        HTTPException 503     – when all retry attempts are exhausted on 503.
        HTTPException 502     – on any other Gemini error.
    """
    last_exc: Exception | None = None

    for attempt in range(MAX_RETRIES):
        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    client.models.generate_content,
                    model=GEMINI_MODEL,
                    contents=contents,
                    config=config,
                ),
                timeout=CHAT_TIMEOUT_SECONDS,
            )
            return response  # success — stop retrying

        except asyncio.TimeoutError:
            raise  # timeout is not retried; bubble up immediately

        except Exception as exc:
            err_str = str(exc).lower()

            # 429 / quota — not retried
            if "429" in err_str or "resource_exhausted" in err_str or "quota" in err_str:
                raise HTTPException(
                    status_code=429,
                    detail="Rate limit reached. Please wait a moment and try again.",
                )

            # 503 / UNAVAILABLE — retry with backoff
            if "503" in err_str or "unavailable" in err_str:
                last_exc = exc
                if attempt < MAX_RETRIES - 1:
                    backoff = RETRY_BACKOFF_SECONDS[min(attempt, len(RETRY_BACKOFF_SECONDS) - 1)]
                    await asyncio.sleep(backoff)
                    continue  # next attempt
                # All retries exhausted
                raise HTTPException(
                    status_code=503,
                    detail="The AI service is busy right now. Please try again in a moment.",
                )

            # Any other error — fail immediately
            raise HTTPException(
                status_code=502,
                detail=f"The AI service returned an error. Please try again. ({type(exc).__name__})",
            )

    # Should be unreachable, but satisfy type-checker
    raise HTTPException(status_code=503, detail="The AI service is busy right now. Please try again in a moment.")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="StudyBuddy Chatbot", version="1.0.0")


# Serve the single-page frontend
@app.get("/", response_class=FileResponse)
async def serve_frontend():
    return FileResponse("index.html", media_type="text/html")


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000, description="User message")
    conversation_id: Optional[str] = Field(
        default=None, description="Omit to start a new conversation"
    )


class ChatResponse(BaseModel):
    reply: str
    conversation_id: str


# ---------------------------------------------------------------------------
# POST /chat
# ---------------------------------------------------------------------------


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Multi-turn chat endpoint.
    - Creates a new conversation_id if none is supplied.
    - Maintains per-conversation history in memory.
    - Truncates history to the last MAX_HISTORY_MESSAGES messages.
    - Enforces a CHAT_TIMEOUT_SECONDS timeout on the Gemini API call.
    """
    # Resolve conversation ID
    conversation_id: str = request.conversation_id or str(uuid.uuid4())
    user_message: str = request.message.strip()

    if not user_message:
        raise HTTPException(status_code=422, detail="Message cannot be empty.")

    # Append the new user turn to history
    history = conversation_store[conversation_id]
    history.append({"role": "user", "parts": [{"text": user_message}]})

    # Truncate before sending
    trimmed_history = _truncate_history(history)

    # Build the contents list for the Gemini API
    contents = [
        types.Content(
            role=turn["role"],
            parts=[types.Part(text=p["text"]) for p in turn["parts"]],
        )
        for turn in trimmed_history
    ]

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        max_output_tokens=300,
        temperature=0.7,
    )

    # Call Gemini with retry logic (handles 503 with backoff)
    try:
        response = await _call_with_retry(contents, config)
    except asyncio.TimeoutError:
        history.pop()
        raise HTTPException(
            status_code=504,
            detail="The request timed out after 30 seconds. Please try again.",
        )
    except HTTPException:
        history.pop()
        raise  # already formatted by _call_with_retry
    except Exception as exc:
        history.pop()
        raise HTTPException(
            status_code=502,
            detail=f"The AI service returned an error. Please try again. ({type(exc).__name__})",
        )

    # Validate response
    reply_text: str = ""
    try:
        reply_text = response.text or ""
    except Exception:
        pass

    if not reply_text.strip():
        history.pop()
        raise HTTPException(
            status_code=502,
            detail="The AI returned an empty response. Please rephrase your question.",
        )

    # Persist model reply
    history.append({"role": "model", "parts": [{"text": reply_text}]})
    # Keep the stored history bounded too
    conversation_store[conversation_id] = _truncate_history(history)

    return ChatResponse(reply=reply_text, conversation_id=conversation_id)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@app.get("/health")
async def health():
    return {"status": "ok", "model": GEMINI_MODEL}
