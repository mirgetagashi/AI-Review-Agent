#!/usr/bin/env python3
"""Validate the JSON Schemas themselves, and the fixtures against them.

Needs jsonschema >= 4 (draft 2020-12). The system python3 here is 3.6 with
jsonschema 2.6, which only understands draft-04, so run this with the dev venv:

    .venv-dev/bin/python tests/test_schemas.py

Three things are checked:
  1. both schemas are themselves valid draft 2020-12 documents;
  2. the completeness rule actually bites - a report missing a criterion is
     REJECTED by the schema, which is the whole point of the contract;
  3. rubric.json and review.schema.json agree on ids and maxima, so the
     machine rubric and the contract cannot drift apart.
"""

import json
import os
import sys

from jsonschema import Draft202012Validator

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "fixtures")

passed = 0
failed = 0


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print("  PASS {0}".format(name))
    else:
        failed += 1
        print("  FAIL {0}".format(name))
        if detail:
            print("       {0}".format(detail))


def load(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def errors_for(validator, instance):
    return sorted(validator.iter_errors(instance), key=lambda e: list(e.path))


def main():
    review_schema = load(os.path.join(ROOT, "schemas", "review.schema.json"))
    verdict_schema = load(os.path.join(ROOT, "schemas", "verdict.schema.json"))
    rubric = load(os.path.join(ROOT, "rubric.json"))

    print("schemas are valid draft 2020-12")
    for name, schema in (("review.schema.json", review_schema),
                         ("verdict.schema.json", verdict_schema)):
        try:
            Draft202012Validator.check_schema(schema)
            check(name, True)
        except Exception as exc:                      # noqa: BLE001
            check(name, False, str(exc))

    review_v = Draft202012Validator(review_schema)
    verdict_v = Draft202012Validator(verdict_schema)

    print("valid fixtures pass")
    good = load(os.path.join(FIX, "review.good.json"))
    errs = errors_for(review_v, good)
    check("review.good.json validates", not errs,
          "; ".join(e.message for e in errs[:3]))

    for name in ("verdict.all-confirmed.json", "verdict.corrects-tests.json",
                 "verdict.secret-confirmed.json", "verdict.unverifiable.json",
                 "verdict.disguised-copy.json"):
        errs = errors_for(verdict_v, load(os.path.join(FIX, name)))
        check("{0} validates".format(name), not errs,
              "; ".join(e.message for e in errs[:3]))

    print("the completeness rule bites")
    missing = load(os.path.join(FIX, "review.missing-criterion.json"))
    errs = errors_for(review_v, missing)
    check("a report missing a criterion is rejected by the schema", bool(errs),
          "schema accepted an incomplete report - the contract is decorative")

    print("other structural rules bite")
    dup = json.loads(json.dumps(good))
    dup["criteria"][3] = json.loads(json.dumps(dup["criteria"][0]))
    check("a duplicated criterion is rejected",
          bool(errors_for(review_v, dup)))

    badmax = json.loads(json.dumps(good))
    badmax["criteria"][3]["max"] = 20            # tests is worth 10
    check("a criterion with the wrong max is rejected",
          bool(errors_for(review_v, badmax)))

    badev = json.loads(json.dumps(good))
    badev["criteria"][1]["evidence"] = [{"type": "file", "file": "x.py"}]  # no line
    check("evidence of type file without a line is rejected",
          bool(errors_for(review_v, badev)))

    badlevel = json.loads(json.dumps(good))
    badlevel["criteria"][3]["level"] = "missing"
    badlevel["criteria"][3]["points"] = 5
    check("level 'missing' with non-zero points is rejected",
          bool(errors_for(review_v, badlevel)))

    badfinding = json.loads(json.dumps(good))
    badfinding["findings"] = [{"type": "secrets", "evidence": [
        {"type": "file", "file": "config.py", "line": 3}]}]   # typo: secrets
    check("a misspelled finding type is rejected (a typo must not disable a penalty)",
          bool(errors_for(review_v, badfinding)))

    conf = load(os.path.join(FIX, "verdict.corrected-without-points.json"))
    check("CORRECTED without corrected_points is rejected by the schema too",
          bool(errors_for(verdict_v, conf)))

    print("rubric.json and the schema agree")
    rubric_ids = [c["id"] for c in rubric["criteria"]]
    schema_ids = review_schema["$defs"]["criterion"]["properties"]["id"]["enum"]
    check("criterion ids match", sorted(rubric_ids) == sorted(schema_ids),
          "rubric: {0} vs schema: {1}".format(sorted(rubric_ids), sorted(schema_ids)))

    contains_ids = [clause["contains"]["properties"]["id"]["const"]
                    for clause in review_schema["properties"]["criteria"]["allOf"]]
    check("every rubric criterion has a contains clause",
          sorted(contains_ids) == sorted(rubric_ids),
          "contains: {0}".format(sorted(contains_ids)))

    schema_maxima = {}
    for clause in review_schema["$defs"]["criterion"]["allOf"]:
        cond = clause.get("if", {}).get("properties", {}).get("id", {})
        if "const" in cond:
            schema_maxima[cond["const"]] = clause["then"]["properties"]["max"]["const"]
    rubric_maxima = {c["id"]: c["max"] for c in rubric["criteria"]}
    check("per-criterion maxima match", schema_maxima == rubric_maxima,
          "schema: {0} vs rubric: {1}".format(schema_maxima, rubric_maxima))

    check("maxima sum to the declared total",
          sum(rubric_maxima.values()) == rubric["total"],
          "sum={0} total={1}".format(sum(rubric_maxima.values()), rubric["total"]))

    print("level bands are contiguous and exhaustive over 0..max")
    for spec in rubric["criteria"]:
        bands = spec["bands"]
        contiguous = (bands["missing"] == [0, 0]
                      and bands["partial"][1] + 1 == bands["complete"][0]
                      and bands["complete"][1] == spec["max"]
                      and bands["partial"][0] > 0)
        check("{0} bands".format(spec["id"]), contiguous, str(bands))

    print("\npassed {0}, failed {1}".format(passed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
