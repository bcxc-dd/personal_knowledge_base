# Evidence hard-veto ablation (diagnostic)

This benchmark closes the E4 research thread by testing the product question that E4 raised: whether a heuristic evidence assessment should be able to veto a response. It does not modify E4 or production code.

## Frozen inputs and comparison

- Inputs: the human-signed Chinese `TEST_FROZEN v1` (21 questions, 21 positive and 21 same-document negative evidence units) and its one-time E0/E4 blind results. F03's two multi-chunk units remain separate diagnostics.
- `hard_veto`: replay E0 routing. `NONE` produces the production-style refusal without calling the answer model. `FULL` or `PARTIAL` calls the model; `PARTIAL` includes the production-style missing-fact note.
- `advisory`: provide the **same evidence text, source title, page and question** to the same answer model. E0's label is disclosed as fallible advisory information. The model must independently check the source, answer supported facts with citations, state partial support, or abstain.
- Both variants use the same source-only system instructions and citation format. No gold labels, expected answers, required facts or hard-negative status are sent to the model.
- This is a fixed-evidence generation comparison. It does not exercise retrieval, parser or chunking. The corpus and gold have already been inspected during the E0/E4 benchmark, so these results are diagnostic, **not a new independent TEST** and cannot alone authorize a production change.

## Review criteria fixed before calls

For human-signed `FULL`, success requires all required facts, proper scope and values, without contradiction; a refusal is a false refusal. For `NONE`, success is an explicit evidence-bound abstention; an asserted answer is unsupported. For `PARTIAL`, success identifies the available fact and the missing part without presenting a full answer. Factual answers also require a valid citation to the supplied evidence. Record answer completeness, unsupported assertions, false refusal, citation accuracy, and latency separately; do not equate model confidence with correctness.

No E5, query rewrite, retriever, reranker or index changes. The result report must distinguish a successful `hard_veto` abstention from a gate that incorrectly suppressed a complete source. If the diagnostic favors advisory routing, a separate fresh Chinese test set and real retrieval context are required before production migration.
