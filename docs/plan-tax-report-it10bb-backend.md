# IT-10BB Tax Report — Backend Implementation Plan

> Spec-driven. This plan extends `backend/SPEC.md` (the `§G/§C/§I/§V/§T/§B` convention already in use — OpenSpec is NOT installed and should NOT be added). Implementation must update `SPEC.md` alongside code.

## Goal

Add a persisted, tracker-scoped **IT-10BB (Bangladesh income-tax expense statement)** report. The user picks a Bangladesh financial year (income year, e.g. `2025-26` = **Jul 1 2025 → Jun 30 2026**), and the backend aggregates that tracker's expenses per category, uses **server-side Gemini** to map each category into one of the **9 fixed IT-10BB heads**, sums the exact amounts per head, and **persists** the result so re-opening the same year reuses it instead of re-calling the LLM.

### Why Bangladesh

This feature targets **IT-10BB, the Bangladesh NBR form** for an individual's annual statement of assets, liabilities, and living expenses. The user runs a **BDT tracker**, and the requirement is: *when the tracker currency is BDT, apply Bangladeshi tax rules*. Those rules define the 9 fixed heads below and the **income-year boundary of July 1 → June 30** (e.g. income year `2025-26`). The trigger is currency-based, but the form structure is fixed regardless of tracker. All copy is **English only** (no Bangla labels).

Key decisions (confirmed with user):
- **AI runs on the backend via Gemini** (mirrors `modules/ai`), NOT the frontend BYO-key path.
- **Persisted** — get-or-create by fiscal year, with manual amount override and a force-regenerate action.
- **English-only labels** — no Bangla strings in the `TAX_HEADS` constant or API responses.

---

## IT-10BB heads (the 9 fixed buckets)

Single source of truth lives in `modules/tax/` as a `TAX_HEADS` constant (code, name, description). The same constant feeds both the LLM prompt and the API response labels.

| code | English name |
|---|---|
| `food_clothing_essentials` | Food, Clothing & Other Essentials |
| `accommodation` | Accommodation Expense |
| `auto_transportation` | Auto & Transportation |
| `household_utility` | Household & Utility |
| `education` | Education Expenses |
| `festival_special` | Festival & Special Expenses |
| `other_expenses` | Any Other Expenses |
| `personal_loan_interest` | Interest on Personal Loan |
| `environmental_surcharge` | Environmental Surcharge |

Heads 8 & 9 default to `0` unless a category clearly maps to them.

---

## New module: `modules/tax/` (full pattern — persisted, so unlike `reports`/`ai` it has `model.py` + `repo.py`)

```
modules/tax/
├── __init__.py
├── model.py      # TaxReport, TaxReportHead (SQLModel tables)
├── schema.py     # request/response Pydantic models + TaxHeadCode enum + TAX_HEADS constant
├── repo.py       # raw CRUD on the two tables (no business logic, no HTTPException)
├── service.py    # get-or-create, aggregation, LLM classification, salvage, override, regenerate
└── router.py     # FastAPI routes
```

### `model.py`

Follow `modules/trackers/model.py` conventions (UUID PK via `uuid4`, `created_at`/`updated_at` with `onupdate`).

- `TaxReport` (`tax_reports`): `id`, `tracker_id` (FK `trackers.id`, `ondelete="CASCADE"`), `fiscal_year` (str, e.g. `"2025-26"`), `start_date` (date), `end_date` (date), `currency` (str), `total_amount` (Decimal, `max_digits=14, decimal_places=2`), timestamps. `__table_args__ = (UniqueConstraint("tracker_id", "fiscal_year", name="uq_tax_reports_tracker_fiscal_year"),)`
- `TaxReportHead` (`tax_report_heads`): `id`, `report_id` (FK `tax_reports.id`, `ondelete="CASCADE"`), `head_code` (str), `amount` (Decimal), `category_allocations` (JSON — `sa_column=Column(JSON)`, list of `{"category_name": str, "amount": str}` with amounts as **decimal strings** to preserve precision), timestamps. `UniqueConstraint("report_id", "head_code", name="uq_tax_report_heads_report_head")`.

### `schema.py`

