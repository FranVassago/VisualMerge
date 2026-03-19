import json
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
        id_provider,
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
        self.id_provider = id_provider
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
        self.on_log(f"Caja {box.box_id} liberada en {cell}")

    def element_direction(self, element: Element, box: Box) -> Tuple[int, int]:
        if element.kind in ("belt", "belt_input", "belt_stopper", "induction"):
            return DIRS.get(element.rotation, (1, 0))
        if element.kind == "diverter":
            return self.resolve_diverter_direction(element, box)
        return box.direction

    def resolve_diverter_direction(self, element: Element, box: Box) -> Tuple[int, int]:
        if box.next_diverter_dir is not None:
            return box.next_diverter_dir

        scanner_id = (element.tag or "").strip()
        tracking_id = self.next_tracking_id()
        payload = {"scannerId": scanner_id, "trackingId": tracking_id, "barcode": box.box_id}
        decision_value = None
        if scanner_id:
            status, body = self.call_scan_endpoint(payload)
            if status >= 400:
                self.logger.error("Diverter scan endpoint error status=%s payload=%s response=%s", status, payload, body)
                self.on_error(element, str(body.get("message", "Sistema no disponible.")))
                return DIRS.get(element.rotation, (1, 0))
            decision_value = body.get("decision")
        direction = self.map_diverter_decision(element.rotation, decision_value)
        box.pending_tracking_id = tracking_id
        box.next_diverter_dir = direction
        self.on_log(
            f"Diverter {scanner_id or '-'}: caja {box.box_id} -> {self.direction_label(element.rotation, direction)} ({tracking_id})"
        )
        return direction

    @staticmethod
    def map_diverter_decision(rotation: int, decision_value) -> Tuple[int, int]:
        forward = DIRS.get(rotation, (1, 0))
        left = DIRS.get((rotation - 90) % 360, (0, -1))
        right = DIRS.get((rotation + 90) % 360, (0, 1))

        if decision_value is None:
            return forward

        raw = str(decision_value).strip().upper()
        if raw in {"IZQ", "LEFT", "L", "1", "-1"}:
            return left
        if raw in {"DER", "RIGHT", "R", "2"}:
            return right
        if raw in {"RECTO", "STRAIGHT", "S", "0", "3", "99"}:
            return forward
        return forward

    @staticmethod
    def direction_label(rotation: int, direction: Tuple[int, int]) -> str:
        if direction == DIRS.get(rotation, (1, 0)):
            return "RECTO"
        if direction == DIRS.get((rotation - 90) % 360, (0, -1)):
            return "IZQ"
        if direction == DIRS.get((rotation + 90) % 360, (0, 1)):
            return "DER"
        return str(direction)

    def can_move_to_next_cell(self, box: Box, next_cell: Tuple[int, int]) -> bool:
        target_el = self.elements.get(next_cell)
        if target_el is not None:
            occ = self.occupants.setdefault(next_cell, deque())
            if len(occ) >= self.element_capacity(target_el):
                return False

        current_element = self.elements.get(box.current_element) if box.current_element else None
        if current_element and current_element.kind == "belt_stopper":
            current_center_x, current_center_y = self.cell_center(box.current_element)
            if abs(box.x - current_center_x) <= 2 and abs(box.y - current_center_y) <= 2:
                return False
        return True

    def try_move_box(self, box: Box, dt: float) -> None:
        speed = self.settings["sim_speed_cells"] * CELL_SIZE
        dx, dy = box.direction
        new_x, new_y = box.x + dx * speed * dt, box.y + dy * speed * dt
        cur_cell = self.world_to_cell(box.x, box.y)
        next_cell = self.world_to_cell(new_x, new_y)

        if next_cell != cur_cell:
            if not self.can_move_to_next_cell(box, next_cell):
                return

            old_element_cell = box.current_element
            box.x, box.y = new_x, new_y
            box.current_cell = next_cell

            target_el = self.elements.get(next_cell)
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
                        box.pending_tracking_id = None
                else:
                    box.current_element = None
                    box.pending_turn_cell = None
                    box.pending_direction = None
                    box.next_diverter_dir = None
                    box.pending_tracking_id = None
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
                if box.current_element is not None:
                    current_el = self.elements.get(box.current_element)
                    if current_el and current_el.kind == "belt_stopper":
                        box.x = center_x
                        box.y = center_y

    def call_scan_endpoint(self, payload: Dict) -> Tuple[int, Dict]:
        req = urllib.request.Request(
            self.settings["scan_endpoint"],
            method="POST",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "APPLICATION/JSON; charset=utf-8",
                "Accept": "application/json",
            },
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

    def run_reinduction_cycle(self, cell: Tuple[int, int], element: Element) -> None:
        if element.kind != "belt_input" or not (element.related_scan or "").strip():
            return
        if self.occupants.get(cell):
            return
        try:
            box_id = self.id_provider.get_reinduction_box_id(element.related_scan.strip())
        except Exception as exc:  # noqa: BLE001
            self.logger.exception("Oracle fetch failed for reinduction cell=%s related_scan=%s", cell, element.related_scan)
            self.on_error(element, f"Error consultando Oracle: {exc}")
            return
        if not box_id:
            return

        existing = self.boxes.get(str(box_id))
        if existing:
            self.move_box_to_cell(existing, cell, element)
            self.on_log(f"Reinducción {element.related_scan}: reubica caja {box_id}")
            return

        self.spawn_box(cell, element, str(box_id))
        self.on_log(f"Reinducción {element.related_scan}: crea caja {box_id}")

    def move_box_to_cell(self, box: Box, cell: Tuple[int, int], element: Element) -> None:
        if box.current_element in self.occupants and box.box_id in self.occupants[box.current_element]:
            self.occupants[box.current_element].remove(box.box_id)
        if box.current_element in self.elements:
            source_el = self.elements[box.current_element]
            if box.box_id in source_el.fifo:
                source_el.fifo.remove(box.box_id)

        cx, cy = self.cell_center(cell)
        box.x = cx
        box.y = cy
        box.current_cell = cell
        box.current_element = cell
        box.direction = DIRS.get(element.rotation, (1, 0))
        box.next_diverter_dir = None
        box.pending_direction = None
        box.pending_turn_cell = None
        box.pending_tracking_id = None
        self.occupants.setdefault(cell, deque()).append(box.box_id)
        element.fifo.append(box.box_id)

    def update(self, dt: float, is_running: bool) -> None:
        if not is_running:
            return

        for cell, el in self.elements.items():
            if el.kind in {"induction", "belt_input"}:
                el.spawn_timer += dt
                if el.spawn_timer >= self.settings["induction_poll_interval"]:
                    el.spawn_timer = 0.0
                    if el.kind == "induction":
                        self.run_induction_cycle(cell, el)
                    else:
                        self.run_reinduction_cycle(cell, el)

        for box in list(self.boxes.values()):
            self.try_move_box(box, dt)
            if abs(box.x) > CELL_SIZE * 200 or abs(box.y) > CELL_SIZE * 200:
                if box.current_element in self.occupants and box.box_id in self.occupants[box.current_element]:
                    self.occupants[box.current_element].remove(box.box_id)
                if box.current_element in self.elements:
                    element = self.elements[box.current_element]
                    if box.box_id in element.fifo:
                        element.fifo.remove(box.box_id)
                self.boxes.pop(box.box_id, None)
