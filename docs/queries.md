# Quarterly review — canned queries (the telemetry questions each contract pre-registers)

One jq query per pre-registered kill criterion. Silence is data: if a
query returns all-empty for a quarter, the entry gate is set too low or
compliance has gone hollow — investigate, never let inert process ride.

1. Intent Contract earning its keep? (delta between raw request and
   confirmed intent; near-zero every time = formatting tax)
       jq -s 'map({task, d: .intent_request_delta})' telemetry.jsonl

2. Gates working or theater? (edits at consent are the gate WORKING)
       jq -s 'map(select(.intent_edited_at_gate or .plan_edited_at_gate)) | length' telemetry.jsonl

3. Execution Contract alive? (empty ledgers + zero escalations forever
   = vestigial or hollow)
       jq -s 'map({task, entries: .ledger_entries.count, esc: (.escalations|length)})' telemetry.jsonl

4. Review adjudicating or rubber-stamping? (any non-approve verdicts?)
       jq -s 'map(.verdict_sequence) | flatten | group_by(.) | map({verdict: .[0], n: length})' telemetry.jsonl

5. Non-goals prediction check (the section bet to earn Refine's keep)
       jq -s 'map(.nongoals_count) | {min: min, max: max, avg: (add/length)}' telemetry.jsonl

6. Follow-up loop closing? (lineage via the followup: source-ref
   convention; also the promotion bar for a review Follow-ups section)
       jq -s 'map(select((.task_ref // "") | startswith("followup:")))
              | {count: length, parents: (map(.task_ref) | unique)}' telemetry.jsonl

7. Lane mix — is express carrying everyday work, or is everything `full`?
   (all-full means the floor is miscalibrated and the cheap lane is inert)
       jq -s 'map(.disposition.lane // "undisposed") | group_by(.)
              | map({lane: .[0], n: length})' telemetry.jsonl

8. Override rate — the D20 kill criterion. An escape hatch must exist, but
   a rising override rate means the FLOOR is wrong, not the developers.
   Fix the policy; never treat the number as a discipline problem.
       jq -s '[.[] | select(.disposition.overridden == true)] | length' telemetry.jsonl

9. Verification alive, or hollow? (all-pass forever with no failures and no
   `inconclusive` suggests checks that cannot fail — the D19 analogue of
   query 3's empty-ledger test)
       jq -s 'map(.verifications.by_verdict) | add' telemetry.jsonl

10. Did changes move their own bar? (standard_touched with a pass is not
    wrong, but a high rate deserves a look at what reviews caught)
        jq -s 'map(select(.verifications.standard_touched)) | length' telemetry.jsonl
