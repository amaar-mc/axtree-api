# Contributing

Thanks for taking a look at AXTree API. The project is intentionally small: a Swift daemon, a Python bridge, and macOS integration scripts that prove the loop works against real apps.

## Development Setup

Install the Python package locally:

```bash
python3 -m pip install -e .
```

Build the Swift daemon:

```bash
swift build --arch arm64
```

The current scripts assume Apple Silicon and real macOS GUI access.

## Before You Open a PR

Run the checks that match your change.

For Python-only changes:

```bash
python3 -m compileall axtree_api examples scripts
```

For Swift daemon changes:

```bash
swift build --arch arm64
```

For behavior changes, run the relevant integration script:

```bash
scripts/test_calculator_state.py
scripts/test_calculator_click.py
scripts/test_python_calculator.py
scripts/test_keyboard_command.py
scripts/test_calculator_complex_expression.py
scripts/test_vision_fallback.py
scripts/evaluate_notes_e2e.py
```

Run GUI integration scripts sequentially. They manipulate foreground macOS apps and can interfere with each other if run in parallel.

## Code Style

- Keep Python standard-library-only unless there is a strong reason to add a dependency.
- Keep Swift on standard Apple frameworks for the daemon.
- Prefer small, explicit APIs over broad abstractions.
- Keep examples short and copy-pasteable.
- Do not commit `.build/`, `artifacts/`, `__pycache__/`, `.egg-info/`, screenshots, or local logs.

## Safety Expectations

Changes that expand action capability should include matching documentation and tests. Desktop automation can click real buttons in real apps, so examples should avoid destructive actions and authenticated workflows.

If a workflow needs to touch private data, payments, account settings, messaging, email sending, or file deletion, design it with a human approval step.

## Commit Shape

Small commits are preferred. Good examples:

```text
feat: add scroll command
test: verify notes text entry
docs: document keypress protocol
```
