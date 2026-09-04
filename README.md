TRACK_ID=PS6

# Banking Transaction Risk Investigation Assistant

> Smart India Hackathon 2024 — Problem Statement PS6  
> Team: Pavansa AI · Track: Banking & Finance

A full-stack AI-powered system for **banking transaction risk investigation**. It analyses a customer's transaction history to surface risk signals using deterministic statistical rules, Gemini AI reasoning, and a local Retrieval-Augmented Generation (RAG) knowledge base — without ever making a fraud determination.

---

## Quick Start

```bash
# 1. Clone and enter the project
git clone https://github.com/Pavansa-ai/NexusTiQ-_24_-CareerTiQ.git
cd NexusTiQ-_24_-CareerTiQ

# 2. Install dependencies (Python 3.11+)
pip install -r requirements.txt

# 3. (Optional) Set Gemini API key for AI explanations
set GEMINI_API_KEY=your_key_here        # Windows
# export GEMINI_API_KEY=your_key_here   # Linux/Mac

# 4. Run the application
python app.py
```

Open **http://localhost:8000** in your browser.

> ⚠️ The system works fully without a Gemini API key — deterministic analysis always runs. AI explanations require a valid GEMINI_API_KEY.

---

## Evaluation Criteria Coverage

| Criterion | Implementation |
|-----------|---------------|
| Problem Understanding | 4 targeted risk rules (R1–R4) addressing the PS6 banking fraud investigation brief |
| Solution Design | Layered architecture: deterministic engine → RAG → Gemini → validation |
| Technical Implementation | FastAPI backend, React frontend, numpy-based local vector search |
| Innovation | Customer-specific statistical baselines (IQR/MAD), known-payee exclusion, R3 bucket deduplication |
| Scalability | SQLite AI response cache (SHA-256 key), stateless endpoints |
| Presentation | Full dashboard: verdict card, rule cards, transaction table, behaviour radar, first steps |
| AI/ML Usage | Gemini 2.0 Flash (LLM), gemini-embedding-001 (RAG), graceful fallback |

---

## Architecture

```
POST /api/analyze
  └─ validate_and_parse()          CSV parsing, alias mapping, dedup
  └─ compute_baseline()            Statistical baseline (30-day split)
  └─ build_evidence()
      ├─ check_large_amount()      R1: IQR anomaly vs. unknown payees
      ├─ check_new_payee_burst()   R2: Sliding-window burst detection
      ├─ check_odd_hours()         R3: Customer-specific hour window
      ├─ check_behavioural_deviation()  R4: 5-dimension weighted score
      ├─ build_clusters()          Groups related flagged transactions
      ├─ compute_priority_score()  Deduplicates by rule_id, caps at 100
      └─ determine_investigation_status()
  └─ SQLite cache lookup (SHA-256 hash)
  └─ retrieve_relevant_chunks()    Local RAG (numpy cosine similarity)
  └─ build_investigation_prompt()  Token-efficient context assembly
  └─ GeminiClient.generate()       gemini-2.0-flash with JSON mode
  └─ validate_gemini_output()      Fraud-phrase check, ID hallucination
  └─ build_deterministic_report()  Fallback if AI unavailable
```

---

## Risk Rules

### R1 — Unusually Large Transfer
- **Large**: amount > Q3 + 1.5×IQR **and** ≥ 3× median (+25 pts)
- **Extreme**: amount > Q3 + 3×IQR **and** ≥ 5× median (+35 pts)
- Skips known historical payees (salary, rent) to eliminate false positives

### R2 — New Payee Burst
- Detects rapid repeated payments to a first-time payee
- Sliding window: ≥3 transactions in 48h above threshold (+20 to +40 pts)

### R3 — Odd-Hours Activity
- Computes customer's personal active-hour window (5th–95th percentile ±2h)
- Flags transactions outside this window (+15 pts); deduplicates via 3h buckets

### R4 — Behavioural Pattern Deviation
- 5 dimensions: amount (40%), timing (20%), payee (20%), channel (10%), frequency (10%)
- Score 50–69 → +20 pts; 70–100 → +30 pts

### Investigation Status
- **ATTENTION REQUIRED**: score ≥ 30 AND ≥2 distinct meaningful rules, OR score ≥ 60
- **NO ATTENTION REQUIRED**: otherwise

---

## Sample Cases

