# GRID evals

`run_evals.py` is the deterministic v3 gate. It checks that 49 natural-language
phrases route to the intended tool before the model sees them. The optional
Sherlock, Nuclei and PlatformIO wrappers are included.

```powershell
python evals/run_evals.py
```

It runs in CI without Ollama or network access. The next layer is a real-model
acceptance run for tool selection, permission decisions, skill loading and
autopilot follow-ups; that will run locally, not in CI.
