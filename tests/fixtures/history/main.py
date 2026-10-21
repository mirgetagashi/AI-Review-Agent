"""Command line entry point for the graph assignment."""

import sys

from graphs import build_adjacency, dijkstra, reconstruct_path, kruskal


def read_edges(lines):
    edges = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        source, target, weight = line.split()
        edges.append((source, target, float(weight)))
    return edges


def main(argv):
    if len(argv) != 3:
        print("usage: main.py <edges-file> <start>")
        return 2
    with open(argv[1], encoding="utf-8") as handle:
        edges = read_edges(handle)
    graph = build_adjacency(edges)
    distances, previous = dijkstra(graph, argv[2])
    for node in sorted(distances):
        route = reconstruct_path(previous, argv[2], node)
        print(node, distances[node], " -> ".join(route))
    total = sum(weight for _, _, weight in kruskal(list(graph), edges))
    print("minimum spanning tree weight:", total)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
