# Vault inbox

Drop knowledge-vault notes here, unedited, one markdown file per note, named as in the vault
(`<note-name>.md`, keeping any date prefix). Agents cannot read the vault; they can read this directory.

This is a staging area, not documentation. `/finding` migrates each note: measurements become dated `docs/` notes, quirks and limits become
`docs/playbook.md` gotchas, procedures become patterns, and every vault reference in the repo is replaced.
A note's file is deleted from here in the commit that migrates it, so whatever is left is still to do.
Nothing else should cite a file in this directory.

Before committing a note, strip anything that should not be public: API keys, tokens, personal details.

## Notes wanted

None outstanding. All fifteen notes the repo cited were migrated on 2026-11-13 (where each went: TODO.md
Done, 2026-11-13, two entries) and their files removed from here.

The migrated notes point at these, which the repo never cited and which were not requested:
`cta-stop-watch-dataset`, `dlsd-cache-last30d-semantics`, `mansueto-processed-max-bus-stop-time`,
`parquet-verification-results`, `michigan-ave-pattern-endpoint-coverage`,
`michigan-ave-shared-observation-window`, `pid-trip-count-skew`, `raw-vs-processed-pipeline`,
`eda-notebook-routes-8-65-66`. Add one if it holds a measurement, a quirk or a procedure the `docs/` notes
do not; `michigan-ave-pattern-endpoint-coverage` (the original PID 6402 Monroe mismatch) is the likeliest.

Any other note in the vault project `cta-bus-analysis` that records an API limit, a dataset quirk or a
measurement is welcome too.
