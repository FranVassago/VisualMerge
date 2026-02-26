from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Optional, Tuple


@dataclass
class Element:
    kind: str
    rotation: int = 0
    capacity: int = 1
    spawn_timer: float = 0.0
    rr_index: int = 0
    fifo: deque = field(default_factory=deque)
    tag: Optional[str] = None
    held_box_id: Optional[str] = None
    held_tracking_id: Optional[int] = None
    held_decision: Optional[int] = None
    has_error: bool = False


@dataclass
class Box:
    box_id: str
    x: float
    y: float
    direction: Tuple[int, int]
    current_cell: Tuple[int, int]
    current_element: Optional[Tuple[int, int]]
    next_diverter_dir: Optional[Tuple[int, int]] = None
    pending_direction: Optional[Tuple[int, int]] = None
    pending_turn_cell: Optional[Tuple[int, int]] = None


@dataclass
class ContextMenu:
    menu_type: str
    cell: Optional[Tuple[int, int]] = None
    box_id: Optional[str] = None
    screen_pos: Tuple[int, int] = (0, 0)
