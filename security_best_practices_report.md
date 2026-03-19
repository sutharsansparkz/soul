# Security Best Practices Report

## Executive Summary

This review covered the Python/Typer CLI runtime, SQLite/Redis/Celery persistence and job model, Telegram/voice presence adapters, and the local file-storage surfaces under `soul_data/`.

No remote-code-execution issue was identified in the current source. The most important weaknesses are:

1. operational secrets can still be exposed through CLI output,
2. highly sensitive conversation artifacts are written to disk without explicit permission hardening,
3. the default Redis/Celery Docker scaffold is unsafe outside a fully trusted local environment,
4. outbound Telegram and ElevenLabs calls do not use explicit timeouts or strict application-level response validation.

This repository does not match any exact framework-specific reference in the security skill's `references/` directory, so the findings below are based on concrete code inspection and general Python secure-coding practice.

## Scope

- Language: Python
- Primary frameworks/libraries: Typer, SQLAlchemy, Pydantic Settings, Celery, Redis, urllib, Rich
- Presence surfaces: Telegram Bot HTTP API client, ElevenLabs TTS, local Whisper/audio tooling

## Critical Severity

No critical findings were identified in the audited code.

## High Severity

No high-severity findings were identified in the audited code.

## Medium Severity

### SEC-001: CLI output can expose database and Redis credentials

Impact: anyone with access to terminal output, shell history capture, CI logs, or support screenshots can recover infrastructure credentials if they are embedded in `DATABASE_URL` or `REDIS_URL`.

Evidence:

- `Settings.as_redacted_dict()` redacts API keys and the Telegram bot token, but leaves `redis_url` untouched and re-inserts `database_url` verbatim. `soul/config.py:137-151`
- `soul config` prints the redacted settings object. `soul/cli.py:816-819`
- `soul status` prints the raw database URL. `soul/cli.py:688-699`
- `soul db init` prints the raw database URL. `soul/cli.py:808-813`

Recommended fix:

- sanitize `DATABASE_URL` and `REDIS_URL` before printing them,
- strip embedded usernames/passwords from URLs by default,
- only reveal full values behind an explicit opt-in such as `--show-secrets`.

### SEC-002: Sensitive local artifacts are written with default filesystem permissions

Impact: on shared machines or under a permissive umask, other local users may be able to read raw conversations, memory data, reflections, proactive logs, archived transcripts, and generated voice files.

Evidence:

- runtime state files are created with default permissions via `Path.write_text()` and directory creation without hardening. `soul/cli.py:62-80`
- the fallback JSONL memory store appends and rewrites memory content without explicit mode enforcement. `soul/memory/vector_store.py:47-54`, `soul/memory/vector_store.py:107-122`
- archived raw session transcripts, including message content and metadata, are written as JSONL files without permission hardening. `soul/tasks/consolidate.py:414-438`
- reflection history is persisted to disk without explicit file mode control. `soul/evolution/reflection.py:24-38`
- voice recordings and synthesized audio are saved to disk without explicit file mode control. `soul/presence/voice.py:87-99`, `soul/presence/voice.py:111-135`

Recommended fix:

- create the `soul_data` tree with restrictive permissions such as `0700`,
- create files with restrictive permissions such as `0600`,
- normalize existing files after writes where needed,
- document that these files contain sensitive personal data.

### SEC-003: The default Redis/Celery Docker scaffold is unsafe outside a trusted local environment

Impact: if the Compose stack is exposed beyond a fully trusted local machine, an attacker with network access can reach Redis, inspect mutable state, and potentially enqueue internal Celery tasks.

Evidence:

- Redis is published on the host interface with `6379:6379`. `docker-compose.yml:2-10`
- the example environment uses an unauthenticated Redis URL. `.env.example:9-11`
- Celery uses the same Redis URL as both broker and backend. `soul/celery_app.py:8-27`
- the README describes the repository as a fuller local-to-production runtime and presents the worker/beat scaffold without a security warning about Redis exposure. `README.md:3-18`, `README.md:48-56`

Recommended fix:

- remove the host port binding from the default Compose file,
- require authenticated Redis for any non-local deployment,
- document this stack as dev-only unless Redis is network-isolated and protected,
- consider separate broker/backend credentials and explicit production deployment docs.

## Low Severity

### SEC-004: Outbound Telegram and ElevenLabs calls have no explicit timeout and only partial response validation

Impact: network stalls can hang bot or voice operations indefinitely, and application-level API failures may be treated as success, weakening operational resilience and incident visibility.

Evidence:

- Telegram requests use `urlopen` through the injected opener without passing an explicit timeout. `soul/presence/telegram.py:74-94`
- `TelegramClient.send_message()` assumes success if `_post()` returns any JSON and does not verify the upstream `"ok"` field. `soul/presence/telegram.py:60-72`
- proactive delivery trusts the `send_message()` result and records delivery once `ok` is true. `soul/tasks/proactive.py:187-205`
- ElevenLabs synthesis also performs a network call without an explicit timeout. `soul/presence/voice.py:121-139`

Recommended fix:

- set explicit connect/read timeouts on outbound HTTP requests,
- validate provider response bodies rather than relying only on transport success,
- propagate upstream error messages/codes into the result objects.

## Positive Controls Observed

- SQL access is parameterized through SQLAlchemy text bindings rather than string interpolation for user-controlled values. `soul/db.py`
- YAML parsing uses `yaml.safe_load()` rather than unsafe deserialization. `soul/core/soul_loader.py:30-33`
- Telegram handling is now gated to the configured chat id, which reduces cross-chat data contamination. `soul/presence/telegram.py:123-153`

## Recommended Remediation Order

1. Fix `SEC-001` to stop leaking infrastructure credentials through normal operator workflows.
2. Fix `SEC-002` to harden local storage of personal conversation data.
3. Fix `SEC-003` by locking down the default Redis/Celery deployment story.
4. Fix `SEC-004` to improve resilience and failure signaling for external network calls.
