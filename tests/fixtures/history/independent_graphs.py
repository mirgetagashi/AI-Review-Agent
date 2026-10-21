import heapq
from collections import defaultdict, deque


class Graph:
    """Weighted graph stored as adjacency lists."""

    def __init__(self):
        self.adj = defaultdict(list)

    def add_edge(self, u, v, w, undirected=True):
        self.adj[u].append((v, w))
        if undirected:
            self.adj[v].append((u, w))

    def vertices(self):
        return list(self.adj.keys())


def bfs(g, s):
    seen = set([s])
    out = []
    q = deque()
    q.append(s)
    while len(q) > 0:
        u = q.popleft()
        out.append(u)
        for v, _w in g.adj[u]:
            if v in seen:
                continue
            seen.add(v)
            q.append(v)
    return out


def shortest(g, s):
    dist = {}
    prev = {}
    for v in g.vertices():
        dist[v] = None
    dist[s] = 0
    pq = []
    heapq.heappush(pq, (0, s))
    done = set()
    while pq:
        d, u = heapq.heappop(pq)
        if u in done:
            continue
        done.add(u)
        for v, w in g.adj[u]:
            nd = d + w
            if dist[v] is None or nd < dist[v]:
                dist[v] = nd
                prev[v] = u
                heapq.heappush(pq, (nd, v))
    return dist, prev


def path_to(prev, s, t):
    if t != s and t not in prev:
        return []
    out = []
    cur = t
    while cur != s:
        out.insert(0, cur)
        cur = prev[cur]
    out.insert(0, s)
    return out


def topo(g):
    state = {}
    order = []

    def visit(u):
        if state.get(u) == 1:
            raise RuntimeError("cycle")
        if state.get(u) == 2:
            return
        state[u] = 1
        for v, _ in g.adj[u]:
            visit(v)
        state[u] = 2
        order.append(u)

    for u in g.vertices():
        visit(u)
    order.reverse()
    return order


def mst(vertices, edge_list):
    leader = {}
    for v in vertices:
        leader[v] = v

    def root(x):
        while leader[x] != x:
            x = leader[x]
        return x

    chosen = []
    edge_list = sorted(edge_list, key=lambda e: e[2])
    for u, v, w in edge_list:
        ru = root(u)
        rv = root(v)
        if ru != rv:
            leader[ru] = rv
            chosen.append((u, v, w))
    return chosen
