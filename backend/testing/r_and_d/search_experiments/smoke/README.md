# Smoke tests

One **verbose, end-to-end** script per phase. Unlike the pytest suite in `tests/` (which
asserts pure logic offline), smoke tests *run the real thing* — live LLM/API calls — and
**print what each function produces** so you can eyeball the pipeline.

Convention: each phase adds `smoke/phaseN_<name>.py`. Every script starts with
`import _bootstrap` (adds the project root to `sys.path` + loads `backend/.env`), then walks
the new functionality stage by stage with labelled output.

Run from the project dir (`search_experiments/`):

```bash
uv run smoke/phase1_metrics.py    # offline — metric worked examples
uv run smoke/phase2_judge.py      # live — OpenAlex retrieve -> judge -> 0-3 levels
uv run smoke/phase3a_core.py      # live — query analysis (content+intent) + Cohere rerank + blend + sweep
uv run smoke/phase3b_loop.py      # offline — BTS allocation spotlight + full broad_search loop (FakeSource)
uv run smoke/phase4_openalex.py   # live — Arm B SourceClient: formulate -> search -> coverage -> suggest/ground -> snowball
```

| Script | Phase | Needs |
|---|---|---|
| `phase1_metrics.py` | 1 | nothing (pure) |
| `phase2_judge.py` | 2 | OpenAI + OpenAlex |
| `phase3a_core.py` | 3a | OpenAI + Cohere |
| `phase3b_loop.py` | 3b | nothing (offline FakeSource + fake judge) |
| `phase4_openalex.py` | 4 | OpenAI + OpenAlex |

> Smoke tests reuse the on-disk caches (`results/`), so reruns are cheap. `rm -rf results/`
> for a clean slate. They are demonstrations, not assertions — correctness lives in `tests/`.
