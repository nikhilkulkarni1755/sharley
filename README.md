# Sharley

Independent verifier for AI-written code. Sharley turns any spec into a test bank, shows the
implementing agent only the example tests, and judges the submission against sealed hidden tests,
LeetCode style.

## Quick start

```
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env     # keys are optional; SHARLEY_OFFLINE=1 runs everything locally
pytest
```
