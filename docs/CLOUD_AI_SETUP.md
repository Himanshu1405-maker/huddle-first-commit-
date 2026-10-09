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

## Use hosted AI without configuring a developer key

For Huddle accounts where no server-side provider key exists, the AI screen now offers **Connect hosted AI**. This is an optional Puter.js integration:

1. Open Huddle Intelligence, tap **Connect hosted AI** to load the lightweight connector script (not AI model weights).
2. Tap **Continue with Puter**. Puter opens its own authorization window, where the visitor can choose whether to sign in and permit third-party AI usage. Huddle does **not** see their Puter password.
3. Once connected, ask Huddle a question. The text is answered remotely using GPT-5.4 Mini via Puter. Requests are subject to Puter's account allowance and policies, which may include charges if the user chooses to exceed the free allowance. Huddle does not automatically enrol anyone in paid services.

**Privacy:** Prompts and recent AI assistant history are sent to Puter when that user initiates a request. A private Huddle conversation is included only after the separate **Use my last opened conversation as optional context** checkbox is explicitly selected. This uses short excerpts from the recap endpoint, not chat attachments. The completed response is saved only in the Huddle account that submitted it, and users can continue to use Huddle chat normally without connecting Puter.

If the Huddle owner later configures a server-side Gemini, Groq, OpenRouter or OpenAI key, the site's server provider takes precedence over Puter.

**Limitations:** This is an additional third-party account sign-in, not a shared free backend key or a free unlimited plan. External popups or network controls may prevent login in some in-app mobile browsers; opening Huddle in Chrome or another standard browser can help. Automated tests can verify the Huddle integration with a mocked Puter response, but a real AI answer requires an authenticated Puter account. No AI model weights are downloaded onto a visitor's device.
