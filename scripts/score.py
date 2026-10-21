#!/usr/bin/env python3
"""Deterministic scorer for the AI Review Agent.

Design rule (section 8 of the design document): measurable facts must not
depend on model judgement. The final grade is the most important measurable
fact in the system, so no agent is allowed to compute it.

  Reviewer  -> proposes points per criterion, with evidence   (review.json)
  Professor -> assigns a STATUS per criterion and per claim    (verdict.json)
  this file -> computes the arithmetic, applies the special rules, emits flags

Stdlib only, Python 3.6+, no network. Same input always gives the same output,
which is what lets the project measure its own consistency.

Usage:
    score.py --review reports/<repo>/review.json \
             --verdict reports/<repo>/verdict.json \
             --rubric  rubric.json \
             --out-dir reports/<repo> \
             [--deadline 2026-11-30]

Exit codes:
    0  scored, no flags - safe to show the student
    3  scored, but flagged: REQUIRES HUMAN REVIEW before release
    1  invalid input - refused to score (schema/invariant violation)
"""

import argparse
import datetime
import json
import os
import sys

SCHEMA_VERSION = "1.0"

# Statuses that keep a criterion's points as the Reviewer proposed them.
STATUS_KEEPS_POINTS = ("CONFIRMED",)
# Statuses where the Professor must restate the rubric-correct points.
STATUS_NEEDS_CORRECTION = ("CORRECTED", "REJECTED")
# Status with a hard mechanical rule: no points, max stays in the denominator.
STATUS_UNVERIFIABLE = "UNVERIFIABLE"


class InvalidInput(Exception):
    """Raised for any violation that makes scoring unsafe."""


# --------------------------------------------------------------------------
# loading
# --------------------------------------------------------------------------

def load_json(path, label):
    if not os.path.isfile(path):
        raise InvalidInput("{0} not found: {1}".format(label, path))
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except ValueError as exc:
        raise InvalidInput("{0} is not valid JSON: {1}".format(label, exc))


def index_by_id(items, label):
    """Map id -> item, rejecting duplicates (a duplicate would double-count)."""
    out = {}
    for item in items:
        key = item.get("id")
        if key is None:
            raise InvalidInput("{0}: an entry has no 'id'".format(label))
        if key in out:
            raise InvalidInput("{0}: duplicate criterion '{1}'".format(label, key))
        out[key] = item
    return out


# --------------------------------------------------------------------------
# validation - the cross-field invariants JSON Schema cannot express
# --------------------------------------------------------------------------

def validate_review(review, rubric_by_id):
    """Check the Reviewer report against the rubric.

    JSON Schema enforces shape and completeness. These are the checks that
    need two fields compared against each other, which draft 2020-12 cannot do.
    """
    errors = []

    if review.get("schema_version") != SCHEMA_VERSION:
        errors.append("review.json: schema_version must be {0!r}, got {1!r}".format(
            SCHEMA_VERSION, review.get("schema_version")))

    criteria = review.get("criteria")
    if not isinstance(criteria, list):
        raise InvalidInput("review.json: 'criteria' must be a list")

    found = index_by_id(criteria, "review.json")

    missing = [cid for cid in rubric_by_id if cid not in found]
    if missing:
        errors.append(
            "review.json is INCOMPLETE - no claim for: {0}. A criterion the "
            "Reviewer skipped produces nothing for the Professor to verify, so "
            "it is refused here rather than graded silently.".format(
                ", ".join(sorted(missing))))

    unknown = [cid for cid in found if cid not in rubric_by_id]
    if unknown:
        errors.append("review.json: criteria not in the rubric: {0}".format(
            ", ".join(sorted(unknown))))

    for cid, crit in sorted(found.items()):
        spec = rubric_by_id.get(cid)
        if spec is None:
            continue
        where = "review.json[{0}]".format(cid)
        points = crit.get("points")
        declared_max = crit.get("max")
        level = crit.get("level")

        if declared_max != spec["max"]:
            errors.append("{0}: max is {1}, rubric says {2}".format(
                where, declared_max, spec["max"]))

        if not isinstance(points, int):
            errors.append("{0}: points must be an integer".format(where))
            continue

        if not 0 <= points <= spec["max"]:
            errors.append("{0}: points {1} outside 0..{2}".format(
                where, points, spec["max"]))
            continue

        band = spec["bands"].get(level)
        if band is None:
            errors.append("{0}: unknown level {1!r}".format(where, level))
        elif not band[0] <= points <= band[1]:
            errors.append(
                "{0}: level {1!r} allows {2}..{3} points, got {4}. The level "
                "and the score must agree or the rubric is decorative.".format(
                    where, level, band[0], band[1], points))

        evidence = crit.get("evidence") or []
        if points > 0 and not evidence:
            errors.append(
                "{0}: {1} points with no evidence. Rule 5.3 - no points "
                "without a verifiable reference.".format(where, points))

    # The Reviewer also sums; disagreement means one of the two is unreliable.
    computed = sum(c.get("points", 0) for c in criteria
                   if isinstance(c.get("points"), int))
    if review.get("proposed_total") != computed:
        errors.append(
            "review.json: proposed_total is {0} but the criteria sum to {1}. "
            "Arithmetic drift in the report itself.".format(
                review.get("proposed_total"), computed))

    if errors:
        raise InvalidInput("\n  - ".join(["review.json failed validation:"] + errors))

    return found


