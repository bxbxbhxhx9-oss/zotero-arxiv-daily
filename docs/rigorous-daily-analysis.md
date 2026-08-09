# Rigorous Daily Paper Analysis

The daily workflow combines two research-skill patterns:

- Daily screening: the `daily-paper-generator` Top 10 -> Top 3 narrowing rule.
- Per-paper review: the ML evidence and reproducibility framework from
  [chenlu-hung/literature-review](https://github.com/chenlu-hung/literature-review).

The automated email analyzes at most three selected papers per report. Candidate
papers are ranked against the user's Zotero corpus before full text is fetched.

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
