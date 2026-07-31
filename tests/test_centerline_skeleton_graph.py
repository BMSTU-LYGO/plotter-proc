import numpy as np

from plotter_processor.centerline_font.skeleton_graph import (
    build_skeleton_graph,
    validate_graph_coverage,
)


def test_graph_covers_t_junction_without_backtracking() -> None:
    mask = np.zeros((9, 9), dtype=bool)
    mask[2, 2:7] = True
    mask[2:7, 4] = True
    nodes, edges = build_skeleton_graph(mask)
    validate_graph_coverage(mask, nodes, edges)
    assert len(edges) == 3
    assert sum(node.kind == "junction" for node in nodes) == 1
