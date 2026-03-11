# Codebase Analyzer v2.0

Multi-agent, multi-provider AI tool that examines your codebase, finds weaknesses, architectural issues, flawed assumptions, and produces a structured report.

Works across most tech stacks — Next.js, PHP/Laravel, Python, .NET, Go, Rust, Java, Ruby on Rails, and more.

## What does it do?

The tool runs a pipeline of specialized AI agents that analyze the code in phases — each phase uses the optimal model for the task:

```
┌──────────┐ Fast/cheap     ┌────────────┐ Mid-tier     ┌────────────────┐
│  SCAN    │───────────────▶│  ANALYZE   │─────────────▶│  SPECIALISTS   │
│ Scout    │ Groq/Gemini    │ Architect  │ Claude/GPT   │ Resilience     │
│ Agent    │ Flash          │ Agent      │ Sonnet       │ Performance    │
└──────────┘                └────────────┘              │ Security       │
   Detect stack               Deep code                 └───────┬────────┘
   <0.01$                     analysis                          │
                              ~0.05$                    ~0.05$ each
                                                                │
                                           ┌────────────────────▼──────┐
                                           │      REPORT              │
                                           │  Summarizer Agent        │
                                           │  Pass 1: Fast (structure)│
                                           │  Pass 2: Mid (enrich)   │
                                           └──────────────────────────┘
                                              Total: ~$0.10-0.30
```

## Model Profiles

| Profile | Scan | Analysis | Specialist | Deep | Cost |
|---------|------|----------|------------|------|------|
| **default** | Groq Llama 3.3 70B | Claude Sonnet 4 | Claude Sonnet 4 | Claude Opus 4 | ~$0.15-0.40 |
| **budget** | Groq Llama 3.3 70B | Groq Llama 3.3 70B | Groq Llama 3.3 70B | Claude Sonnet 4 | ~$0.03-0.10 |
| **local** | Llama 3.2 3B | Qwen 2.5 Coder 14B | Qwen 2.5 Coder 14B | Qwen 2.5 Coder 32B | $0.00 |

You can also mix freely with `--phase-model`.

## Installation

### Docker (recommended)

No Python installation needed:

```bash
docker pull ghcr.io/thetechguyab/code-analyzer:latest

# Analyze a local project (reports saved to ./reports)
docker run --rm \
  -v ./my-project:/code \
  -v ./reports:/app/reports \
  -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
  -e GROQ_API_KEY=$GROQ_API_KEY \
  ghcr.io/thetechguyab/code-analyzer /code
```

### From source

```bash
git clone https://github.com/TheTechGuyAB/code-analyzer.git
cd code-analyzer
pip install -r requirements.txt
```

### API Keys (set whichever ones you want to use)

```bash
export ANTHROPIC_API_KEY=sk-ant-...    # Claude
export OPENAI_API_KEY=sk-...           # GPT-4o / o3
export GROQ_API_KEY=gsk_...            # Groq (free tier)
export GOOGLE_API_KEY=AI...            # Gemini
export GITHUB_TOKEN=ghp_...            # GitHub (private repos)

# Local: Ollama must be running (http://localhost:11434)
```

The tool has **automatic fallback** — if a provider is unavailable, it selects the next best alternative.

## Usage

### Local codebase

```bash
# Basic — HTML report
python analyze.py ./my-project

# With a specific question
python analyze.py ./my-project -q "why is it so slow?"

# Budget profile
python analyze.py ./my-project --profile budget

# All models local via Ollama
python analyze.py ./my-project --profile local

# JSON output
python analyze.py ./my-project -o report.json -f json
```

### GitHub repo

```bash
# Public repo
python analyze.py --github facebook/react --branch main

# Private repo (requires GITHUB_TOKEN)
python analyze.py --github my-company/backend --branch develop

# With guidelines to check against
python analyze.py --github my-company/api -q "are we following our API rules?" \
    --guidelines ./external-api-guideline.md
```

### Per-phase model override

```bash
# Use Gemini for the analysis phase, rest default
python analyze.py ./project --phase-model analyze=analyst-mid-google

# Use GPT-4o Mini for scanning, Claude Opus for deep analysis
python analyze.py ./project \
    --phase-model scan=scout-fast-openai \
    --phase-model deep=deep-heavy
```

