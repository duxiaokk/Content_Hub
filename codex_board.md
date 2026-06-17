# Content Hub MVP - Codex Board

> 鎬昏繘搴︾湅鏉?路 19 涓换鍔?路 鎸夋帹鑽愬紑鍙戦『搴忔帓鍒?
---

## 鏁翠綋杩涘害

| 瀹屾垚 | 鎬昏 | 杩涘害 |
|------|------|------|
| 19 | 19 | 100% |

---

## Phase 1: 鏁版嵁妯″瀷 (1 task)

| 缂栧彿 | 浠诲姟 | 鐘舵€?| 妯″潡 |
|------|------|------|------|
| [T001](tasks/T001_db_migration_batch1.md) | db_migration_batch1 - 鏁版嵁妯″瀷鎵╁睍 | DONE | DB |

---

## Phase 2: Fetcher Engine (6 tasks)

| 缂栧彿 | 浠诲姟 | 鐘舵€?| 妯″潡 |
|------|------|------|------|
| [T002](tasks/T002_fetch_service_unified.md) | fetch_service_unified - 缁熶竴鍏ュ彛 FetchService | DONE | fetcher_engine |
| [T003](tasks/T003_rss_fetcher_stable.md) | rss_fetcher_stable - RSS 鎶撳彇鍣ㄧǔ瀹氬寲 | DONE | fetcher_engine |
| [T004](tasks/T004_github_trending_fetcher.md) | github_trending_fetcher - GitHub Trending | DONE | fetcher_engine |
| [T005](tasks/T005_reddit_fetcher.md) | reddit_fetcher - Reddit 鎶撳彇鍣?| DONE | fetcher_engine |
| [T006](tasks/T006_cnblogs_bilibili_fields.md) | cnblogs_bilibili_fields - CNBlogs/Bilibili 瀛楁琛ラ綈 | DONE | fetcher_engine |
| [T007](tasks/T007_incremental_cursor.md) | incremental_cursor - 澧為噺鎺у埗 + 澶辫触瀹归敊 | DONE | fetcher_engine |

---

## Phase 3: AI Processor (2 tasks)

| 缂栧彿 | 浠诲姟 | 鐘舵€?| 妯″潡 |
|------|------|------|------|
| [T008](tasks/T008_ai_summarize_classify_tag.md) | ai_summarize_classify_tag - 鎽樿/鍒嗙被/鏍囩 | DONE | ai_processor |
| [T009](tasks/T009_ai_rewrite_config.md) | ai_rewrite_config - 鏀瑰啓澶勭悊鍣?+ 缁熶竴閰嶇疆 | DONE | ai_processor |

---

## Phase 4: Workflow Engine (2 tasks)

| 缂栧彿 | 浠诲姟 | 鐘舵€?| 妯″潡 |
|------|------|------|------|
| [T010](tasks/T010_workflow_radar_template.md) | workflow_radar_template - radar_pipeline 鑺傜偣瀹氫箟 | DONE | workflow_engine |
| [T011](tasks/T011_workflow_trace_idempotency.md) | workflow_trace_idempotency - 杩愯杞ㄨ抗 + 骞傜瓑鎺у埗 | DONE | workflow_engine |

---

## Phase 5: Platform API (3 tasks)

| 缂栧彿 | 浠诲姟 | 鐘舵€?| 妯″潡 |
|------|------|------|------|
| [T012](tasks/T012_platform_source_api.md) | platform_source_api - 淇℃簮绠＄悊 CRUD API | DONE | platform |
| [T013](tasks/T013_platform_review_api.md) | platform_review_api - 瀹℃牳闃熷垪 API | DONE | platform |
| [T014](tasks/T014_platform_digest_api.md) | platform_digest_api - 鏃ユ姤 API | DONE | platform |

---

## Phase 6: Publisher Engine (2 tasks)

| 缂栧彿 | 浠诲姟 | 鐘舵€?| 妯″潡 |
|------|------|------|------|
| [T015](tasks/T015_publisher_markdown.md) | publisher_markdown - Markdown 鏃ユ姤鐢熸垚鍣?| DONE | publisher_engine |
| [T016](tasks/T016_publisher_blog_draft.md) | publisher_blog_draft - 鍗氬鑽夌鍙戝竷 + 鍙戝竷璁板綍 | DONE | publisher_engine |

---

## Phase 7: Scheduler + Frontend + Tests (3 tasks)

| 缂栧彿 | 浠诲姟 | 鐘舵€?| 妯″潡 |
|------|------|------|------|
| [T017](tasks/T017_scheduler_cron.md) | scheduler_cron - 瀹氭椂浠诲姟閰嶇疆 | DONE | scheduler_center |
| [T018](tasks/T018_frontend_minimal_pages.md) | frontend_minimal_pages - 鍓嶇鏈€灏忛〉闈?| DONE | frontend |
| [T019](tasks/T019_tests_and_config.md) | tests_and_config - 娴嬭瘯 + 閰嶇疆鏁寸悊 | DONE | tests |

