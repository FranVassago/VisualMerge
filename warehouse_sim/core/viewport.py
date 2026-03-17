import math
from typing import Optional, Tuple

from core.constants import CELL_SIZE


class Viewport:
    def __init__(self, camera_x: float, camera_y: float, zoom: float) -> None:
        self.camera_x = camera_x
        self.camera_y = camera_y
        self.zoom = zoom

    def world_to_screen(self, wx: float, wy: float) -> Tuple[int, int]:
        return int((wx - self.camera_x) * self.zoom), int((wy - self.camera_y) * self.zoom)

    def screen_to_world(self, sx: int, sy: int) -> Tuple[float, float]:
        return sx / self.zoom + self.camera_x, sy / self.zoom + self.camera_y

    def world_to_cell(self, wx: float, wy: float) -> Tuple[int, int]:
        return math.floor(wx / CELL_SIZE), math.floor(wy / CELL_SIZE)

    def cell_center(self, cell: Tuple[int, int]) -> Tuple[float, float]:
        return (cell[0] * CELL_SIZE + CELL_SIZE / 2, cell[1] * CELL_SIZE + CELL_SIZE / 2)

    def zoom_with_center_anchor(self, factor: float, anchor: Optional[Tuple[int, int]] = None) -> None:
        anchor = anchor or (0, 0)
        old_zoom = self.zoom
        old_wx, old_wy = self.screen_to_world(*anchor)
        self.zoom = max(0.2, min(2.4, old_zoom * factor))
        new_wx, new_wy = self.screen_to_world(*anchor)
        self.camera_x += old_wx - new_wx
        self.camera_y += old_wy - new_wy
