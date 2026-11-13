# Vault inbox

Drop knowledge-vault notes here, unedited, one markdown file per note, named as in the vault
(`<note-name>.md`, keeping any date prefix). Agents cannot read the vault; they can read this directory.

This is a staging area, not documentation. `/finding` migrates each note (TODO.md Foundation, "Migrate the
durable knowledge-vault notes"): measurements become dated `docs/` notes, quirks and limits become
`docs/playbook.md` gotchas, procedures become patterns, and every vault reference in the repo is replaced.
A note's file is deleted from here in the commit that migrates it, so whatever is left is still to do.
Nothing else should cite a file in this directory.

Before committing a note, strip anything that should not be public: API keys, tokens, personal details.

## Notes wanted

Migrated 2026-11-13 and removed from here: `canonical-data-views`, `cta-bus-tracker-api`,
`cta-holiday-schedule-filtering`, `michigan-ave-segment-view`, `mansueto-imputed-stop-times` (where each
went: TODO.md Done, 2026-11-13).

Still wanted, because the repo cites them:

| Vault note | Cited in |
|---|---|
| `michigan-ave-bus-lane-segment` | README.md, TODO.md |
| `michigan-ave-corridor-stops-snapshot` | TODO.md |
| `michigan-ave-6402-pattern-trim` | README.md, TODO.md |
| `michigan-ave-slow-hour-corridor-plots` | TODO.md, `notebooks/michigan_ave_speed_plots.ipynb` |
| `rt-to-pid-missing-parquet` | TODO.md |
| `cta-stop-watch-freshness-check` | DECISIONS.md |
| `dlsd-rush-hour-min-sample` | TODO.md, `notebooks/dlsd_express_comparison_plots.ipynb` |
| `lsd-express-segment-boundaries` | DLSD notebooks |
| `2026-09-24-dlsd-rush-express-routes` | DLSD notebooks |
| `2026-09-15-processed-parquet-verification-checklist` | `scripts/verify_parquet.py`, `notebooks/michigan_ave_route_identification.ipynb` |

The migrated notes also pointed at these, which the repo does not cite: `cta-stop-watch-dataset`,
`dlsd-cache-last30d-semantics`, `mansueto-processed-max-bus-stop-time`, `parquet-verification-results`,
`michigan-ave-pattern-endpoint-coverage`. Add them if they hold something the notes above do not.

Any other note in the vault project `cta-bus-analysis` that records an API limit, a dataset quirk or a
measurement is welcome too, cited or not.