---

## 浠诲姟渚濊禆鍥?
```mermaid
graph TD
    T001["T001: 鏁版嵁妯″瀷"] --> T002["T002: FetchService"]
    T001 --> T010["T010: Workflow 妯℃澘"]
    T001 --> T012["T012: 淇℃簮 CRUD"]
    T002 --> T003["T003: RSS 绋冲畾鍖?]
    T002 --> T004["T004: GitHub Trending"]
    T002 --> T005["T005: Reddit"]
    T002 --> T006["T006: CNBlogs/Bilibili"]
    T003 --> T007["T007: 澧為噺鎺у埗"]
    T004 --> T007
    T005 --> T007
    T006 --> T007
    T007 --> T008["T008: AI 鎽樿/鍒嗙被/鏍囩"]
    T008 --> T009["T009: AI 鏀瑰啓 + 閰嶇疆"]
    T009 --> T010
    T010 --> T011["T011: 杩愯杞ㄨ抗 + 骞傜瓑"]
    T012 --> T013["T013: 瀹℃牳闃熷垪 API"]
    T011 --> T013
    T013 --> T014["T014: 鏃ユ姤 API"]
    T011 --> T015["T015: Markdown 鏃ユ姤"]
    T013 --> T016["T016: 鍗氬鑽夌鍙戝竷"]
    T015 --> T017["T017: 瀹氭椂浠诲姟"]
    T016 --> T017
    T012 --> T018["T018: 鍓嶇椤甸潰"]
    T014 --> T018
    T017 --> T019["T019: 娴嬭瘯 + 閰嶇疆"]
```

---

## 閲岀▼纰戦獙鏀?
| 閲岀▼纰?| 娑夊強浠诲姟 | 楠屾敹鏍囧噯 |
|--------|----------|----------|
| M1: 鎶撳彇闂幆 | T001~T007 | 鍙厤缃嚦灏?3 涓俊婧愶紱鎶撳彇缁撴灉缁熶竴鍏ュ簱锛涙敮鎸佸幓閲嶅拰鍏抽敭璇嶈繃婊?|
| M2: AI 澶勭悊闂幆 | T008~T009 | 鍙敓鎴愭憳瑕侊紱鍙敓鎴愪腑鏂囨敼鍐欑锛涘鐞嗗け璐ユ湁鏄庣‘闄嶇骇 |
| M3: 瀹℃牳闂幆 | T010~T013 | 鎺у埗鍙板彲鏌ョ湅寰呭鏍稿唴瀹癸紱鍙€氳繃/椹冲洖/褰掓。锛涘彲缂栬緫鏈€缁堢 |
| M4: 鍙戝竷闂幆 | T014~T016 | 瀹℃牳閫氳繃鍚庡彲鐢熸垚鍗氬鑽夌锛涘彲鐢熸垚鏃ユ姤 Markdown锛涘彲鏌ョ湅鍙戝竷缁撴灉璁板綍 |
| M5: 璋冨害闂幆 | T017~T019 | 姣忓ぉ 09:00 鑷姩杩愯锛涘彲鏌ョ湅杩愯鐘舵€佸拰閿欒淇℃伅锛涢噸璺戜笉閲嶅鍙戝竷 |

---

*鏈€鍚庢洿鏂帮細2026-06-11*

## Notes

