The daily pipeline skipped `grid_india` on 2026-10-31.

- State: `failed`
- Newest value: 2026-10-26
- Detail: listing failed: ConnectionError(MaxRetryError("HTTPSConnectionPool(host='webapi.grid-india.in', port=443): Max retries exceeded with url: /api/v1/file (Caused by ProtocolError('Connection aborted.', ConnectionResetError(104, 'Connection reset by peer')))"))

Other sources and models ran normally. The skip is recorded as a gap in `health/source_health.csv` on the data branch. Close this issue when the source recovers.
