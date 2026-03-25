# CHANGELOG


## v0.2.0 (2026-03-25)

### Features

- Enhance error handling in LLM interactions and add license file
  ([`fab0d20`](https://github.com/sparkz-technology/soul/commit/fab0d2001c22a803adbcb3247dd27073d58bcf36))


## v0.1.0 (2026-03-25)

### Bug Fixes

- Add DDL injection guards to _ensure_columns and migrate_postgres_jsonb
  ([`9e6e253`](https://github.com/sparkz-technology/soul/commit/9e6e2537370aa4e544d715b5accfdc350bb34911))

Both functions interpolated caller-supplied strings directly into ALTER TABLE statements executed
  via exec_driver_sql, allowing arbitrary DDL if an attacker could influence the table name, column
  name, or type definition.

Changes: - _validate_sql_identifier(): rejects any value not matching [A-Za-z_][A-Za-z0-9_]* -
  _ALLOWED_TABLE_NAMES: explicit frozenset; unknown tables raise ValueError -
  _ALLOWED_COLUMN_DEFINITIONS: explicit frozenset of permitted type strings -
  _JSONB_MIGRATION_COLUMNS: column names in migrate_postgres_jsonb now validated through
  _validate_sql_identifier before interpolation

20 new tests in tests/test_sql_injection_guards.py cover valid identifiers, injection payloads
  (semicolons, comments, spaces), unknown table/definition rejection, and the postgres-skip path.

Co-authored-by: Ona <no-reply@ona.com>

- Switch to OpenAI-compatible backend only and fix four bugs
  ([`5feab4b`](https://github.com/sparkz-technology/soul/commit/5feab4be6339b91f153d8089daf81bc5741bf0a0))

LLM backend - Remove Anthropic SDK dependency entirely (llm_client.py, requirements.txt,
  pyproject.toml) - Single OpenAI-compatible backend via the openai package - Add OPENAI_BASE_URL
  setting so any compatible endpoint works (Ollama, LM Studio, Together AI, Azure OpenAI, etc.) -
  LLM_MODEL default changed from claude-sonnet-4-6 to gpt-4o - Remove FALLBACK_LLM_MODEL — there is
  now one model, one provider

Bug fixes - mood_engine.py: MODEL_LABEL_MAP corrected to the exact 7 labels output by
  cardiffnlp/twitter-roberta-base-emotion; disgust was missing (silently discarded) and 7 dead
  go-emotions entries removed - cli.py: _next_milestone_label condition was inverted — 100th-message
  countdown now shows only while total_messages < 100 and the milestone is not yet recorded -
  mood_engine.py + config.py: MOOD_MODEL_ENABLED defaults to True; emits a one-time UserWarning when
  transformers is absent instead of silently degrading with no indication - consolidate.py: warning
  messages updated to reference OPENAI_API_KEY only

Co-authored-by: Ona <no-reply@ona.com>

### Chores

- Update GitHub Actions to use latest versions of checkout and setup-python
  ([`045a8ca`](https://github.com/sparkz-technology/soul/commit/045a8ca6ab3315de64516e692dcd2ba1e8b4f1cd))

- **release**: 0.1.0 [skip ci]
  ([`a8009c0`](https://github.com/sparkz-technology/soul/commit/a8009c09cac2cb2d4509d29efb9ea0be605dfea5))

### Features

- Add GitHub Actions workflow for running tests
  ([`62f21a9`](https://github.com/sparkz-technology/soul/commit/62f21a9c31a05fdd1456b9e0a51e447d916d2b76))

- Add optional birthday field to user stories and update related tests
  ([`fb1eea2`](https://github.com/sparkz-technology/soul/commit/fb1eea2d11dd192c539493c493c24d02edd2b6a6))

- Add Security Best Practices Report detailing vulnerabilities and recommended fixes
  ([`ef615be`](https://github.com/sparkz-technology/soul/commit/ef615be4b1944400d1c570cbb3f864aa363a759c))

- Add session memory export tracking and archiving functionality
  ([`78b7d27`](https://github.com/sparkz-technology/soul/commit/78b7d270c4429aab2dcbaa978343158b54d13aab))

- Introduced a new table `session_memory_exports` to track exported sessions. - Implemented
  `mark_session_memory_exported` and `is_session_memory_exported` functions for managing session
  export status. - Added `list_completed_sessions_with_messages_before` to retrieve sessions for
  archiving. - Created `archive_and_purge_old_session_messages` to archive old sessions and delete
  their messages based on retention policy. - Enhanced `UserStory` model to include
  `upcoming_events` and related extraction logic. - Updated proactive triggers to consider upcoming
  events and stress signals. - Added tests for memory search, clearing, context building, and
  proactive triggers. - Introduced persona conversation fixtures for regression testing.

- Add VSCode settings to control ChatGPT startup behavior
  ([`7f68de1`](https://github.com/sparkz-technology/soul/commit/7f68de1a7b1d1f80b1ed46dee8fbd5136581df0c))

- Enhance drift task functionality and add settings parameter; improve memory cleanup in tests
  ([`88e0521`](https://github.com/sparkz-technology/soul/commit/88e0521ef3555442417bacad23c8cbc6a320fdce))

- Enhance memory management with HMS scoring and retrieval
  ([`743f932`](https://github.com/sparkz-technology/soul/commit/743f932d016269082b006f07123b06f5d0edb001))

- Updated MemoryRecord to support more flexible metadata types. - Introduced MemoryRetriever for
  improved memory retrieval with HMS scoring. - Added HMSComponents and scoring functions to
  calculate emotional, retrieval, and temporal scores. - Implemented decay logic for memories to
  transition to 'cold' based on age and score thresholds. - Enhanced CLI commands to include
  HMS-related functionalities. - Added tests for HMS scoring, retrieval, and decay processes to
  ensure reliability.

- Enhance memory retrieval and management with unified search and HMS scoring updates
  ([`80b6f6f`](https://github.com/sparkz-technology/soul/commit/80b6f6f52f78974e9a1a9d408041c97a2657d60e))

- Updated `soul memories search` to perform unified search across episodic and manual memories with
  HMS-aware ranking. - Enhanced memory schema to include new fields for HMS scoring and retrieval
  behavior. - Implemented new filtering capabilities in memory retrieval to exclude non-user
  memories. - Added comprehensive documentation for API and architecture, detailing CLI commands and
  memory management strategies. - Introduced tests for memory retrieval and consolidation processes
  to ensure correct functionality and data integrity.

- Enhance mood classification and voice command handling; add tests for runtime file creation
  ([`5d1fbcf`](https://github.com/sparkz-technology/soul/commit/5d1fbcfb9256964cc4ccd16519b02c76e820a588))

- Enhance session memory export functionality and update documentation for Python version
  requirements
  ([`eb682ce`](https://github.com/sparkz-technology/soul/commit/eb682ce2cc58ab3895b8794e557beb623a420c6b))

- Implement AST visitor to detect module-level get_settings() calls
  ([`d2cfe5c`](https://github.com/sparkz-technology/soul/commit/d2cfe5cae505577f5179e0c03fa522fbd1854bab))

- Implement hybrid embeddings and FTS for episodic memory retrieval
  ([`08e097b`](https://github.com/sparkz-technology/soul/commit/08e097ba947e3d0ac9fab30284ff11b3b256f88a))

- Added hybrid embedding configuration options in Settings. - Introduced LocalHybridEmbedder for
  encoding and decoding embeddings. - Enhanced episodic memory repository to store embeddings and
  utilize hybrid retrieval. - Implemented FTS (Full-Text Search) for efficient memory searching with
  ranking. - Updated database schema to include embedding storage and FTS triggers. - Modified
  memory retrieval logic to incorporate BM25 scoring and cosine similarity. - Added tests for
  embedder functionality and FTS search capabilities.

- Implement URL redaction for database and Redis credentials in settings
  ([`ef53ced`](https://github.com/sparkz-technology/soul/commit/ef53cedd99b2ea7285f650cc309a80f9f004cf51))

- Improve testing setup with Python version checks and pytest installation verification
  ([`e5b8374`](https://github.com/sparkz-technology/soul/commit/e5b837424c644ef372bcfbc02d1778e58d7916d8))

- Introduce comprehensive documentation, new core configuration and database modules, and remove
  Docker infrastructure.
  ([`3647815`](https://github.com/sparkz-technology/soul/commit/36478159e831ec9817bebf7ae4c1890d962d8141))

- Mock MoodEngine's _openai_mood method in voice CLI tests for improved test isolation
  ([`e3665a9`](https://github.com/sparkz-technology/soul/commit/e3665a96745c6e0644fc9b8c2e2507fc97fee7a4))

- Remove obsolete data files and logs to streamline project structure
  ([`19a7756`](https://github.com/sparkz-technology/soul/commit/19a77562d41dd25b4725239dab72627e7a23347b))

- Transition mood classification to OpenAI API; update settings and refactor related components
  ([`6d9962a`](https://github.com/sparkz-technology/soul/commit/6d9962a1b6440005c903c9080e377bee4458c285))

- Update default timezone to UTC and enhance voice output handling; add tests for timezone settings
  and voice output autoplay
  ([`8770d3a`](https://github.com/sparkz-technology/soul/commit/8770d3a9a36fb384ea1b221e586927f529413ab8))

- Update documentation and remove legacy chroma references from tests
  ([`8f2acd6`](https://github.com/sparkz-technology/soul/commit/8f2acd6cad9e26ae2e598598acc5c6fd3d653fc9))

- Update mood engine to ensure neutral state decay and adjust tests for consistency
  ([`c24baba`](https://github.com/sparkz-technology/soul/commit/c24baba998ed4ecc34032ac8a74c620e2bab0229))

### Refactoring

- Update LLM references to OpenAI API and enhance mood classification details
  ([`1b6e234`](https://github.com/sparkz-technology/soul/commit/1b6e234d73f805c2a6f24bee257e140776ffb591))