| Case | File | Expected Result |
|------|------|-----------------|
| Normal | `data/normal_case.csv` | NO ATTENTION REQUIRED (score 0) |
| Investigation | `data/investigation_case.csv` | ATTENTION REQUIRED (score 80, CRITICAL) |

The investigation case simulates a realistic attack pattern: 4 rapid IMPS transfers to a new payee (TechnoTrade Solutions) totalling ₹1,64,500 — the first at 02:14 AM — triggering R1 (extreme amounts) + R2 (new payee burst) + R3 (odd hours).

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Health check + AI availability |
| GET | `/api/rules` | List of all investigation rules |
| GET | `/api/sample/{case}` | Load sample CSV (`normal` or `investigation`) |
| POST | `/api/analyze` | Analyse transaction history |
| GET | `/docs` | Interactive Swagger UI |

---

## Local RAG Knowledge Base

Six policy documents in `data/documents/` are chunked (400 chars, 80 overlap), embedded with `gemini-embedding-001`, and stored in a local pickle index at `data/index/embeddings.pkl`. Retrieval uses numpy cosine similarity (no FAISS dependency). When AI is unavailable, keyword fallback is used.

Documents:
- `investigation_rules.md` — R1–R4 rule definitions
- `amount_deviation_policy.md` — Large amount investigation protocol
- `new_payee_policy.md` — New payee burst investigation protocol
- `timing_deviation_policy.md` — Odd-hours activity protocol
- `behavioural_deviation_policy.md` — Pattern deviation assessment
- `investigator_guidance.md` — Human-in-the-loop framework

---

## AI Safety Constraints

The Gemini output validator (`src/ai/output_validator.py`) enforces:
- **No fraud claims** — 10 prohibited phrases (e.g., "fraud has occurred")
- **No hallucinated transaction IDs** — validates every TX\d+ reference
- **Amount cross-check** — reported amounts must match evidence
- **Step cap** — maximum 6 investigator first steps
- **JSON schema enforcement** — rejects malformed or incomplete responses

If validation fails, the deterministic report is used as fallback.

---

## Project Structure

```
NexusTiQ-_24_-CareerTiQ/
├── app.py                    # Single entry point (python app.py)
├── requirements.txt          # pip install -r requirements.txt
├── data/
│   ├── normal_case.csv       # 95-transaction normal case
│   ├── investigation_case.csv # 112-transaction investigation case
│   ├── documents/            # 6 RAG policy documents (Markdown)
│   ├── index/                # Persistent embedding index (pickle)
│   └── cache.db              # SQLite AI response cache
├── src/
│   ├── models/transaction.py # Pydantic data models
│   ├── core/                 # Deterministic engine
│   │   ├── validation.py     # CSV parsing & normalisation
│   │   ├── baseline.py       # Customer statistical baseline
│   │   ├── risk_engine.py    # R1–R4 rule implementations
│   │   ├── clustering.py     # Transaction cluster grouping
│   │   ├── scoring.py        # Priority scoring & status
│   │   ├── evidence.py       # Evidence builder orchestrator
│   │   └── report.py         # Deterministic fallback report
│   ├── ai/                   # AI integration layer
│   │   ├── gemini_client.py  # google-genai SDK wrapper
│   │   ├── embeddings.py     # Doc chunking + vector index
│   │   ├── retrieval.py      # Cosine similarity RAG
│   │   ├── prompt_builder.py # Token-efficient prompts
│   │   └── output_validator.py # Gemini output safety checks
│   ├── services/
│   │   └── investigation.py  # Full pipeline orchestrator
│   └── api/
│       └── routes.py         # FastAPI routes
├── frontend/
│   └── dist/index.html       # React 18 SPA (CDN, no build step)
└── tests/                    # 47 pytest unit tests
    ├── test_validation.py
    ├── test_baseline.py
    ├── test_risk_engine.py
    └── test_scoring_and_validator.py
```

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GEMINI_API_KEY` | Optional | Enables AI explanations and vector embeddings |

Never commit your API key. Use `.env` (gitignored) or set it in your shell.

---

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Backend API | FastAPI 0.141 + Uvicorn |
| Data models | Pydantic v2 |
| Data processing | pandas 3.0, numpy 2.4 |
| AI/LLM | google-genai (gemini-2.0-flash) |
| Embeddings | gemini-embedding-001 |
| Vector search | numpy cosine similarity (no FAISS) |
| Cache | SQLite (stdlib) |
| Frontend | React 18 + Tailwind CSS (CDN) |
| Tests | pytest (47 tests) |