- `TaxHeadCode(str, Enum)` — the 9 codes above.
- `TAX_HEADS: list[dict]` — `{code, name, description}`; used by prompt + response.
- `TaxReportCreateRequest { fiscal_year: str }` — validator enforces `^\d{4}-\d{2}$` and that the end year = start year + 1 (e.g. `2025-26`).
- `TaxCategoryAllocation { category_name: str, amount: Decimal }`
- `TaxHeadResponse { head_code, head_name, description, amount: Decimal, category_allocations: list[TaxCategoryAllocation] }`
- `TaxReportResponse { id, tracker_id, fiscal_year, start_date, end_date, currency, total_amount, heads: list[TaxHeadResponse], created_at, updated_at }`
- `TaxReportSummaryResponse { id, fiscal_year, start_date, end_date, total_amount, created_at }` (for the list endpoint)
- `TaxHeadUpdate { head_code: TaxHeadCode, amount: Decimal = Field(ge=0) }` and `TaxReportUpdateRequest { heads: list[TaxHeadUpdate] }`

### `repo.py` (raw queries, `select()` only)

- `get_report_by_fiscal_year(session, tracker_id, fiscal_year) -> TaxReport | None`
- `create_report(session, **fields) -> TaxReport` (caller adds heads)
- `list_reports_by_tracker(session, tracker_id) -> list[TaxReport]`
- `list_heads_by_report(session, report_id) -> list[TaxReportHead]`
- `get_head_by_code(session, report_id, head_code) -> TaxReportHead | None`
- `add_heads(session, heads)`, `commit()` handled by service.

### `service.py` (business logic)

