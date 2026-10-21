---
name: review
description: Review and grade a student GitHub project end to end with the reviewer and professor agents and the deterministic scorer.
argument-hint: <github-url>
disable-model-invocation: true
---

Grade the student project at: $ARGUMENTS

Run these steps in order. Do not grade anything yourself — your job is to drive
the two agents and the scorer.

1. **Validate the input.** `$ARGUMENTS` must be a single
   `https://github.com/<owner>/<repo>` URL. If it is anything else, stop and ask
   for a valid URL. Derive `<repo>` (the repository name) from it.

2. **Prepare.** Create `reports/<repo>/`.

3. **Review.** Invoke the `reviewer` agent, giving it the GitHub URL and telling
   it to write `reports/<repo>/review.json` against `schemas/review.schema.json`
   and `rubric.json`. Wait for it to finish.

4. **Verify.** Invoke the `professor` agent, giving it ONLY the path
   `reports/<repo>/review.json` and the clone at `work/<repo>`. Do not pass it
   anything the reviewer said beyond the report file. Wait for it to finish
   writing `reports/<repo>/verdict.json`.

5. **Score.** Run:
   `python3 scripts/score.py --review reports/<repo>/review.json --verdict reports/<repo>/verdict.json --rubric rubric.json --out-dir reports/<repo>`
   - Exit 0: scored, no flags.
   - Exit 3: scored but flagged — human review required. Continue, but the
     result must be shown as provisional.
   - Exit 1: invalid input. Report refused to score. Show the scorer's message
     to the responsible agent and ask it to fix its JSON, then re-run from the
     step that produced the bad file. Do this at most twice; if it still fails,
     stop and report the failure to the user. Never edit the JSON yourself to
     make it pass.

6. **Write final.md.** Invoke the `professor` agent again to write
   `reports/<repo>/final.md` from `reports/<repo>/final-table.md`.

7. **Report to the user.** Show the final score and grade, the list of
   corrections the professor made, and any human-review flags. Point to
   `reports/<repo>/final.md` for the full write-up.