### With team guidelines

Provide a guidelines file (markdown, text, anything) and the tool checks whether the code follows your rules:

```bash
python analyze.py ./project --guidelines ./our-api-guideline.md
```

## Available Models

| Key | Provider | Model | Usage |
|-----|----------|-------|-------|
| `scout-fast` | Groq | Llama 3.3 70B | Scanning, classification |
| `scout-fast-google` | Google | Gemini 2.0 Flash | Scanning, classification |
| `scout-fast-openai` | OpenAI | GPT-4o Mini | Scanning, classification |
| `analyst-mid` | Anthropic | Claude Sonnet 4 | Analysis, specialists |
| `analyst-mid-openai` | OpenAI | GPT-4o | Analysis, specialists |
| `analyst-mid-google` | Google | Gemini 2.5 Pro | Analysis, specialists |
| `deep-heavy` | Anthropic | Claude Opus 4 | Deep reasoning |
| `deep-heavy-openai` | OpenAI | o3 | Deep reasoning |
| `local-fast` | Ollama | Llama 3.2 3B | Local scanning |
| `local-mid` | Ollama | Qwen 2.5 Coder 14B | Local analysis |
| `local-heavy` | Ollama | Qwen 2.5 Coder 32B | Local deep analysis |

## What it looks for

### Architecture & flawed assumptions
- Tight coupling, God classes, SOLID violations
- Business logic in controllers, missing abstraction layers
- Race conditions, null reference risks
- Incorrect assumptions in the code

### Resilience (external API handling)
- Direct calls without retry, timeout, circuit breaker
- Missing fallback when services are down
- Missing caching of external responses
- `new HttpClient()` instead of `IHttpClientFactory`
- Default timeout (100s) on HttpClient

### Performance
- N+1 queries, missing index hints
- `.Result` / `.Wait()` in async context
- Missing caching, pagination
- Client-side LINQ evaluation

### Security
- Hardcoded secrets and API keys
- SQL injection, missing input validation
- Missing auth attributes, CORS issues

## Report Schema

All findings follow `schemas/report_schema.json`:

```json
{
  "id": "RES-001",
  "severity": "critical",
  "category": "resilience",
  "title": "External API call without timeout or retry",
  "description": "PaymentService.cs calls Stripe API...",
  "affected_files": ["Services/PaymentService.cs"],
  "evidence": "var response = await _http.GetAsync(url);",
  "recommendation": "Add Polly retry + circuit breaker via IHttpClientFactory",
  "effort": "medium",
  "agent": "specialist-resilience",
  "tags": ["external-api", "no-retry"]
}
```

## File Structure

```
codebase-analyzer/
├── analyze.py                # CLI entry point
├── providers/
│   └── llm_router.py         # Multi-provider LLM abstraction
├── agents/
│   ├── file_collector.py     # Scans & collects files
│   ├── base_agent.py         # Shared agent base class
│   ├── scout_agent.py        # Stack detection (fast)
│   ├── architect_agent.py    # Architecture review (mid)
│   ├── specialist_agent.py   # Resilience/Perf/Security (mid)
│   ├── summarizer_agent.py   # Dual-pass report (fast+mid)
│   └── orchestrator.py       # Pipeline coordinator
├── reporters/
│   ├── html_reporter.py      # Interactive HTML report
│   └── json_reporter.py      # Structured JSON output
├── schemas/
│   └── report_schema.json    # Finding schema
└── utils/
    └── github.py             # GitHub clone integration
```

## Extending

### Custom agent

```python
from agents.base_agent import BaseAgent

class MyAgent(BaseAgent):
    AGENT_NAME = "my-agent"

    def analyze(self, files, stack, user_query=None):
        result = self._chat_json("specialist",
            "You are a ...",
            f"Analyze:\n{self._format_files(files)}")
        return result  # list of findings
```

### Custom provider

Implement `BaseProvider` in `providers/llm_router.py` and register it in `PROVIDERS`.

### Custom model profile

Add to `PROFILES` in `providers/llm_router.py`.

## Author

**Marcus Johansson**
- Website: [thetechguy.se](https://thetechguy.se)
- Email: marcus@thetechguy.se
