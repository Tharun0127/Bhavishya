# Submitting a model

The full guide is in [CONTRIBUTING.md](https://github.com/Tharun0127/Bhavishya/blob/main/CONTRIBUTING.md) and the threat model in [SECURITY.md](https://github.com/Tharun0127/Bhavishya/blob/main/SECURITY.md).

In short:

1. Copy `submissions/_template/` to `submissions/<model_name>/`.
2. Implement `_predict(history, horizon)` returning quantiles 0.1 to 0.9 for horizons 1 to 28.
3. Put weights downloads in the `Dockerfile`. There is no network at forecast time.
4. Open a pull request. A maintainer reviews it and applies the `run-submission` label to test-run it.