1. `_fiscal_year_bounds(fiscal_year) -> (start_date, end_date)` — parse `"YYYY-YY"` → `date(Y, 7, 1)` … `date(Y+1, 6, 30)`.
2. `_aggregate_by_category(session, tracker_id, start, end)` — the aggregation query lives **in service** (per CLAUDE.md rule: aggregations don't go in repo). Join `Expense` + `Category`, group by `Category.name`, sum + count; also fetch up to 5 sample descriptions per category (top by amount) for classification accuracy.
3. `_classify_categories(llm, aggregates, currency) -> dict[category_name, head_code]` — build a prompt listing the 9 heads (code + name + description) and the per-category aggregates (name, total, count, sample descriptions) + currency; instruct the model to map **each category to exactly one head**, use `other_expenses` when unsure, keep `personal_loan_interest`/`environmental_surcharge` at 0 unless obvious. Uses `llm.generate_structured(prompt, response_schema)` with a Gemini ARRAY schema `[{category: STRING, head: STRING enum}]`. **Salvage** untrusted output (mirror `modules/ai/service.py`): drop rows whose category isn't in our aggregate set; coerce unknown head codes to `other_expenses`.
4. `_sum_by_head(aggregates, mapping)` — **exact Decimal sums** per head, building `category_allocations` (`{category_name, amount}`).
5. `get_or_create(session, llm, tracker_id, user_id, fiscal_year)`:
   - `tracker_service.get_tracker_or_404(...)` (ownership).
   - If `repo.get_report_by_fiscal_year` returns a report → return it (no LLM call).
   - Else aggregate; if **no expenses in range**, skip the LLM and build a report with all 9 heads = 0; otherwise classify + sum. Persist `TaxReport` + 9 `TaxReportHead` rows (one per head, zeros included). Return the full report.
6. `regenerate(session, llm, tracker_id, user_id, fiscal_year)` — delete existing heads, re-aggregate, re-classify, persist (reuse steps 2–5).
7. `update_heads(session, tracker_id, user_id, fiscal_year, updates)` — apply manual amount overrides to the given heads (validate each head_code, `amount >= 0`), recompute `total_amount`, persist, return full report.
8. `list_reports(session, tracker_id, user_id)` — summaries.

Error mapping (mirror `modules/ai`): `LLMNotConfiguredError` → 503, `LLMError` → 502, non-list LLM payload → 502. Empty category aggregate → skip LLM (all-zero report), never 422 (unlike parse-expenses, an empty year is a valid result).

### `router.py`

Prefix `/trackers/{tracker_id}/tax-reports`, tags `["Tax"]`. Uses `Annotated[Session, Depends(get_session)]`, `Annotated[User, Depends(get_current_user)]`, `Annotated[LLMClient, Depends(get_llm)]`.

| Method | Path | Body / query | Notes |
|---|---|---|---|
| POST | `/trackers/{tracker_id}/tax-reports` | `{fiscal_year}` | get-or-create; **`@limiter.limit("10/minute")`** (protects Gemini quota) |
| GET | `/trackers/{tracker_id}/tax-reports` | — | list summaries |
| GET | `/trackers/{tracker_id}/tax-reports/{fiscal_year}` | — | fetch existing (404 if none) |
| PATCH | `/trackers/{tracker_id}/tax-reports/{fiscal_year}` | `{heads:[{head_code,amount}]}` | manual override |
| POST | `/trackers/{tracker_id}/tax-reports/{fiscal_year}/regenerate` | — | force re-run (also rate-limited) |

---

## Wiring changes (outside `modules/tax/`)

- **`app/api/v1/api.py`**: `from modules.tax.router import router as tax_router` + `api_router.include_router(tax_router)`.
- **`alembic/env.py`**: add `from modules.tax.model import TaxReport, TaxReportHead  # noqa` (invariant V21 — otherwise autogenerate proposes DROPPING the new tables).
- **`tests/conftest.py`**: add the same model imports so `SQLModel.metadata.create_all` covers them.
- **Migration**: `make migrations` → "add tax reports tables", then `make upgrade`.

---

## SPEC.md updates (backend)

- `§I` — new `api.tax` interface block documenting the 5 endpoints above.
- `§V` — new invariants, e.g.:
  - `V28`: ≤1 TaxReport per `(tracker_id, fiscal_year)` (UNIQUE); get-or-create returns existing without re-calling the LLM.
  - `V29`: IT-10BB heads are a fixed 9-element set; every report persists exactly 9 `TaxReportHead` rows (zeros included).
  - `V30`: LLM classification output is untrusted — unknown categories dropped, unknown head codes coerced to `other_expenses`; **all sums computed server-side from real amounts, never from LLM numbers**.
  - `V31`: manual head override `amount >= 0`; `personal_loan_interest`/`environmental_surcharge` default to 0.
- `§T` — add `T17 |x| tax module: IT-10BB get-or-create + override + regenerate | V28,V29,V30,V31,I.tax`.

---

## Tests (`tests/test_tax.py`)

Mirror `tests/test_ai.py` — stub `get_llm` with a `_StubLLM` (canned payload / error) and assert behavior, never a real Gemini call. Cover:

1. Auth required (401); unknown tracker → 404; other user's tracker → 404.
2. Get-or-create idempotency: two `POST`s for the same fiscal year → same report id, and `stub_llm.prompts` stays length 1.
3. Happy path: stub mapping e.g. `Groceries→food_clothing_essentials`, `Transport→auto_transportation`; assert exact summed amounts land on the right heads, and `category_allocations` carry per-category amounts.
4. Salvage: unknown category dropped; unknown head coerced to `other_expenses`.
5. No expenses in range → all 9 heads returned with `0` amounts, LLM NOT called (`stub_llm.prompts` empty).
6. `fiscal_year` validation: bad format (`"25-26"`, `"2025-27"`) → 422.
7. PATCH override updates a head amount and recomputes `total_amount`; unknown `head_code` → 422; negative amount → 422.
8. Regenerate calls the LLM again and updates the report in place.
9. Provider failures: `LLMError` → 502, `LLMNotConfiguredError` → 503.

Run `make test`, `make lint`, `make format`.

---

## Verification

1. `make migrations` (message: "add tax reports tables") then `make upgrade`.
2. `make test` — new `tests/test_tax.py` green plus existing suite.
3. `make lint` (ruff + mypy).
4. Manual smoke (needs `GEMINI_API_KEY` in `.env` + Postgres via `docker-compose up` + `make run`):
   - `POST /api/v1/trackers/{id}/tax-reports` `{"fiscal_year":"2025-26"}` → 200 with 9 heads and totals; repeat → identical response, no new LLM call (verify via server logs).
   - `PATCH` one head amount → persisted; `POST .../regenerate` → recomputed.
   - `GET /api/v1/trackers/{id}/tax-reports` → lists the saved year.
