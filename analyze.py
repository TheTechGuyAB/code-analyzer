#!/usr/bin/env python3
"""
Codebase Analyzer v2.0 — Multi-agent, multi-provider codebase analysis.

Supports: Local dirs, GitHub repos (public & private)
Providers: Anthropic, OpenAI, Groq, Google Gemini, Ollama (local)
Profiles: default (mixed), budget (Groq-heavy), local (Ollama)

Usage:
    # Local directory
    python analyze.py ./my-project

    # GitHub repo
    python analyze.py --github owner/repo --branch main

    # With specific concern
    python analyze.py ./project -q "why is it slow?"

    # Budget mode (mostly Groq)
    python analyze.py ./project --profile budget

    # All local (Ollama)
    python analyze.py ./project --profile local

    # With team guidelines file
    python analyze.py ./project --guidelines ./api-guidelines.md

    # Override specific phase model
    python analyze.py ./project --phase-model analyze=analyst-mid-google
"""

import argparse
import json
import sys
import time
from pathlib import Path

from agents.orchestrator import Orchestrator
from providers.llm_router import LLMRouter, MODELS, PROFILES
from reporters.json_reporter import JsonReporter
from reporters.html_reporter import HtmlReporter


def main():
    parser = argparse.ArgumentParser(
        description="Multi-agent codebase analyzer with multi-provider LLM support",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Model profiles:
  default    Groq (scan) → Claude Sonnet (analyze) → Claude Opus (deep)
  budget     Groq for everything, Sonnet only for deep analysis
  local      Ollama models only (free, private)

Available models:
  scout-fast         Llama 3.3 70B (Groq)     — scan, classify
  scout-fast-google  Gemini 2.0 Flash          — scan, classify
  scout-fast-openai  GPT-4o Mini               — scan, classify
  analyst-mid        Claude Sonnet 4            — analyze, specialist
  analyst-mid-openai GPT-4o                     — analyze, specialist
  analyst-mid-google Gemini 2.5 Pro             — analyze, specialist
  deep-heavy         Claude Opus 4              — deep reasoning
  deep-heavy-openai  OpenAI o3                  — deep reasoning
  local-fast         Llama 3.2 3B (Ollama)      — scan
  local-mid          Qwen 2.5 Coder 14B (local) — analyze
  local-heavy        Qwen 2.5 Coder 32B (local) — deep

Examples:
  %(prog)s ./my-project
  %(prog)s --github owner/repo --branch develop
  %(prog)s ./project -q "why is it slow?" --profile budget
  %(prog)s ./project --guidelines ./our-api-rules.md
  %(prog)s ./project --phase-model analyze=analyst-mid-google
  %(prog)s ./project -o report.json -f json
        """,
    )

    # Source
    parser.add_argument("path", nargs="?", type=str, default=None,
                        help="Path to local codebase")
    parser.add_argument("--github", "-g", type=str, default=None,
                        help="GitHub repo (owner/repo or full URL)")
    parser.add_argument("--branch", "-b", type=str, default=None,
                        help="Branch/tag to analyze (with --github)")

    # Analysis
    parser.add_argument("--query", "-q", type=str, default=None,
                        help="Specific concern (e.g. 'why is it slow?')")
    parser.add_argument("--guidelines", type=str, default=None,
                        help="Path to team guidelines/rules file to check against")
    parser.add_argument("--max-files", type=int, default=200,
                        help="Max files to analyze (default: 200)")

    # Models
    parser.add_argument("--profile", "-p", type=str, default="default",
                        choices=list(PROFILES.keys()),
                        help="Model profile (default, budget, local)")
    parser.add_argument("--phase-model", action="append", default=[],
                        help="Override phase model: phase=model (e.g. analyze=analyst-mid-google)")

    # Output
    parser.add_argument("--output", "-o", type=str, default=None,
                        help="Output file path")
    parser.add_argument("--format", "-f", type=str, choices=["json", "html"],
                        default="html", help="Output format (default: html)")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Show detailed progress")

    args = parser.parse_args()

    # ── Validate source ──
    if not args.path and not args.github:
        parser.error("Provide a local path or --github owner/repo")

    # ── Setup model routing ──
    phase_models = dict(PROFILES[args.profile])
    for override in args.phase_model:
        if "=" not in override:
            parser.error(f"Invalid --phase-model format: {override}. Use phase=model")
        phase, model = override.split("=", 1)
        if model not in MODELS:
            parser.error(f"Unknown model: {model}. Available: {', '.join(MODELS.keys())}")
        phase_models[phase] = model

    router = LLMRouter(phase_models=phase_models, verbose=args.verbose)

    # Check provider availability
    avail = router.check_availability()
    unavail = [p for p, ok in avail.items() if not ok]
    if unavail:
        print(f"  ⚠️  Unavailable providers: {', '.join(unavail)}")
        print(f"     Set env vars: " + ", ".join(
            f"{p.upper()}_API_KEY" for p in unavail if p != "ollama"
        ))
        print(f"     Fallbacks will be attempted.\n")

    # ── Load guidelines ──
    guidelines = None
    if args.guidelines:
        gp = Path(args.guidelines)
        if not gp.exists():
            parser.error(f"Guidelines file not found: {gp}")
        guidelines = gp.read_text(encoding="utf-8")
        print(f"  📋 Loaded guidelines: {gp.name} ({len(guidelines)} chars)")

    # ── Resolve source ──
    repo_info = None
    cleanup_fn = None

    if args.github:
        from utils.github import GitHubSource
        gh = GitHubSource(repo=args.github, branch=args.branch)
        root = gh.clone()
        repo_info = gh.get_info()
        cleanup_fn = gh.cleanup
    else:
        root = Path(args.path).resolve()
        if not root.exists():
            print(f"Error: Path '{root}' does not exist.", file=sys.stderr)
            sys.exit(1)

    # ── Print header ──
    phase_display = []
    for phase in ["scan", "analyze", "specialist", "deep", "report", "validate"]:
        model_key = phase_models.get(phase, "?")
        cfg = MODELS.get(model_key)
        if cfg:
            phase_display.append(f"    {phase:12s} → {cfg.display_name}")

    print(f"""
┌──────────────────────────────────────────────────┐
│  Codebase Analyzer v2.0                          │
│  Multi-agent · Multi-provider                    │
└──────────────────────────────────────────────────┘
  Source:    {repo_info['full_name'] + ' @ ' + repo_info.get('branch', '?') if repo_info else root}
  Query:     {args.query or '(general analysis)'}
  Profile:   {args.profile}
  Pipeline:
{chr(10).join(phase_display)}
""")

    start = time.time()

    try:
        orchestrator = Orchestrator(
            root_path=root,
            router=router,
            verbose=args.verbose,
            max_files=args.max_files,
            guidelines=guidelines,
        )

        report = orchestrator.run(user_query=args.query, repo_info=repo_info)
        duration = time.time() - start
        report["meta"]["duration_seconds"] = round(duration, 1)

    finally:
        if cleanup_fn:
            cleanup_fn()

    # ── Output ──
    reports_dir = Path("reports")
    reports_dir.mkdir(exist_ok=True)

    if args.format == "json":
        reporter = JsonReporter()
        output_str = reporter.render(report)
        if args.output:
            out_path = Path(args.output)
        else:
            out_path = reports_dir / f"codebase-report-{int(time.time())}.json"
        out_path.write_text(output_str, encoding="utf-8")
        print(f"\n✅ JSON report → {out_path}")
    else:
        reporter = HtmlReporter()
        output_str = reporter.render(report)
        out_path = Path(args.output) if args.output else reports_dir / f"codebase-report-{int(time.time())}.html"
        out_path.write_text(output_str, encoding="utf-8")
        print(f"\n✅ HTML report → {out_path}")

    # ── Summary ──
    s = report["summary"]
    cost = report.get("meta", {}).get("cost", {})
    total_cost = cost.get("total_cost_usd", 0)

    print(f"""
┌──────────────────────────────────────────────────┐
│  Analysis Complete                               │
├──────────────────────────────────────────────────┤
│  Health Score:  {s.get('health_score', 0):>3}/100                           │
│  Critical:      {s.get('critical_count', 0):>3}                               │
│  Warnings:      {s.get('warning_count', 0):>3}                               │
│  Info:          {s.get('info_count', 0):>3}                               │
│  Duration:      {duration:>5.1f}s                             │
│  Cost:          ${total_cost:>7.4f}                          │
└──────────────────────────────────────────────────┘
""")

    # Print cost breakdown if verbose
    if args.verbose and cost.get("calls"):
        print("  Cost breakdown:")
        for call in cost["calls"]:
            print(f"    {call['phase']:12s} {call['provider']:10s} "
                  f"{call['model']:30s} "
                  f"${call['cost_usd']:.4f}  "
                  f"({call['latency_ms']}ms)")


if __name__ == "__main__":
    main()
