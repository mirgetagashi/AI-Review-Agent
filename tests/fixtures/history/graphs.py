"""Small graph algorithms library used in the shortest-path assignment."""

from collections import deque
import heapq


def build_adjacency(edges, directed=False):
    # turn an edge list into an adjacency map
    graph = {}
    for source, target, weight in edges:
        graph.setdefault(source, []).append((target, weight))
        if not directed:
            graph.setdefault(target, []).append((source, weight))
        else:
            graph.setdefault(target, [])
    return graph


def breadth_first_order(graph, start):
    # visit nodes level by level
    visited = {start}
    order = []
    queue = deque([start])
    while queue:
        node = queue.popleft()
        order.append(node)
        for neighbour, _ in graph.get(node, []):
            if neighbour not in visited:
                visited.add(neighbour)
                queue.append(neighbour)
    return order


def dijkstra(graph, start):
    # classic dijkstra with a binary heap
    distances = {node: float("inf") for node in graph}
    distances[start] = 0
    previous = {}
    heap = [(0, start)]
    while heap:
        current_distance, node = heapq.heappop(heap)
        if current_distance > distances[node]:
            continue
        for neighbour, weight in graph[node]:
            candidate_distance = current_distance + weight
            if candidate_distance < distances[neighbour]:
                distances[neighbour] = candidate_distance
                previous[neighbour] = node
                heapq.heappush(heap, (candidate_distance, neighbour))
    return distances, previous


def reconstruct_path(previous, start, goal):
    # walk back from the goal to the start
    path = [goal]
    while path[-1] != start:
        step = previous.get(path[-1])
        if step is None:
            return []
        path.append(step)
    path.reverse()
    return path


def topological_sort(graph):
    # kahn's algorithm, raises on cycles
    indegree = {node: 0 for node in graph}
    for node in graph:
        for neighbour, _ in graph[node]:
            indegree[neighbour] += 1
    ready = deque(sorted(node for node, count in indegree.items() if count == 0))
    result = []
    while ready:
        node = ready.popleft()
        result.append(node)
        for neighbour, _ in graph[node]:
            indegree[neighbour] -= 1
            if indegree[neighbour] == 0:
                ready.append(neighbour)
    if len(result) != len(graph):
        raise ValueError("graph has a cycle")
    return result