- 2026-06-12: T003 revalidated. RSS fetcher registration, empty-feed 0-item handling, cursor writeback, and RSS exception -> `FetchBatchResult.errors` integration tests now pass.
- 2026-06-12: T004 completed. GitHub Trending fetcher is registered, parses repository cards into `SourceItem`, and degrades to `[]` on network errors. Acceptance tests pass.
- 2026-06-12: T005 completed. Reddit fetcher now reads public subreddit JSON, maps posts into `SourceItem`, and returns `[]` on 404/network failures. Acceptance tests pass.
- 2026-06-12: T006 completed. CNBlogs and Bilibili fetchers now fill normalized source metadata, summary, URL, and published time fields. Acceptance tests pass.
- 2026-06-12: T007 completed. FetchService now stores JSON cursors, filters incrementally across runs, and reports per-source success/failure stats. Acceptance tests pass.
- 2026-06-12: T008 completed. Summarize, classify, and tag processors now run with fallback behavior and can write summary/tags/score back to content_items. Acceptance tests pass.
- 2026-06-12: T009 completed. Rewrite processing now loads profile-aware config, applies score threshold gating, and writes rewritten fields back to content_items. Acceptance tests pass.
- 2026-06-12: T010 completed. radar_pipeline template, filter node, workflow contracts, and radar service flow are now available. Acceptance tests pass.
- 2026-06-12: T011 completed. workflow_run persistence, step-level trace payload, token cost aggregation, and publish idempotency checks were added. Workflow tests pass.
- 2026-06-12: T012 completed. Source subscription CRUD API, source service layer, and source API tests are now available. Acceptance tests pass.
- 2026-06-12: T013 completed. Review queue list/detail/approve/reject/archive APIs are now available, including edited-content approval flow. Acceptance tests pass.
- 2026-06-12: T014 completed. Digest list/detail/generate/download APIs are now available, and approved content can be assembled into persisted markdown digests. Acceptance tests pass.
- 2026-06-13: T015 completed. Markdown digest publisher now writes dated files under `CONTENT_HUB_DIGEST_OUTPUT_DIR`, digest generation routes through `publisher_engine`, and success/failed publish records are persisted with platform API coverage. Acceptance tests pass.
- 2026-06-13: T016 completed. Blog draft publishing now writes unpublished posts, persists success/failed publish records, marks content items as published, and skips duplicate blog publishes. Acceptance tests pass.
- 2026-06-14: T017 completed. Scheduler cron jobs now enqueue daily radar and daily digest tasks, scheduler startup respects `CONTENT_HUB_SCHEDULER_ENABLED`, and internal trigger endpoints for radar/daily-digest are available. Acceptance tests pass.
- 2026-06-14: T018 completed. Frontend source management, content list, review queue, and digest pages are wired to the current content APIs and routes. `npx tsc -b` passes; `vite build` still fails in this environment with `spawn EPERM` when `esbuild` starts.
- 2026-06-14: T019 completed. Added focused fetcher/AI/workflow/publisher tests, refreshed platform API/integration coverage, appended Content Hub env examples, and added root pytest discovery config. `pytest apps/fetcher_engine/tests apps/ai_processor/tests apps/publisher_engine/tests apps/workflow_engine/tests -v` and targeted platform API/integration pytest groups pass.
- 2026-06-14: Pytest cache permission warnings (`pytest-cache-files-*`) still appear in this workspace, and `apps/platform/pyproject.toml` now declares `asyncio_mode`, but the current environment lacks `pytest-asyncio`, so that config still emits an unknown-option warning.
- 2026-06-11: T001 revalidated. Alembic `upgrade` / `downgrade` passes on a clean temp SQLite database.
- 2026-06-11: Default workspace SQLite files under `apps/platform/*.db` still raise `disk I/O error`; keep T001 as `DONE`, but this local database file issue still needs environment cleanup or file replacement.
- 2026-06-12: T011 Alembic path import issue is fixed in `migrations/env.py`, but SQLite migration commands still hit environment-level `disk I/O error` on local file databases during `alembic upgrade/current/downgrade`.
- 2026-06-12: Pytest cache now targets `.tmp/.pytest_cache`, but this workspace still denies creation of pytest atomic temp directories (`pytest-cache-files-*`), so cache warnings may persist until filesystem permissions are fixed.
- 2026-06-16: Agent control plane migration M01-M05 completed. B-side entrypoints are unified, `ContentDomainClient` now mediates B -> A calls for radar/digest/publish capabilities, scheduler dispatch no longer expands direct A-side execution paths, and legacy orchestration/planner/aggregator layers are marked as frozen compatibility only. Targeted platform migration tests and orchestration compatibility tests pass.
- 2026-06-16: Migration P0 fix batch completed. `content.workflow.run` now executes through `ContentDomainClient` and reaches `SUCCEEDED`/`FAILED` correctly in scheduler worker execution, `content.publish.approved` is contract-limited to `target_type="blog"`, and real dispatcher execution tests now cover workflow success/failure plus publish success/invalid-target cases.
- 2026-06-16: `pytest` targeted migration validation still emits `PytestConfigWarning: Unknown config option: asyncio_mode` because `apps/platform/pyproject.toml` declares `asyncio_mode`, but the current environment still lacks `pytest-asyncio`.
- 2026-06-17: End-to-end bridge patch completed for local startup and manual fetch flow. `start_content_hub.ps1` now injects `PYTHONPATH` and a local dev `SECRET_KEY`, Console manual fetch submits `content.fetch.batch`, scheduler dispatcher executes local fetch without legacy agent routing, and workflow registry now includes RSS/GitHub Trending/Reddit. Targeted registry/internal-task/dispatcher pytest groups pass.
- 2026-06-17: Review-queue bridge for the manual content loop is now closed. `run_radar_pipeline()` persists `ReviewQueue` rows for fetch-run-scoped processed items, review API/service imports no longer depend on legacy top-level module aliases, and combined radar/review/console/internal-task pytest groups pass. Workspace still emits `PytestCacheWarning` for `.pytest_cache`.

*?????2026-06-12*
