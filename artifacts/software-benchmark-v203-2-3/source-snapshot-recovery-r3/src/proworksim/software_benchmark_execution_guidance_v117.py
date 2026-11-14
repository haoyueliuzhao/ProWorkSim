"""Short, shared public verification guidance, without task-specific hints."""

VERSION = 'v117-evidence-based-completion-guidance-r1'

WORKFLOW_GUIDANCE = """Repair and verification workflow:
- Use the issue and public contract to identify the requested behavior and relevant callers or edge cases. Choose an actionable hypothesis before repeating searches.
- Use the documented tools and public test entry. Collection errors, unavailable dependencies, failed commands and zero collected tests are not successful verification.
- Derive expected behavior independently of your patch. Inspect the final diff to confirm what behavior it actually changes; comments or passing unrelated tests do not establish a repair.
- Prefer a focused issue reproduction or regression test. After editing again, distinguish older test evidence from results for the current version. Reuse sufficient current evidence rather than rerunning identical checks without a reason.
- If progress stalls, use the concrete tool or test error to choose a different action, or report the unresolved limitation honestly.
All actions, self-review and history summarization share the original cumulative token, attempt, decision and time limits."""

FINISH_REVIEW = """One final self-review is available in this conversation under the remaining original budget and deadlines.
Inspect the final diff and compare its actual behavior with the issue's requested behavior, relevant callers and edge cases. Do not rely on your earlier success claim. If the final change only affects comments, formatting or tests, explain whether that truly addresses the issue. Identify what issue-specific behavior your public evidence actually exercises; unrelated passing tests, collection errors and unexecuted tests do not establish correctness.
If a concrete gap remains, use a focused public check and repair it if warranted. Reuse sufficient current-version evidence without repeating it. Finish with what changed, what actually ran, and what remains unverified. This review adds no budget, agent, automatic submission or additional review opportunity."""