def validate_verdict(verdict, review, rubric_by_id):
    errors = []

    if verdict.get("schema_version") != SCHEMA_VERSION:
        errors.append("verdict.json: schema_version must be {0!r}".format(SCHEMA_VERSION))

    if verdict.get("repo") != review.get("repo"):
        errors.append("verdict.json: repo {0!r} != review.json repo {1!r}".format(
            verdict.get("repo"), review.get("repo")))

    # Verifying a different snapshot than the one graded is not verification.
    if verdict.get("commit") != review.get("commit"):
        errors.append(
            "verdict.json: commit {0!r} != review.json commit {1!r}. The "
            "Professor verified a different snapshot than the one graded.".format(
                verdict.get("commit"), review.get("commit")))

    criteria = verdict.get("criteria")
    if not isinstance(criteria, list):
        raise InvalidInput("verdict.json: 'criteria' must be a list")

    found = index_by_id(criteria, "verdict.json")

    missing = [cid for cid in rubric_by_id if cid not in found]
    if missing:
        errors.append("verdict.json is INCOMPLETE - unverified criteria: {0}".format(
            ", ".join(sorted(missing))))

    for cid, entry in sorted(found.items()):
        spec = rubric_by_id.get(cid)
        if spec is None:
            errors.append("verdict.json: criterion {0!r} not in the rubric".format(cid))
            continue
        where = "verdict.json[{0}]".format(cid)
        status = entry.get("status")
        has_corrected = "corrected_points" in entry

        if status in STATUS_NEEDS_CORRECTION and not has_corrected:
            errors.append(
                "{0}: status {1} requires corrected_points - the Professor must "
                "state the rubric-correct score, not just that the Reviewer was "
                "wrong.".format(where, status))
        if status in STATUS_KEEPS_POINTS and has_corrected:
            errors.append("{0}: CONFIRMED must not carry corrected_points".format(where))
        if status == STATUS_UNVERIFIABLE and has_corrected:
            errors.append("{0}: UNVERIFIABLE must not carry corrected_points "
                          "(points are forced to 0)".format(where))
        if has_corrected:
            value = entry["corrected_points"]
            if not isinstance(value, int) or not 0 <= value <= spec["max"]:
                errors.append("{0}: corrected_points {1} outside 0..{2}".format(
                    where, value, spec["max"]))
        if status not in STATUS_KEEPS_POINTS + STATUS_NEEDS_CORRECTION + (STATUS_UNVERIFIABLE,):
            errors.append("{0}: unknown status {1!r}".format(where, status))

    if errors:
        raise InvalidInput("\n  - ".join(["verdict.json failed validation:"] + errors))

    return found


# --------------------------------------------------------------------------
# scoring
# --------------------------------------------------------------------------

