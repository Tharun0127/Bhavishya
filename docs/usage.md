# Usage

## Install

```bash
pip install bhavishya            # loaders only
pip install "bhavishya[baselines]"  # plus statsforecast and LightGBM baselines
```

Until the first release, install from GitHub:

```bash
pip install "git+https://github.com/Tharun0127/Bhavishya"
```

## Load a source

```python
import bhavishya

df = bhavishya.load("grid_india", "2026-10-01", "2026-10-26")
df.head()
#                          series_id  timestamp    value unit      source vintage_date
# 0  grid_india/energy_met/all_india 2026-10-01  ...      MU  grid_india   2026-10-02
```

Every row has the same six columns:

| Column | Meaning |
|---|---|
| `series_id` | `<source>/<metric>/<place>`, for example `cpcb_aqi/aqi/delhi` |
| `timestamp` | the date the value describes (IST calendar date) |
| `value` | float |
| `unit` | `MU`, `MW`, `aqi`, `degC` or `mm` |
| `source` | source name |
| `vintage_date` | the date this value was published, as far as we know |

## Pick series

```python
aqi = bhavishya.load("cpcb_aqi", "2026-09-01", series=["cpcb_aqi/aqi/delhi", "cpcb_aqi/aqi/mumbai"])
wide = bhavishya.to_wide(aqi)   # one column per series
```

## Ask what existed on a past date

Sources revise history. `as_of` returns the data as it was known on that date:

```python
df = bhavishya.load("grid_india", "2026-10-01", "2026-10-26", as_of="2026-10-10")
```

## Cache

Files are cached in `~/.cache/bhavishya` (or `$BHAVISHYA_DATA_DIR`). A second call for the same dates downloads nothing new. Every new file is checked against the source's data contract. A broken file raises `bhavishya.ContractError` unless you pass `strict=False`.

## List sources

```python
for s in bhavishya.list_sources():
    print(s.name, s.licence)
```

Read [Data sources](data_sources.md) for licences and attribution before you republish anything.
