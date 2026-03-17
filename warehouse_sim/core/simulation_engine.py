import json
import math
import urllib.error
import urllib.request
from collections import deque
from typing import Callable, Dict, Optional, Tuple

from core.constants import CELL_SIZE, DIRS
from core.models import Box, Element


class SimulationEngine:
    def __init__(
        self,
        elements: Dict[Tuple[int, int], Element],
        boxes: Dict[str, Box],
        occupants: Dict[Tuple[int, int], deque],
        settings: Dict,
        logger,
        world_to_cell: Callable[[float, float], Tuple[int, int]],
        cell_center: Callable[[Tuple[int, int]], Tuple[float, float]],
        next_box_id: Callable[[], str],
        next_tracking_id: Callable[[], int],
        on_log: Callable[[str], None],
        on_error: Callable[[Element, str], None],
    ) -> None:
        self.elements = elements
        self.boxes = boxes
        self.occupants = occupants
        self.settings = settings
        self.logger = logger
        self.world_to_cell = world_to_cell
        self.cell_center = cell_center
        self.next_box_id = next_box_id
        self.next_tracking_id = next_tracking_id
        self.on_log = on_log
        self.on_error = on_error

    def element_capacity(self, element: Element) -> int:
        return 4 if element.kind == "induction" else element.capacity

    def spawn_box(self, cell: Tuple[int, int], element: Element, box_id: str) -> None:
        if len(self.occupants.get(cell, deque())) >= self.element_capacity(element):
            return
        cx, cy = self.cell_center(cell)
        direction = DIRS.get(element.rotation, (1, 0))
        box = Box(box_id=box_id, x=cx, y=cy, direction=direction, current_cell=cell, current_element=cell)
        self.boxes[box.box_id] = box
        self.occupants.setdefault(cell, deque()).append(box.box_id)
        element.fifo.append(box.box_id)
        self.on_log(f"Caja {box.box_id} liberada por inducción {cell}")

    def element_direction(self, element: Element, box: Box) -> Tuple[int, int]:
        if element.kind in ("belt", "belt_input", "induction"):
            return DIRS.get(element.rotation, (1, 0))
        if element.kind == "diverter":
            if box.next_diverter_dir is None:
                options = [(0, -1), (1, 0), (0, 1)]
                choice = options[element.rr_index % len(options)]
                element.rr_index += 1
                box.next_diverter_dir = choice
            return box.next_diverter_dir
        return box.direction

    def try_move_box(self, box: Box, dt: float) -> None:
        speed = self.settings["sim_speed_cells"] * CELL_SIZE
        dx, dy = box.direction
        new_x, new_y = box.x + dx * speed * dt, box.y + dy * speed * dt
        cur_cell = self.world_to_cell(box.x, box.y)
        next_cell = self.world_to_cell(new_x, new_y)

        if next_cell != cur_cell:
            target_el = self.elements.get(next_cell)
            if target_el is not None:
                occ = self.occupants.setdefault(next_cell, deque())
                if len(occ) >= self.element_capacity(target_el):
                    return

            old_element_cell = box.current_element
            box.x, box.y = new_x, new_y
            box.current_cell = next_cell

            if old_element_cell != next_cell:
                if old_element_cell is not None and old_element_cell in self.occupants:
                    if box.box_id in self.occupants[old_element_cell]:
                        self.occupants[old_element_cell].remove(box.box_id)
                    old_el = self.elements.get(old_element_cell)
                    if old_el is not None and box.box_id in old_el.fifo:
                        old_el.fifo.remove(box.box_id)

                if target_el is not None:
                    self.occupants.setdefault(next_cell, deque()).append(box.box_id)
                    target_el.fifo.append(box.box_id)
                    box.current_element = next_cell
                    box.pending_turn_cell = next_cell
                    box.pending_direction = self.element_direction(target_el, box)
                    if target_el.kind != "diverter":
                        box.next_diverter_dir = None
                else:
                    box.current_element = None
                    box.pending_turn_cell = None
                    box.pending_direction = None
        else:
            box.x, box.y = new_x, new_y

        if box.pending_turn_cell is not None and box.pending_direction is not None:
            center_x, center_y = self.cell_center(box.pending_turn_cell)
            dir_x, dir_y = box.direction
            crossed_center = (
                (dir_x > 0 and box.x >= center_x)
                or (dir_x < 0 and box.x <= center_x)
                or (dir_y > 0 and box.y >= center_y)
                or (dir_y < 0 and box.y <= center_y)
            )
            if crossed_center:
                box.direction = box.pending_direction
                box.pending_direction = None
                box.pending_turn_cell = None

    def call_scan_endpoint(self, payload: Dict) -> Tuple[int, Dict]:
        req = urllib.request.Request(
            self.settings["scan_endpoint"],
            method="POST",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                body = resp.read().decode("utf-8") or "{}"
                return int(resp.status), json.loads(body)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8") or "{}"
            try:
                parsed = json.loads(body)
            except json.JSONDecodeError:
                parsed = {"message": body}
            return exc.code, parsed
        except Exception as exc:  # noqa: BLE001
            return 500, {"message": f"Sistema no disponible. {exc}"}

    def run_induction_cycle(self, cell: Tuple[int, int], element: Element) -> None:
        if not element.tag:
            element.tag = self.settings["scanner_default_tag"]

        if not element.tag:
            return

        if element.held_box_id is None:
            try:
                box_id = self.next_box_id()
                tracking_id = self.next_tracking_id()
            except Exception as exc:  # noqa: BLE001
                self.logger.exception("Oracle fetch failed for induction cell=%s tag=%s", cell, element.tag)
                self.on_error(element, f"Error consultando Oracle: {exc}")
                return
            payload = {"scannerId": element.tag, "barcode": box_id, "trackingId": tracking_id}
            status, body = self.call_scan_endpoint(payload)
            if status >= 400:
                self.logger.error("Scan endpoint error status=%s payload=%s response=%s", status, payload, body)
                self.on_error(element, str(body.get("message", "Sistema no disponible.")))
                return
            decision = int(body.get("decision", 0))
            if decision == 0:
                element.held_box_id = box_id
                element.held_tracking_id = tracking_id
                element.held_decision = decision
                self.on_log(f"Inducción {element.tag}: caja {box_id} retenida ({tracking_id})")
            else:
                self.spawn_box(cell, element, box_id)
        else:
            payload = {
                "scannerId": element.tag,
                "trackingId": element.held_tracking_id,
                "decision": element.held_decision,
            }
            status, body = self.call_scan_endpoint(payload)
            if status >= 400:
                self.logger.error("Scan endpoint polling error status=%s payload=%s response=%s", status, payload, body)
                self.on_error(element, str(body.get("message", "Sistema no disponible.")))
                return
            decision = int(body.get("decision", 0))
            if decision == 99:
                self.spawn_box(cell, element, element.held_box_id)
                self.on_log(f"Inducción {element.tag}: libera caja en espera {element.held_box_id}")
                element.held_box_id = None
                element.held_tracking_id = None
                element.held_decision = None

    def update(self, dt: float, is_running: bool) -> None:
        if not is_running:
            return

        for cell, el in self.elements.items():
            if el.kind == "induction":
                el.spawn_timer += dt
                if el.spawn_timer >= self.settings["induction_poll_interval"]:
                    el.spawn_timer = 0.0
                    self.run_induction_cycle(cell, el)

        for box in list(self.boxes.values()):
            self.try_move_box(box, dt)
            if abs(box.x) > CELL_SIZE * 200 or abs(box.y) > CELL_SIZE * 200:
                if box.current_element in self.occupants and box.box_id in self.occupants[box.current_element]:
                    self.occupants[box.current_element].remove(box.box_id)
                self.boxes.pop(box.box_id, None)
