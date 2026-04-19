import networkx as nx

from ranking.models import DanceResult


def build_graph(results: list[DanceResult]) -> nx.Graph:
    g = nx.Graph()
    for result in results:
        for i, a in enumerate(result.competitors):
            g.add_node(a)
            for b in result.competitors[i + 1:]:
                if g.has_edge(a, b):
                    g[a][b]["weight"] += 1
                else:
                    g.add_edge(a, b, weight=1)
    return g


def assign_leaderboards(
    graph: nx.Graph,
    min_cluster_size: int = 2,
) -> dict[str, str]:
    components = sorted(
        nx.connected_components(graph),
        key=len,
        reverse=True,
    )
    labels = _generate_labels(len(components))
    assignments: dict[str, str] = {}

    for idx, component in enumerate(components):
        label = labels[idx] if len(component) >= min_cluster_size else "Not Rated"
        for competitor in component:
            assignments[competitor] = label

    return assignments


def _generate_labels(count: int) -> list[str]:
    labels = []
    uppercase = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    lowercase = "abcdefghijklmnopqrstuvwxyz"
    for i in range(count):
        if i < 26:
            labels.append(uppercase[i])
        elif i < 52:
            labels.append(lowercase[i - 26])
        else:
            labels.append(str(i))
    return labels
