#!/usr/bin/env python3
"""Tests for scripts/history_originality.py.

Builds real git repositories in a temporary directory and replays the exact
scenario the check exists for:

    candidate   someone else's repository (two commits, 2025)
    disguised   commit 1  README only (what GitHub creates)
                commit 2  identical copy of the candidate
                commit 3  every identifier renamed
                commit 4  comments rewritten, indentation changed
                commit 5  functions reordered
                commit 6  one small new function
    plain       commit 1  README, commit 2 identical copy, commit 3 small edit
    honest      unrelated code written over three commits
    starter     course starter code (the candidate) + the student's own file

Run from the project root:  python3 tests/test_history_originality.py
Needs only python3 and git.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "history_originality.py")
SRC = os.path.join(ROOT, "tests", "fixtures", "history")

sys.path.insert(0, os.path.join(ROOT, "scripts"))
import history_originality as ho  # noqa: E402

RENAMES = {
    "build_adjacency": "make_graph_map", "breadth_first_order": "bfs_walk",
    "dijkstra": "shortest_paths", "reconstruct_path": "trace_route",
    "topological_sort": "order_tasks", "UnionFind": "DisjointSets",
    "kruskal": "min_tree", "graph": "g_map", "edges": "links", "start": "origin",
    "node": "vertex", "neighbour": "adj", "weight": "cost", "visited": "seen_set",
    "order": "walk", "queue": "pending", "distances": "dist_map",
    "previous": "parent_of", "heap": "pq", "current_distance": "d_now",
    "candidate_distance": "d_try", "path": "route_list", "step": "hop",
    "indegree": "incoming", "ready": "free_now", "result": "out_list",
    "parent": "up", "rank": "depth", "item": "elem", "first": "x_item",
    "second": "y_item", "root_a": "rx", "root_b": "ry", "forest": "ds",
    "tree": "mst", "source": "src", "target": "dst", "line": "raw",
    "lines": "raw_lines", "handle": "fh", "total": "mst_cost", "route": "rt",
    "argv": "args_in", "read_edges": "parse_links", "main": "run",
    "goal": "dest", "directed": "is_directed", "count": "cnt", "items": "elems",
    "nodes": "vertices", "edge": "lnk", "find": "lookup", "union": "merge",
}


def read(name):
    with open(os.path.join(SRC, name), encoding="utf-8") as handle:
        return handle.read()


def rename(source):
    for old, new in RENAMES.items():
        source = re.sub(r"\b{0}\b".format(re.escape(old)), new, source)
    return source


def recomment(source):
    out = []
    for line in source.splitlines():
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if stripped.startswith("#"):
            out.append(" " * (indent // 2) + "# step: see the function name")
            continue
        out.append(" " * (indent // 2) + stripped)      # 4-space -> 2-space indent
        if stripped.startswith("return"):
            out.append("")
    return "\n".join(out) + "\n"


def reorder(source):
    head, *blocks = re.split(r"\n(?=def |class )", source)
    return "\n".join([head] + list(reversed(blocks))) + "\n"


def pad(source, every):
    """Insert a do-nothing statement before every `every`-th simple statement.

    A common way to break k-gram fingerprints. The result still compiles.
    """
    lines = source.splitlines()
    out = []
    blocked = ("def ", "class ", "@", "else", "elif", "except", "finally", '"""', "#")
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        prev = lines[i - 1].rstrip() if i else ""
        if (i and i % every == 0 and stripped and not stripped.startswith(blocked)
                and not prev.endswith((",", "(", "[", "{", "\\")) and not prev.lstrip().startswith("@")):
            out.append(" " * (len(line) - len(stripped)) + '_unused = len("x")')
        out.append(line)
    return "\n".join(out) + "\n"


class Git(object):
    def __init__(self, path):
        self.path = path
        os.makedirs(path)
        self.run("init", "-q")

    def run(self, *args, date=None):
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.org",
                   GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.org")
        if date:
            env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = date
        subprocess.check_call(["git", "-C", self.path] + list(args), env=env,
                              stdout=subprocess.DEVNULL)

    def commit(self, files, message, date):
        for name, content in files.items():
            with open(os.path.join(self.path, name), "w", encoding="utf-8") as handle:
                handle.write(content)
        self.run("add", "-A")
        self.run("commit", "-q", "-m", message, date=date)


