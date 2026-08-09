# Rigorous Daily Paper Analysis

The daily workflow combines two research-skill patterns:

- Daily screening: the `daily-paper-generator` Top 10 -> Top 3 narrowing rule.
- Per-paper review: the ML evidence and reproducibility framework from
  [chenlu-hung/literature-review](https://github.com/chenlu-hung/literature-review).

The automated email analyzes at most three selected papers per report. Candidate
papers are ranked against the user's Zotero corpus before full text is fetched.
Each daily email and archived report contains the complete screening trace:

1. The number of OpenAlex arXiv records retrieved by the configured queries.
2. The Top 10 candidates after Zotero-based relevance ranking.
3. The final Top 3 selected for full-text retrieval and LLM analysis.

## Required Sections

Every paper must contain these Chinese sections:

1. Core conclusion
2. Research problem and context
3. Method breakdown
4. Innovation analysis
5. Experimental evidence
6. Reproducibility check
7. Limitations and risks
8. Confidence conclusion

Innovation claims must distinguish what the authors claim, what the supplied
evidence supports, and what cannot be verified. Missing datasets, baselines,
metrics, ablations, random seeds, code, data, hyperparameters, compute, or model
weights must be reported as missing rather than inferred.

## Failure Policy

For the deployed configuration, an LLM error, non-Chinese response, empty response,
or missing required section fails the workflow before email delivery. The workflow
must never substitute an English abstract for a failed analysis.

The deployed relay configuration keeps `gpt-5.6-sol` as the primary model and uses
the independently probed `gpt-5.4` as a fallback. A timeout, server error, empty
response, or failed structure check advances to the fallback model. Both models must
pass the same Chinese evidence and section validation; this is not an abstract fallback.

## Weekly Synthesis

Historical backfill can generate one thematic weekly report from the daily Top 3
analyses in the requested date range. The weekly report follows the synthesis and
reproducibility patterns from
[chenlu-hung/literature-review](https://github.com/chenlu-hung/literature-review):

- Synthesis is organized by themes and method families, not paper-by-paper summaries.
- Every claim cites a stable evidence ID such as `[D03-P02]`.
- Numerical comparisons are allowed only when datasets, splits, metrics, and protocols
  are comparable.
- Author novelty claims are separated from evidence-supported and unverified novelty.
- Code, data, checkpoints, hyperparameters, compute, repeated seeds, and uncertainty
  reporting are checked explicitly.

The required weekly sections are:

1. Weekly overview
2. Themes and method evolution
3. Key-paper comparison
4. Innovation evidence grading
5. Experimental credibility and reproducibility
6. Research gaps and risks
7. Reading priorities for the next week

The workflow writes UTF-8 JSON and Markdown under `reports/daily/` and
`reports/weekly/`, then uploads the directory as a GitHub Actions artifact retained
for 90 days. Email HTML escapes all model-generated content.

If daily emails succeed but weekly synthesis times out, use the manual
`weekly-from-artifact.yml` workflow with the failed run ID and the same date range.
It validates that every daily JSON file is present, then retries only the weekly LLM
call with the longer weekly timeout. It does not resend any daily email.
For a resumed range, provide `additional_source_run_id` and
`additional_artifact_name`; the workflow merges the non-overlapping daily files and
refuses to synthesize until every date in the requested week is present.

For a complete month, run bounded weekly ranges instead of a single 31-day job. For
July 2026 the ranges are `07-01..07-07`, `07-08..07-14`, `07-15..07-21`,
`07-22..07-28`, and the partial week `07-29..07-31`. Pass `send_weekly=true` and
`max_papers=3` to each workflow dispatch.

## Scope Limitation

Historical discovery uses OpenAlex records whose source is arXiv. These are preprints.
The pipeline must not label a paper as accepted by an A-tier conference or journal
unless the supplied metadata independently verifies that venue. The report can assess
methodological quality and relevance, but it cannot infer an acceptance decision from
an arXiv posting.