def score_criteria(review_by_id, verdict_by_id, rubric):
    """Apply the statuses. Section 5.5 steps 1-2."""
    rows = []
    for spec in rubric["criteria"]:
        cid = spec["id"]
        proposed = review_by_id[cid]["points"]
        entry = verdict_by_id[cid]
        status = entry["status"]

        if status == STATUS_UNVERIFIABLE:
            # Points excluded, max retained. Keeping the max in the denominator
            # is deliberate: dropping it would silently rescale the grade.
            final = 0
        elif status in STATUS_NEEDS_CORRECTION:
            final = entry["corrected_points"]
        else:
            final = proposed

        rows.append({
            "id": cid,
            "title": spec["title"],
            "max": spec["max"],
            "proposed": proposed,
            "status": status,
            "final": final,
            "delta": final - proposed,
            "reason": entry.get("reason", ""),
        })
    return rows


def confirmed_finding_types(verdict):
    """Only verified findings may move the grade."""
    out = set()
    for finding in verdict.get("findings") or []:
        if finding.get("status") in ("CONFIRMED", "CORRECTED"):
            out.add(finding.get("type"))
    return out


def apply_special_rules(rows, verdict, rubric, deadline):
    """Section 5.4. Every rule either changes points or raises a flag, never both
    silently."""
    rules = rubric["special_rules"]
    by_id = {row["id"]: row for row in rows}
    flags = []
    notes = []
    confirmed = confirmed_finding_types(verdict)

    if "secret" in confirmed and rules.get("secret_confirmed_zeroes_security"):
        row = by_id["security"]
        if row["final"] != 0:
            notes.append(
                "security {0} -> 0: confirmed secret in the repository or its "
                "history (rule 5.4)".format(row["final"]))
            row["final"] = 0
            row["delta"] = row["final"] - row["proposed"]
        flags.append("secret_confirmed")

    if "originality_match" in confirmed:
        # Section 5.4 says "originality is lowered", section 9 says
        # "flag for the human, not an automatic penalty". The document
        # contradicts itself; flag-only is implemented because a match can be a
        # permitted template or library and only a human can tell.
        flags.append("originality_match_needs_human")
        notes.append("originality: match flagged, no automatic deduction "
                     "(permitted templates are indistinguishable to the tool)")

    if "copied_then_disguised" in confirmed:
        # The project matched a source repository in an early commit and the
        # later commits only renamed, reformatted or reordered it (evidence from
        # scripts/history_originality.py). Flag-only for the same reason as an
        # originality match: permitted starter code is a human's call.
        flags.append("copied_then_disguised_needs_human")
        notes.append("originality: an early commit matches a source repository and later "
                     "commits changed only names, formatting or order - flagged, no "
                     "automatic deduction")

    if "injection_attempt" in confirmed:
        flags.append("injection_attempt")
        notes.append("injection attempt recorded: no positive effect on the grade")

    if "drastic_history" in confirmed:
        if deadline is None:
            flags.append("drastic_history_unevaluable_no_deadline")
            notes.append("drastic history finding present but no --deadline was "
                         "given, so the 'all code near the deadline' rule in 5.4 "
                         "could not be evaluated")
        else:
            flags.append("drastic_history")
            notes.append("drastic history relative to deadline {0}: git_process "
                         "assessed by the Professor, flagged for the human".format(deadline))

    unverifiable = [row["id"] for row in rows if row["status"] == STATUS_UNVERIFIABLE]
    if len(unverifiable) > rules.get("max_unverifiable_claims", 3):
        flags.append("too_many_unverifiable")
        notes.append("{0} unverifiable criteria ({1}) exceed the limit of {2}: the "
                     "grade is not sufficiently supported".format(
                         len(unverifiable), ", ".join(unverifiable),
                         rules.get("max_unverifiable_claims", 3)))

    proposed_total = sum(row["proposed"] for row in rows)
    final_total = sum(row["final"] for row in rows)
    threshold = rules.get("large_delta_threshold", 15)
    if abs(final_total - proposed_total) > threshold:
        flags.append("large_delta")
        notes.append("Professor moved the total by {0:+d} points (> {1}): high "
                     "disagreement means high uncertainty".format(
                         final_total - proposed_total, threshold))

    return flags, notes


def to_grade(total, rubric):
    for band in rubric["grade_scale"]:
        if band["min"] <= total <= band["max"]:
            return band["grade"]
    raise InvalidInput("total {0} falls outside every grade band".format(total))