class HistoryOriginality(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="history-originality-")
        work = os.path.join(cls.tmp, "work")
        os.makedirs(os.path.join(cls.tmp, "reports"))
        graphs_v1, mst, main_py = read("graphs.py"), read("graphs_mst.py"), read("main.py")
        graphs_v2 = graphs_v1 + mst
        readme = {"README.md": "# Assignment\n"}

        cand = Git(os.path.join(work, "candidate"))
        cand.commit({"graphs.py": graphs_v1}, "graph algorithms", "2025-03-01T10:00:00+01:00")
        cand.commit({"graphs.py": graphs_v2, "main.py": main_py}, "add mst and cli",
                    "2025-03-05T10:00:00+01:00")

        dis = Git(os.path.join(work, "disguised"))
        dis.commit(readme, "Initial commit", "2026-10-01T09:00:00+02:00")
        dis.commit({"graphs.py": graphs_v2, "main.py": main_py}, "implement solution",
                   "2026-10-02T21:00:00+02:00")
        g3, m3 = rename(graphs_v2), rename(main_py)
        dis.commit({"graphs.py": g3, "main.py": m3}, "refactor names", "2026-10-03T21:00:00+02:00")
        g4, m4 = recomment(g3), recomment(m3)
        dis.commit({"graphs.py": g4, "main.py": m4}, "cleanup", "2026-10-04T21:00:00+02:00")
        g5 = reorder(g4)
        dis.commit({"graphs.py": g5}, "reorganize", "2026-10-05T21:00:00+02:00")
        g6 = g5 + ("\ndef count_parts(vertices, links):\n  ds = DisjointSets(vertices)\n"
                   "  for src, dst, _ in links:\n    ds.merge(src, dst)\n"
                   "  return len({ds.lookup(v) for v in vertices})\n")
        dis.commit({"graphs.py": g6}, "add components", "2026-10-06T21:00:00+02:00")

        plain = Git(os.path.join(work, "plain"))
        plain.commit(readme, "Initial commit", "2026-10-01T09:00:00+02:00")
        plain.commit({"graphs.py": graphs_v2, "main.py": main_py}, "solution",
                     "2026-10-02T21:00:00+02:00")
        plain.commit({"main.py": main_py.replace("Command line entry point",
                                                 "Entry point")},
                     "docstring", "2026-10-03T21:00:00+02:00")

        padded = Git(os.path.join(work, "padded"))
        padded.commit(readme, "Initial commit", "2026-10-01T09:00:00+02:00")
        padded.commit({"graphs.py": graphs_v2, "main.py": main_py}, "solution",
                      "2026-10-02T21:00:00+02:00")
        p3 = pad(rename(graphs_v2), 3)
        cls.padded_source = p3
        padded.commit({"graphs.py": p3, "main.py": pad(rename(main_py), 3)}, "improve",
                      "2026-10-04T21:00:00+02:00")

        indep = Git(os.path.join(work, "independent"))
        indep.commit(readme, "Initial commit", "2026-10-01T09:00:00+02:00")
        indep.commit({"graph.py": read("independent_graphs.py")}, "my implementation",
                     "2026-10-05T21:00:00+02:00")

        inventory = read("inventory.py")
        cut = inventory.index("\ndef restock_list")
        honest = Git(os.path.join(work, "honest"))
        honest.commit(readme, "Initial commit", "2026-10-01T09:00:00+02:00")
        honest.commit({"inventory.py": inventory[:cut] + "\n"}, "products and summary",
                      "2026-10-03T21:00:00+02:00")
        honest.commit({"inventory.py": inventory}, "report", "2026-10-06T21:00:00+02:00")

        starter = Git(os.path.join(work, "starter"))
        starter.commit({"graphs.py": graphs_v2, "main.py": main_py}, "starter code",
                       "2026-10-01T09:00:00+02:00")
        starter.commit({"inventory.py": inventory}, "my part", "2026-10-04T21:00:00+02:00")

        cls.results = {}
        for name, extra in (("disguised", []), ("plain", []), ("honest", []),
                            ("padded", []), ("independent", []),
                            ("starter", []),
                            ("starter_with_base", ["--base", "work/candidate"])):
            repo = "starter" if name.startswith("starter") else name
            cls.results[name] = cls.run_script(
                ["--student", "work/" + repo, "--candidate", "work/candidate",
                 "--out", "reports/{0}.json".format(name)] + extra, name)

    @classmethod
    def run_script(cls, args, name):
        proc = subprocess.run([sys.executable, SCRIPT] + args, cwd=cls.tmp,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              universal_newlines=True)
        if proc.returncode != 0:
            raise AssertionError("{0}: exit {1}: {2}".format(name, proc.returncode, proc.stderr))
        if os.environ.get("SHOW"):
            print("\n" + proc.stdout)
        with open(os.path.join(cls.tmp, "reports", name + ".json"), encoding="utf-8") as handle:
            return handle.read(), proc.stdout

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def report(self, name):
        return json.loads(self.results[name][0])

    # ---- the scenario the check exists for --------------------------------

    def test_disguised_copy_is_detected(self):
        r = self.report("disguised")
        self.assertEqual(r["verdict"], "copied_then_disguised", r["signals"])

    def test_copy_found_in_commit_two_not_only_root(self):
        # The first commit is a README, as GitHub creates it. The copy lands in
        # commit 2; a check that only looked at the root commit would miss it.
        s = self.report("disguised")["summary"]
        self.assertEqual(s["identical_peak_ratio"], 1.0)
        self.assertNotEqual(s["identical_peak_commit"], self.report("disguised")["student"]["first_commit"])

    def test_text_falls_while_structure_stays(self):
        s = self.report("disguised")["summary"]
        self.assertGreaterEqual(s["head_structure"], 0.6)
        self.assertLess(s["head_text"], 0.5)
        self.assertGreaterEqual(s["gap_at_head"], 0.25)

    def test_head_alone_no_longer_shares_files(self):
        # HEAD has no byte-identical file left: a HEAD-only check sees nothing.
        timeline = self.report("disguised")["timeline"]
        self.assertEqual(timeline[-1]["identical_files"], 0)

    def test_chronology_says_candidate_was_first(self):
        c = self.report("disguised")["chronology"]
        self.assertTrue(c["candidate_had_it_first"], c)

    def test_disguise_with_dead_code_is_detected(self):
        # Renamed AND a do-nothing statement every third line: the trick that
        # breaks naive fingerprinting. The padded file is still valid Python.
        compile(self.padded_source, "padded.py", "exec")
        r = self.report("padded")
        self.assertEqual(r["verdict"], "copied_then_disguised", r["summary"])

    # ---- the other outcomes ------------------------------------------------

    def test_independent_same_algorithm_is_not_a_copy(self):
        # Every student in a course writes Dijkstra, BFS and Kruskal. An
        # independent implementation must not be reported as copied.
        r = self.report("independent")
        self.assertEqual(r["verdict"], "no_evidence", r["summary"])
        self.assertLess(r["summary"]["peak_structure"], 0.3)


    def test_plain_copy_is_copied_not_disguised(self):
        self.assertEqual(self.report("plain")["verdict"], "copied")

    def test_unrelated_project_has_no_evidence(self):
        r = self.report("honest")
        self.assertEqual(r["verdict"], "no_evidence")
        self.assertLess(r["summary"]["peak_structure"], 0.4)

    def test_starter_code_matches_without_base(self):
        self.assertEqual(self.report("starter")["verdict"], "copied")

    def test_starter_code_is_excluded_with_base(self):
        r = self.report("starter_with_base")
        self.assertEqual(r["verdict"], "no_evidence", r["signals"])
        self.assertEqual(r["summary"]["identical_peak_ratio"], 0.0)

    # ---- properties the system relies on ------------------------------------

    def test_output_is_deterministic(self):
        first = self.results["disguised"][0]
        again, _ = self.run_script(["--student", "work/disguised", "--candidate",
                                    "work/candidate", "--out", "reports/disguised.json"],
                                   "disguised")
        self.assertEqual(first, again)

    def test_out_outside_reports_is_refused(self):
        proc = subprocess.run([sys.executable, SCRIPT, "--student", "work/plain",
                               "--candidate", "work/candidate", "--out", "scripts/x.json"],
                              cwd=self.tmp, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(proc.returncode, 1)

    def test_student_equal_to_candidate_is_refused(self):
        proc = subprocess.run([sys.executable, SCRIPT, "--student", "work/candidate",
                               "--candidate", "work/candidate"],
                              cwd=self.tmp, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(proc.returncode, 1)

    def test_renaming_does_not_change_structure_tokens(self):
        a = "def total(items):\n    s = 0  # sum\n    for x in items:\n        s += x\n    return s\n"
        b = "def suma(lista):\n  acc = 0\n  for el in lista:\n    acc += el\n  return acc\n"
        self.assertEqual(ho.tokenize(a, "py")[1], ho.tokenize(b, "py")[1])
        self.assertNotEqual(ho.tokenize(a, "py")[0], ho.tokenize(b, "py")[0])

    def test_notebook_code_cells_are_read_outputs_ignored(self):
        nb = {"cells": [
            {"cell_type": "markdown", "source": ["# title"]},
            {"cell_type": "code", "source": ["x = 1\n", "print(x)"],
             "outputs": [{"data": {"image/png": "A" * 5000}}]}]}
        self.assertEqual(ho.notebook_source(json.dumps(nb).encode()), "x = 1\nprint(x)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
