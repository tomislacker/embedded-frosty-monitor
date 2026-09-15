# frosty-analysis

Offline analysis pipeline for `frosty-monitor` microSD diagnostic dumps.
Loads a card dump pulled from a DAQ installed in a frozen-drink machine and
produces plots for failure diagnosis.

The on-card format this package reads is defined authoritatively in
[`../docs/firmware/data-format-spec.md`](../docs/firmware/data-format-spec.md)
— if this package and that document ever disagree, the spec wins and this
is a bug.

## Install

This is an Arch (externally-managed Python) friendly workflow — always
install into a venv, never into system Python:

```sh
cd analysis
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Run the tests:

```sh
pytest tests
```

## Quickstart

```python
from frosty_analysis import load_deployment, load_vibration_burst
from frosty_analysis.plots import plot_channels, plot_state_timeline, plot_burst_spectrogram

dep = load_deployment("tests/fixtures/sample_deployment")

dep.channels      # DataFrame, tz-aware UTC DatetimeIndex, 1 row/s
dep.events        # DataFrame of button/system/trigger/error events
dep.vib_summary   # DataFrame, one row per captured vibration burst
dep.burst_files   # sorted list of raw vib_<pod>_<ts_unix_ms>.bin paths

fig, axes = plot_channels(dep)
fig, ax = plot_state_timeline(dep)

burst = load_vibration_burst(dep.burst_files[0])
fig, ax = plot_burst_spectrogram(burst, axis="z")
```

See `notebooks/01_quickstart.ipynb` for a fuller walkthrough, including the
burst waveform plot and a listing of the roadmap signature-detector stubs
in `frosty_analysis/signatures.py`.

## Fixture regeneration

`tests/fixtures/sample_deployment/` is a small, synthetic-but-format-correct
card dump checked into the repo so the test suite (and the quickstart
notebook) don't depend on real field data. It's generated deterministically
(seeded `np.random.default_rng(42)`) by `tests/make_fixture.py`. To
regenerate it after a format or fixture-shape change:

```sh
cd analysis
python tests/make_fixture.py
```

This overwrites everything under `tests/fixtures/sample_deployment/` in
place. Commit the regenerated fixture alongside the script change that
produced it.