# --------------------------------------------------------------------------
# output
# --------------------------------------------------------------------------

def render_table(rows, result):
    lines = [
        "| Kriteri | Max | Reviewer | Statusi | Finale | Ndryshim |",
        "|---|---:|---:|---|---:|---:|",
    ]
    for row in rows:
        lines.append("| {0} | {1} | {2} | {3} | {4} | {5} |".format(
            row["title"], row["max"], row["proposed"], row["status"],
            row["final"], "{0:+d}".format(row["delta"]) if row["delta"] else "-"))
    lines.append("| **Totali** | **100** | **{0}** | | **{1}** | **{2:+d}** |".format(
        result["proposed_total"], result["final_total"],
        result["final_total"] - result["proposed_total"]))
    return "\n".join(lines)


def render_markdown(rows, result):
    out = []
    if result["requires_human_review"]:
        out.append("## Kerkon rishikim njerezor\n")
        out.append("Nota nuk publikohet automatikisht. Arsyet:\n")
        for flag in result["flags"]:
            out.append("- `{0}`".format(flag))
        out.append("")
    out.append("## Nota: {0}/100 (shkalla: {1})\n".format(
        result["final_total"], result["grade"]))
    out.append(render_table(rows, result))
    if result["adjustments"]:
        out.append("\n## Korrigjimet dhe rregullat e zbatuara\n")
        for note in result["adjustments"]:
            out.append("- {0}".format(note))
    out.append("\n<!-- generated by scripts/score.py - do not edit by hand -->")
    return "\n".join(out) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Compute the final grade deterministically from the "
                    "Reviewer report and the Professor verdict.")
    parser.add_argument("--review", required=True)
    parser.add_argument("--verdict", required=True)
    parser.add_argument("--rubric", default="rubric.json")
    parser.add_argument("--out-dir", help="where final.json and final-table.md are written")
    parser.add_argument("--deadline", help="YYYY-MM-DD, required to evaluate the "
                                           "'all code near the deadline' rule")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    deadline = None
    if args.deadline:
        try:
            deadline = datetime.datetime.strptime(args.deadline, "%Y-%m-%d").date().isoformat()
        except ValueError:
            print("error: --deadline must be YYYY-MM-DD", file=sys.stderr)
            return 1

    try:
        rubric = load_json(args.rubric, "rubric.json")
        review = load_json(args.review, "review.json")
        verdict = load_json(args.verdict, "verdict.json")

        rubric_by_id = index_by_id(rubric["criteria"], "rubric.json")
        if sum(spec["max"] for spec in rubric["criteria"]) != rubric["total"]:
            raise InvalidInput("rubric.json: criterion maxima do not sum to 'total'")

        review_by_id = validate_review(review, rubric_by_id)
        verdict_by_id = validate_verdict(verdict, review, rubric_by_id)

        rows = score_criteria(review_by_id, verdict_by_id, rubric)
        flags, notes = apply_special_rules(rows, verdict, rubric, deadline)

        proposed_total = sum(row["proposed"] for row in rows)
        final_total = sum(row["final"] for row in rows)

        result = {
            "schema_version": SCHEMA_VERSION,
            "repo": review["repo"],
            "commit": review["commit"],
            "proposed_total": proposed_total,
            "final_total": final_total,
            "grade": to_grade(final_total, rubric),
            "criteria": rows,
            "flags": flags,
            "adjustments": notes,
            "requires_human_review": bool(flags),
            "deadline": deadline,
            "scored_by": "scripts/score.py",
        }
    except InvalidInput as exc:
        print("REFUSED TO SCORE\n{0}".format(exc), file=sys.stderr)
        return 1

    markdown = render_markdown(rows, result)

    if args.out_dir:
        os.makedirs(args.out_dir, exist_ok=True)
        with open(os.path.join(args.out_dir, "final.json"), "w", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        with open(os.path.join(args.out_dir, "final-table.md"), "w", encoding="utf-8") as handle:
            handle.write(markdown)

    if not args.quiet:
        sys.stdout.write(markdown)

    return 3 if result["requires_human_review"] else 0


if __name__ == "__main__":
    sys.exit(main())
