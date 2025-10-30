# CVOptima Backend – AI-Powered CV Intelligence Engine

## Table of Contents
1. Introduction – Product Context & Problem Statement  
2. System Overview (High-Level Architecture)  
3. Tech Stack & Why These Choices Matter  
4. AI Workflow & Prompt Orchestration  
5. Authentication & Data Ownership (RLS)  
6. CV Parsing & OCR Pipeline  
7. API Surface & Key Endpoints  
8. Deployment & Infrastructure Model  
9. Future Growth Path / Roadmap  
10. Local Development & Setup Guide

---

## 1. Introduction – Product Context & Problem Statement

CVOptima exists to make CV evaluation structured, explainable and fair. Traditional hiring relies on human screening, which is subjective, inconsistent, and often misses skill-to-role alignment. This backend serves as the **AI intelligence core**, comparing a candidate’s CV with a specific job posting using a schema-driven approach instead of unconstrained text generation.

The key principle:  
**AI is not a “chat”, but a deterministic evaluator.**  
Output is always a strict JSON response validated at runtime — enabling repeatability, objectivity and downstream automation.

---

## 2. System Overview (High-Level Architecture)

Client (Next.js) → FastAPI Backend → Supabase (Auth + DB + Storage)
↳ Gemini 2.5 Flash (AI core)
↳ OCR / Parsing Layer

The backend responsibilities:
- receiving files  
- extracting structured text  
- orchestrating AI analysis  
- persisting results per authenticated user  
- protecting data via RLS

---

## 3. Tech Stack & Why These Choices Matter

| Layer | Technology | Reason |
|------|------------|--------|
| Language | Python | Clean ecosystem for OCR/AI |
| API Framework | FastAPI | Async, typed, developer-friendly |
| Auth + DB | Supabase (PostgreSQL) | Built-in Row Level Security |
| Storage | Supabase Storage | User ownership is preserved |
| AI Model | Google Gemini 2.5 Flash | Fast + schema-controlled output |
| OCR | Tesseract / pdfplumber / pdf2image | Hybrid pipeline |
| Server | Gunicorn + Uvicorn | Stable production runtime |
| Reverse Proxy | nginx | SSL + public routing |

Supabase was chosen intentionally because the platform is identity-centric: the database schema directly respects user boundaries via RLS, not just middleware.

---

## 4. AI Workflow & Prompt Orchestration

1. User uploads CV → parsed + stored  
2. Frontend calls `/analysis/start` with `(cv_id + job_description)`  
3. Service fetches clean CV text  
4. Gemini receives a strict system prompt: *JSON-only, schema-locked*  
5. Response validated via `FullAnalysisResponse`  
6. Stored in `analysis_jobs` as `pending → completed`  
7. The frontend retrieves structured insight, not free text

---

## 5. Authentication & Data Ownership (RLS)

- Identity: Supabase Auth JWT  
- Every `user_cvs` and `analysis_jobs` row is tied to `user_id`  
- RLS guarantees data isolation **at database level**  
- Deletion cascades ensure no orphan data

---

## 6. CV Parsing & OCR Pipeline

| Format | Method |
|--------|--------|
| .pdf (digital) | pdfplumber |
| .docx | python-docx |
| scanned PDF / image | pdf2image → Tesseract OCR |

If a valid text payload cannot be extracted, the AI pipeline is blocked — ensuring reliability and preventing hallucinated summaries.

---

## 7. API Surface & Key Endpoints

POST   /api/v1/cv/upload         → upload & extract CV
GET    /api/v1/cv                → list user CVs
DELETE /api/v1/cv/:id            → delete CV
POST   /api/v1/analysis/start    → start AI analysis
GET    /api/v1/analysis          → list previous analyses
GET    /api/v1/analysis/status   → check analysis result

---

## 8. Deployment & Infrastructure Model

| Component | Technology |
|----------|------------|
| OS | Ubuntu VPS |
| Proxy | nginx |
| TLS | certbot (Let's Encrypt) |
| Runtime | Gunicorn (systemd-managed) |
| OCR | Installed system-wide |
| Supabase | Remote DB/Auth/Storage |

This architecture is intentionally lean: fast to deploy, safe to operate, easy to scale.

---

## 9. Future Growth Path / Roadmap

| Phase | Direction |
|------|-----------|
| Short-term | Redis-based rate limiting, async queue |
| Mid-term | Skill benchmarking & scoring |
| Long-term | Multi-model LLM orchestration |

---

## 10. Local Development & Setup Guide

### Prerequisites
- Python 3.10+
- Supabase project
- Google Gemini API key
- Tesseract OCR installed

### 1. Clone repository
```bash'''
git clone https://github.com/AriceNn/cvoptima-ai-backend.git
cd cvoptima-ai-backend

2. Virtual environment

python3 -m venv .venv
source .venv/bin/activate

3. Install dependencies

pip install --upgrade pip
pip install -r requirements.txt

4. Environment variables

Create .env:

SUPABASE_URL=...
SUPABASE_ANON_KEY=...
SUPABASE_SERVICE_ROLE_KEY=...
GOOGLE_API_KEY=...

5. Install OCR packages (macOS / Ubuntu)

macOS

brew install tesseract poppler

Ubuntu

sudo apt update
sudo apt install -y tesseract-ocr libtesseract-dev poppler-utils

6. Run backend

uvicorn app.main:app --reload

7. Production-style (optional)

gunicorn app.main:app --workers 1 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
