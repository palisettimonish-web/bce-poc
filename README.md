# Behavior Coverage Engine — POC

A small, controlled laboratory for measuring whether a test-generation method finds policy failures in an LLM refund agent better than a pairwise baseline.

## What is included

- `world.py` — isolated SQLite state, controlled tool responses, fault injection, and a complete evidence log.
- `agent.py` — a Microsoft Foundry Responses API function-calling loop. The model can only affect the local fake world.
- `oracle.py` — deterministic policy checks; it never asks another model whether behavior is correct.
- `scenarios.py` — pairwise baseline across validity, payment state, amount, approval, faults, and duplicate requests.
- `run.py` — repeatable experiment runner that appends one auditable JSON record per execution.

## Run it

```bash
cd outputs/bce-poc
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# Authenticate locally through Microsoft Entra ID.
az login
export FOUNDRY_PROJECT_ENDPOINT="https://bce-poc-1-resource.services.ai.azure.com/api/projects/bce-poc-1"
export FOUNDRY_MODEL="gpt-4.1-mini"
pytest -q
python run.py --repeats 3 --out results.jsonl
```

The test run calls your Foundry project through Microsoft Entra ID. `DefaultAzureCredential` uses the identity from `az login` during local development; that identity needs permission to invoke the project deployment.

## First experiment

Run the clean prompt first and inspect each violation. Then seed one defect at a time:

```python
from agent import SYSTEM

no_duplicate_rule = SYSTEM.replace("4. Never refund a payment twice.\n", "")
boundary_defect = SYSTEM.replace("above 50000", "50000 or above")
```

Pass one of these to `run_all(system=..., label=...)` from `run.py`, write to a separate JSONL file, and compare the first scenario that finds each named violation. Keep the oracle unchanged across every method.

The implementation uses the project endpoint's Responses API, returns each tool result with its original `call_id`, and preserves the response chain with `previous_response_id`.

Microsoft Foundry documents the [Responses API](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/responses) and [programmatic tool-calling flow](https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/programmatic-tool-calling) used here.
