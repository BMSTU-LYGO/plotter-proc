import numpy as np

from plotter_processor.centerline_font.topology import (
    classify_skeleton_pixel,
    crossing_number,
    topology_neighbors,
)


def test_crossing_number_does_not_turn_diagonal_corner_into_junction() -> None:
    mask = np.zeros((7, 7), dtype=bool)
    mask[1:4, 3] = True
    mask[3, 3:6] = True
    assert crossing_number((3, 3), mask) == 2
    assert classify_skeleton_pixel((3, 3), mask) == "regular"


def test_corner_diagonal_is_suppressed_when_orthogonal_path_exists() -> None:
    mask = np.zeros((5, 5), dtype=bool)
    mask[2, 2] = mask[2, 3] = mask[3, 3] = True
    assert (3, 3) not in topology_neighbors(
        (2, 2), mask, suppress_corner_diagonals=True
    )


def test_t_and_x_are_junctions() -> None:
    t = np.zeros((7, 7), dtype=bool)
    t[3, 1:6] = True
    t[3:6, 3] = True
    assert crossing_number((3, 3), t) == 3
    x = np.zeros((7, 7), dtype=bool)
    for index in range(1, 6):
        x[index, index] = True
        x[index, 6 - index] = True
    assert crossing_number((3, 3), x) == 4
