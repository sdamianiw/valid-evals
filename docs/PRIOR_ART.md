# Prior art

Independent search on 2026 10 17, written to falsify the novelty claim. Pieces: (1) a decision rule sealed by
hash before the run, (2) a deterministic validity gate over traces that drops invalid runs before scoring,
(3) two judges from different vendors that must agree, calibrated against human labels with kappa.

| Tool or work | 1 | 2 | 3 | Source |
|---|---|---|---|---|
| Inspect Scout (UK AISI) | no | partial: `grep_scanner` and LLM scanners; no exclusion from the score described | partial: scanner accuracy against human labels, no agreement rule | inspect.aisi.org.uk/scanners.html (checked twice) |
| AISI transcript scanners paper | no | partial: LLM scanners flag ground truth access | partial: human labels | arXiv 2607.27518 (abstract only) |
| HAL, Holistic Agent Leaderboard | no | partial: LLM log analysis found agents looking up answers | no | arXiv 2510.11977 |
| Docent (Transluce) | no | partial: LLM search over transcripts | partial: human labels | docs.transluce.org |
| METR reward hacking report | no | describes the problem | no | metr.org/blog/2025-06-05-recent-reward-hacking |
| OpenAI chain of thought monitoring | no | partial: LLM monitor | no | arXiv 2503.11926 |
| Agentic Benchmark Checklist | no | partial: design checklist, not a gate | no | arXiv 2507.02825 |
| PoLL, juries instead of judges | no | no | partial: panel of disjoint model families; aggregation not checked here | arXiv 2404.18796 (abstract checked) |
| LangSmith Align Evals | no | no | partial: one judge aligned to human labels | blog.langchain.com/introducing-align-evals |
| arXiv 2607.06001 | partial: rules frozen in a public git chain | no | no | abstract only |
| arXiv 2607.00276 | partial: locked pre-registrations | no | partial: dual LLM judging | abstract only |
| BIG-bench canary | no | partial: canary against training contamination, not in run reads | no | BIG-bench |
| promptfoo | no | no | no agreement rule found | promptfoo.dev |

Verdict: partly novel. Every piece exists; no tool found combines the three as refusing gates. Confidence 0.6.

Not checked: OpenAI Evals, Braintrust, HELM, the SWE-bench harness and the METR task standard (not opened);
whether Inspect approval policies act as a tool allowlist gate; whether Scout findings can drop samples; full
texts of the two 2607 papers and of PoLL.
