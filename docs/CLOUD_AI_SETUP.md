# Huddle Intelligence — cloud-only setup

The assistant **never downloads or runs model weights in visitors' browsers**. It uses hosted inference over HTTPS, through Huddle's existing authenticated FastAPI server. Chat, messages, documents, media and Poster Studio work independently of cloud AI.

## Connect a capable AI provider

The Railway production service **does not currently have an AI provider key**. Until one is added, Huddle displays an honest "Cloud AI requires administrator setup" notice, disables AI text submissions, and continues supporting all other features. No key is required on the user's phone.

In Railway, open the existing Huddle service, choose **Variables**, and add **one** of the following (keep it server-side; never commit credentials to GitHub or put them in HTML/JavaScript):

| Provider | Required Railway variable | Optional model override | Default model |
| --- | --- | --- | --- |
| Google Gemini | `GEMINI_API_KEY` | `GEMINI_MODEL` | `gemini-3.5-flash` |
| Groq | `GROQ_API_KEY` | `GROQ_MODEL` | `openai/gpt-oss-120b` |
| OpenRouter | `OPENROUTER_API_KEY` | `OPENROUTER_MODEL` | `openai/gpt-4.1` |
| OpenAI API | `OPENAI_API_KEY` | `OPENAI_MODEL` | `gpt-4.1` |

When several keys are configured, set `HUDDLE_AI_PROVIDER` to `gemini`, `groq`, `openrouter` or `openai`. Otherwise Huddle prefers Gemini, Groq, OpenRouter, then OpenAI. Railway will redeploy on variable changes. Check `/api/config`: `ai_chat` should become `true` and `ai_local` remains `false`; no keys appear in this endpoint.

Provider accounts, rate limits, availability and potential charges depend on the chosen provider. A ChatGPT subscription does not automatically supply an API key, and Huddle cannot produce remote AI responses without appropriate provider access.

## Privacy and behaviour

* API keys live **only on Railway**, never in browser JavaScript.
* Cloud AI requires Huddle sign-in and existing per-user request limits.
* Huddle sends the user's AI question plus relevant **own AI conversation history** to the selected provider. It does not automatically send their private chats.
* The optional **Use my last opened conversation as context** checkbox sends up to 14 recent excerpts **only when explicitly enabled** and **only after the server rechecks conversation membership**.
* AI conversations already stored in the SQLite database are preserved. Third-party AI providers may process prompts according to their policies.
* The prior browser-based Qwen/SmolLM worker has been removed. Previously downloaded browser model caches are no longer used; individual browsers may retain old caches until site storage is cleared by their owner.
* No change was made to Huddle's persistent Railway /data volume, SQLite records, file uploads or encryption key.

## Testing

Run `python -m pytest -q` and `node --check app/web/app.js` plus the GitHub Actions suite. Tests use fake credentials and mocked provider responses; they **do not prove live provider availability**. After entering a real provider key, sign in and ask a few factual and reasoning questions to verify the live provider connection. For accessibility, the AI setup and failure message stays visible instead of starting a loading spinner or model download.
