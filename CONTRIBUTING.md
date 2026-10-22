# Contributing to Yativo Fiat SDK for Python

Thanks for helping! This guide covers everything you need to make a change and get it merged.

## Requirements

- Python 3.8 or newer
- pytest (only to run the tests)
- Git
- A Yativo **sandbox** API key, only if you want to try changes against the real sandbox. The tests never call Yativo and need no key.

## Get set up

```bash
git clone https://github.com/Yativo/yativo-fiat-python.git
cd yativo-fiat-python
python3 -m venv .venv && . .venv/bin/activate && pip install -e . pytest
```

## Run the checks

```bash
python -m pytest -v tests
python -m compileall -q src examples
```

All checks must pass before a pull request can be merged. CI runs them on every supported version.

## Where things are

- Source: `src/yativo_fiat/`. `resources.py` is generated.
- Tests: `tests/` or `*_test` files next to the code.
- Examples: `examples/`. Keep them runnable: they are linted in CI.

## Generated code

Every endpoint is described once in [`spec/endpoints.json`](spec/endpoints.json). The resource classes and [`docs/REFERENCE.md`](docs/REFERENCE.md) are generated from it:

```bash
python3 tools/generate.py --lang python --root .
```

- To add or change an endpoint, edit `spec/endpoints.json`, run the command above and commit both.
- Don't edit generated files by hand. CI fails if they don't match the spec.
- The same spec drives every Yativo SDK. Please also open the change in [yativo-sdks](https://github.com/Yativo/yativo-sdks), so all languages stay in step.

## Making a change

1. Open an issue first for anything bigger than a small fix, so we can agree on the approach.
2. Create a branch from `main`: `git checkout -b fix/short-description`.
3. Make the change **with tests**. Bug fixes need a test that fails without the fix.
4. Update `README.md` and `CHANGELOG.md` (under "Unreleased") when behaviour changes.
5. Run the checks above.
6. Open a pull request and fill in the template.

### Style

- Follow the existing code style. Keep functions small and names descriptive.
- No new runtime dependencies without discussing it first: the SDK has none on purpose.
- Public methods need a short doc comment that says what they do.
- Error messages are full sentences a developer can act on.

### Commit messages

Write a short summary line in the imperative ("Add retry for 504"), a blank line, then what changed and why.

## Security rules for every change

- Never log, print or include the API key, API secret or webhook secret anywhere: not in errors, debug output or tests with real values.
- Use test placeholders such as `yativo_sk_test_...` in tests and docs. Never real credentials.
- Keep HTTPS enforcement, constant-time signature checks and the refusal to follow redirects.

Found a vulnerability? Don't open an issue: see [SECURITY.md](SECURITY.md).

## Releasing (maintainers)

1. Move "Unreleased" entries in `CHANGELOG.md` under the new version.
2. Bump the version number.
3. Tag `vX.Y.Z` and publish a GitHub release.

## License

By contributing, you agree that your contributions are licensed under the [MIT License](LICENSE).
