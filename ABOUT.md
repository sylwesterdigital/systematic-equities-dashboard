# About — Systematic Equities Minimal Dashboard

## Purpose
Provide a **dead-simple, front-office-friendly** scaffold to demonstrate the daily loop of a systematic equities desk:
**upload data → compute signal → construct portfolio → view results → export**.

## Design principles
- **Monolithic, transparent:** Single Flask app with Jinja templates; no app builders.
- **Minimal, not trivial:** Real L/S construction with turnover costs and guardrails.
- **Zero ceremony:** SVG charting, CSV I/O, no client-side frameworks.

## What it shows
- Cross-sectional momentum signal with gap handling
- Dollar neutrality and per-name caps
- Cost awareness via turnover bps
- Reproducible runs (CSV exports) and quick visual feedback

## Non-goals (by design)
- No vendor data connectors
- No full execution stack or OMS
- No risk model beyond basic metrics (yet)

## Extensions (recommended next)
- **Constraints:** sector neutrality; β targeting vs benchmark
- **Execution:** simple TWAP/VWAP simulator; arrival/realized slippage; basic impact curve
- **TCA:** per-day slippage attribution, turnover diagnostics
- **Perf & quality:** pytest for signals/weights; CI linting
- **Analytics:** factor exposure snapshot; turnover and PnL decomposition

## Notes on data quality
- Ensure split/dividend adjustments are consistent if extending beyond simple momentum.
- Validate survivorship (universe definition) if backtests are expanded.

## Credits
© 2025 WORKWORK.FUN LTD — minimal research → portfolio → results loop.
