# Multi-Agent Code Review & Auto-Debugging System

## Project Overview

An AI-powered multi-agent system that automatically reviews code from multiple angles (bugs, security, style, performance), suggests fixes, and generates test cases. Built as a coursework project for an AI training class.

**Final Deliverable:** A single Google Colab notebook (.ipynb) reproducible with "Runtime > Run All".

**Development Strategy:** Build locally first, validate each component, then consolidate into Colab notebook.

---

## Architecture

### Phase 1: Single Agent (Current — Local)
```
Input (.py file) → Code Review Agent (GPT-4o) → Report + Fixed Code
```

### Phase 2: Multi-Agent Pipeline (Target)
```
Input (.py file)
    │
    ▼
┌─────────────────┐
│ Orchestrator    │  ← tree-sitter AST parsing, chunk routing
└────────┬────────┘
         │
    ┌────┼────────────────┐
    ▼    ▼                ▼
┌──────┐ ┌──────────┐ ┌──────────────┐
│Secur.│ │Bug Detect│ │Style & Perf. │
│Agent │ │Agent     │ │Agent         │
└──┬───┘ └────┬─────┘ └──────┬───────┘
   │          │               │
   └──────────┼───────────────┘
              ▼
      ┌──────────────┐
      │Patch Gen Agent│  ← Structured diffs via Pydantic
      └──────┬───────┘
             ▼
      ┌──────────────┐
      │Test Gen Agent │  ← pytest suites
      └──────┬───────┘
             ▼
      Report + Fixed Code + Tests (.zip)
```

### RAG Layer
- ChromaDB vector store
- Embedded CWE descriptions + OWASP Top-10 guidelines
- Embedding model: sentence-transformers/all-MiniLM-L6-v2
- Agents query RAG to ground analysis and cite references

### LangGraph State Machine
- StateGraph with nodes per agent
- Conditional edges for routing (e.g., critical security → human review interrupt)
- Retry logic with exponential backoff for LLM failures

---

## Tech Stack

| Component | Tool | Notes |
|-----------|------|-------|
| Orchestration | LangGraph | State machine, conditional routing |
| LLM (local dev) | OpenAI GPT-4o | Via API |
| LLM (Colab) | CodeLlama-7B-Instruct | 4-bit quantized via BitsAndBytes |
| Security classification | CodeBERT | Fine-tuned on vulnerability data |
| Vector DB | ChromaDB | CWE/OWASP knowledge base |
| Embeddings | all-MiniLM-L6-v2 | sentence-transformers |
| Code parsing | tree-sitter | AST chunking |
| Static analysis | pylint, radon | Style + complexity metrics |
| Output schema | Pydantic | Structured patch format |
| Testing | pytest | Generated test suites |
| Interface | Gradio | Upload, report, download |
| Runtime | Google Colab (T4 GPU) | Final deployment target |

---

## Development Phases

### Phase 1: Single Agent Foundation ✅
- [x] Basic code review agent with GPT-4o
- [x] File input → LLM analysis → report + fixed code output
- [ ] Add LangChain wrapper around the LLM call
- [ ] Add structured output with Pydantic models
- [ ] Port to Colab notebook

### Phase 2: Multi-Agent with LangGraph
- [ ] Define Pydantic state schema (shared across agents)
- [ ] Build Orchestrator Agent with tree-sitter parsing
- [ ] Build Security Agent (CodeBERT classifier)
- [ ] Build Bug Detection Agent (CodeLlama + chain-of-thought)
- [ ] Build Style & Performance Agent (pylint + radon)
- [ ] Wire agents into LangGraph StateGraph
- [ ] Add conditional routing and error handling

### Phase 3: Patch & Test Generation
- [ ] Patch Generation Agent (structured diffs)
- [ ] Test Generation Agent (pytest suites)
- [ ] End-to-end pipeline validation

### Phase 4: RAG Knowledge Base
- [ ] Download and parse CWE/OWASP data
- [ ] Embed into ChromaDB
- [ ] Integrate retrieval into Security + Bug agents
- [ ] Add CWE references to output reports

### Phase 5: Interface & Packaging
- [ ] Gradio UI (code upload, report display, ZIP download)
- [ ] Consolidate everything into single Colab notebook
- [ ] Test with "Runtime > Run All"
- [ ] Add demo section with synthetic buggy examples

---

## Project Structure

```
AI_Training/
├── CLAUDE.md                  # This file — project guide
├── .env                       # OpenAI API key (git-ignored)
├── .env.example               # Template for API key
├── requirements.txt           # Python dependencies
├── code_review_agent.py       # Phase 1: Single agent script
├── sample_bad_code.py         # Test input (deliberately buggy)
├── sample_bad_code_fixed.py   # Generated output (fixed version)
├── agents/                    # Phase 2: Individual agent modules
│   ├── orchestrator.py
│   ├── security_agent.py
│   ├── bug_agent.py
│   ├── style_agent.py
│   ├── patch_agent.py
│   └── test_agent.py
├── models/                    # Pydantic schemas
│   └── schemas.py
├── rag/                       # RAG knowledge base
│   ├── build_kb.py
│   └── data/
├── graph/                     # LangGraph pipeline
│   └── pipeline.py
├── tests/                     # Test samples and validation
│   └── test_samples/
└── notebook/                  # Final Colab notebook
    └── multi_agent_code_review.ipynb
```

---

## Running the Project

### Local Development
```bash
# Install dependencies
pip install -r requirements.txt

# Set up API key
cp .env.example .env
# Edit .env with your OpenAI API key

# Run single agent
python code_review_agent.py sample_bad_code.py
```

### Google Colab (Final)
- Upload notebook to Colab
- Set runtime to GPU (T4)
- Runtime > Run All

---

## Conventions

- **Python version:** 3.10+
- **Code style:** PEP 8, type hints on function signatures
- **Models:** Use Pydantic v2 for all data schemas
- **LLM calls:** Always set temperature low (0.1–0.3) for deterministic code analysis
- **Error handling:** Retry with exponential backoff for LLM API calls
- **File naming:** snake_case for modules, PascalCase for classes
- **Prompts:** Store as module-level constants, use f-strings or .format() for injection
- **Git:** Do not commit .env files or model weights

---

## Key Design Decisions

1. **Local-first development** — Build and test each component locally with GPT-4o before porting to Colab with CodeLlama. Faster iteration, easier debugging.

2. **LangGraph over raw LangChain** — StateGraph gives explicit control over agent routing, supports conditional edges, human-in-the-loop interrupts, and retry logic.

3. **Pydantic for all outputs** — Every agent returns structured data. No free-form string parsing between agents. This makes the pipeline deterministic and testable.

4. **RAG for grounding** — Agents cite CWE/OWASP references rather than hallucinating vulnerability classifications. ChromaDB is lightweight and Colab-friendly.

5. **tree-sitter for parsing** — AST-level chunking means agents review logical units (functions, classes) rather than arbitrary line splits. Language-agnostic.

6. **Gradio for UI** — Lightweight, Colab-native, supports file upload/download. No frontend build step needed.

---

## Datasets

| Dataset | Purpose | Source |
|---------|---------|--------|
| CodeSearchNet | Code corpus for embeddings | HuggingFace |
| Devign | Vulnerability detection training | GitHub/HuggingFace |
| CWE database | Security knowledge base for RAG | MITRE (XML/JSON) |
| OWASP Top-10 | Security guidelines for RAG | OWASP.org |
| Synthetic samples | Stress-test agents | Self-generated with CodeLlama |
