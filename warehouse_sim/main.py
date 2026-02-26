import configparser
import json
import math
import urllib.error
import urllib.request
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, Tuple

import pygame

CELL_SIZE = 124
WINDOW_W, WINDOW_H = 1400, 900
BG_COLOR = (8, 8, 10)
WHITE = (235, 235, 235)
GREEN = (122, 199, 76)
YELLOW = (235, 196, 64)
RED = (218, 88, 88)
BLUE = (93, 164, 222)

CONFIG_PATH = Path(__file__).parent / "config.ini"
LAYOUT_PATH = Path(__file__).parent / "layout.json"

DIRS = {
    0: (1, 0),
    90: (0, 1),
    180: (-1, 0),
    270: (0, -1),
}


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


class WarehouseSim:
    def __init__(self) -> None:
        pygame.init()
        self.screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
        pygame.display.set_caption("Warehouse Simulator Prototype")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("consolas", 18)
        self.small_font = pygame.font.SysFont("consolas", 14)

        self.camera_x = -WINDOW_W // 2
        self.camera_y = -WINDOW_H // 2
        self.zoom = 0.45

        self.elements: Dict[Tuple[int, int], Element] = {}
        self.boxes: Dict[str, Box] = {}
        self.occupants: Dict[Tuple[int, int], deque] = {}
        self.logs: deque = deque(maxlen=8)
        self.error_message: Optional[str] = None
        self.mock_box_seq = 1000000000
        self.mock_tracking_seq = 250

        self.mode = "idle"
        self.place_kind: Optional[str] = None
        self.place_rotation = 0
        self.selected_cells: set[Tuple[int, int]] = set()

        self.is_running = False
        self.select_drag = False
        self.select_start = (0, 0)
        self.select_end = (0, 0)
        self.pan_drag = False
        self.pan_prev = (0, 0)
        self.eraser_drag = False

        self.show_config = False
        self.settings = {
            "sim_speed_cells": 1.7,
            "grid_gray": 65,
            "induction_poll_interval": 5.0,
            "scan_endpoint": "http://vpn.v10.solutions:18080/ords/merza/merza/scan",
            "scanner_default_tag": "SCAN01",
        }
        self.load_config()

        self.toolbar_buttons = [
            ("induction", "Inducción"),
            ("belt", "Cinta"),
            ("belt_input", "Cinta+Input"),
            ("diverter", "Diverter"),
            ("eraser", "Borrador"),
            ("save", "Guardar"),
            ("load", "Cargar"),
        ]

        self.context_menu: Optional[ContextMenu] = None
        self.tag_input_value = ""

    def log(self, message: str) -> None:
        self.logs.appendleft(message)

    def fail_with_error(self, element: Element, message: str) -> None:
        element.has_error = True
        self.is_running = False
        self.error_message = message[:150]
        self.log(f"ERROR: {self.error_message}")

    def load_config(self) -> None:
        if not CONFIG_PATH.exists():
            self.save_config()
            return
        cfg = configparser.ConfigParser()
        cfg.read(CONFIG_PATH)
        if "sim" in cfg:
            self.settings["sim_speed_cells"] = cfg.getfloat("sim", "sim_speed_cells", fallback=self.settings["sim_speed_cells"])
            self.settings["grid_gray"] = cfg.getint("sim", "grid_gray", fallback=self.settings["grid_gray"])
            self.settings["induction_poll_interval"] = cfg.getfloat(
                "sim", "induction_poll_interval", fallback=self.settings["induction_poll_interval"]
            )
            self.settings["scan_endpoint"] = cfg.get("sim", "scan_endpoint", fallback=self.settings["scan_endpoint"])
            self.settings["scanner_default_tag"] = cfg.get(
                "sim", "scanner_default_tag", fallback=self.settings["scanner_default_tag"]
            )

    def save_config(self) -> None:
        cfg = configparser.ConfigParser()
        cfg["sim"] = {
            "sim_speed_cells": str(self.settings["sim_speed_cells"]),
            "grid_gray": str(int(self.settings["grid_gray"])),
            "induction_poll_interval": str(self.settings["induction_poll_interval"]),
            "scan_endpoint": str(self.settings["scan_endpoint"]),
            "scanner_default_tag": str(self.settings["scanner_default_tag"]),
        }
        with CONFIG_PATH.open("w", encoding="utf-8") as f:
            cfg.write(f)

    def world_to_screen(self, wx: float, wy: float) -> Tuple[int, int]:
        return int((wx - self.camera_x) * self.zoom), int((wy - self.camera_y) * self.zoom)

    def screen_to_world(self, sx: int, sy: int) -> Tuple[float, float]:
        return sx / self.zoom + self.camera_x, sy / self.zoom + self.camera_y

    def world_to_cell(self, wx: float, wy: float) -> Tuple[int, int]:
        return math.floor(wx / CELL_SIZE), math.floor(wy / CELL_SIZE)

    def cell_center(self, cell: Tuple[int, int]) -> Tuple[float, float]:
        return (cell[0] * CELL_SIZE + CELL_SIZE / 2, cell[1] * CELL_SIZE + CELL_SIZE / 2)

    def zoom_with_center_anchor(self, factor: float, anchor: Optional[Tuple[int, int]] = None) -> None:
        anchor = anchor or (WINDOW_W // 2, WINDOW_H // 2)
        old_zoom = self.zoom
        old_wx, old_wy = self.screen_to_world(*anchor)
        self.zoom = max(0.2, min(2.4, old_zoom * factor))
        new_wx, new_wy = self.screen_to_world(*anchor)
        self.camera_x += old_wx - new_wx
        self.camera_y += old_wy - new_wy

    def click_over_ui(self, pos: Tuple[int, int]) -> bool:
        x, y = pos
        if y > WINDOW_H - 78:
            return True
        if 10 <= x <= 320 and 10 <= y <= 220 and self.show_config:
            return True
        if WINDOW_W // 2 - 120 <= x <= WINDOW_W // 2 + 200 and 10 <= y <= 54:
            return True
        if self.context_menu and self.context_menu_rect().collidepoint(pos):
            return True
        return False

    def supports_context_menu(self, element: Element) -> bool:
        return element.kind in {"induction", "belt_input"}

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
        self.log(f"Caja {box.box_id} liberada por inducción {cell}")

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
            crossed_center = (dir_x > 0 and box.x >= center_x) or (dir_x < 0 and box.x <= center_x) or (dir_y > 0 and box.y >= center_y) or (dir_y < 0 and box.y <= center_y)
            if crossed_center:
                box.direction = box.pending_direction
                box.pending_direction = None
                box.pending_turn_cell = None

    def get_next_available_box_id(self) -> str:
        self.mock_box_seq += 1
        return str(self.mock_box_seq)

    def get_next_tracking_id(self) -> int:
        self.mock_tracking_seq += 1
        return self.mock_tracking_seq

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
            box_id = self.get_next_available_box_id()
            tracking_id = self.get_next_tracking_id()
            payload = {"scannerId": element.tag, "barcode": box_id, "trackingId": tracking_id}
            status, body = self.call_scan_endpoint(payload)
            if status >= 400:
                self.fail_with_error(element, str(body.get("message", "Sistema no disponible.")))
                return
            decision = int(body.get("decision", 0))
            if decision == 0:
                element.held_box_id = box_id
                element.held_tracking_id = tracking_id
                element.held_decision = decision
                self.log(f"Inducción {element.tag}: caja {box_id} retenida ({tracking_id})")
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
                self.fail_with_error(element, str(body.get("message", "Sistema no disponible.")))
                return
            decision = int(body.get("decision", 0))
            if decision == 99:
                self.spawn_box(cell, element, element.held_box_id)
                self.log(f"Inducción {element.tag}: libera caja en espera {element.held_box_id}")
                element.held_box_id = None
                element.held_tracking_id = None
                element.held_decision = None

    def update_simulation(self, dt: float) -> None:
        if not self.is_running:
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

    def save_layout(self) -> None:
        data = {
            "camera": {"x": self.camera_x, "y": self.camera_y, "zoom": self.zoom},
            "elements": [
                {"cell": [x, y], "kind": e.kind, "rotation": e.rotation, "capacity": e.capacity, "tag": e.tag}
                for (x, y), e in self.elements.items()
            ],
        }
        with LAYOUT_PATH.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        self.log("Layout guardado")

    def load_layout(self) -> None:
        if not LAYOUT_PATH.exists():
            self.log("No existe layout.json")
            return
        data = json.loads(LAYOUT_PATH.read_text(encoding="utf-8"))
        self.elements.clear()
        self.boxes.clear()
        self.occupants.clear()
        cam = data.get("camera", {})
        self.camera_x = cam.get("x", self.camera_x)
        self.camera_y = cam.get("y", self.camera_y)
        self.zoom = cam.get("zoom", self.zoom)

        for item in data.get("elements", []):
            cell = tuple(item["cell"])
            self.elements[cell] = Element(
                kind=item["kind"],
                rotation=int(item.get("rotation", 0)) % 360,
                capacity=int(item.get("capacity", 1)),
                tag=item.get("tag"),
            )

    def draw_icon(self, kind: str, rotation: int, alpha: int = 255) -> pygame.Surface:
        surf = pygame.Surface((CELL_SIZE, CELL_SIZE), pygame.SRCALPHA)
        a = alpha
        if kind in ("induction", "diverter"):
            pygame.draw.rect(surf, (WHITE[0], WHITE[1], WHITE[2], a), pygame.Rect(6, 6, CELL_SIZE - 12, CELL_SIZE - 12), 8)
        if kind == "induction":
            pts = [(62, 24), (74, 56), (106, 62), (74, 68), (62, 100), (50, 68), (18, 62), (50, 56)]
            pygame.draw.polygon(surf, (WHITE[0], WHITE[1], WHITE[2], a), pts, 4)
        elif kind in ("belt", "belt_input"):
            pygame.draw.line(surf, (WHITE[0], WHITE[1], WHITE[2], a), (12, 14), (112, 14), 7)
            pygame.draw.line(surf, (WHITE[0], WHITE[1], WHITE[2], a), (12, 110), (112, 110), 7)
            pygame.draw.lines(surf, (WHITE[0], WHITE[1], WHITE[2], a), False, [(30, 30), (74, 62), (30, 94)], 6)
            if kind == "belt_input":
                pygame.draw.circle(surf, (GREEN[0], GREEN[1], GREEN[2], a), (98, 30), 11)
        elif kind == "diverter":
            pygame.draw.polygon(surf, (WHITE[0], WHITE[1], WHITE[2], a), [(62, 20), (78, 40), (46, 40)], 4)
            pygame.draw.polygon(surf, (WHITE[0], WHITE[1], WHITE[2], a), [(104, 62), (84, 78), (84, 46)], 4)
            pygame.draw.polygon(surf, (WHITE[0], WHITE[1], WHITE[2], a), [(62, 104), (78, 84), (46, 84)], 4)
        if rotation:
            surf = pygame.transform.rotate(surf, -rotation)
        return surf

    def draw_grid(self) -> None:
        gray = int(self.settings["grid_gray"])
        color = (gray, gray, gray)
        world_left, world_top = self.screen_to_world(0, 0)
        world_right, world_bottom = self.screen_to_world(WINDOW_W, WINDOW_H)
        sx = math.floor(world_left / CELL_SIZE) * CELL_SIZE
        ex = math.ceil(world_right / CELL_SIZE) * CELL_SIZE
        sy = math.floor(world_top / CELL_SIZE) * CELL_SIZE
        ey = math.ceil(world_bottom / CELL_SIZE) * CELL_SIZE
        for x in range(int(sx), int(ex) + 1, CELL_SIZE):
            pygame.draw.line(self.screen, color, self.world_to_screen(x, sy), self.world_to_screen(x, ey), 1)
        for y in range(int(sy), int(ey) + 1, CELL_SIZE):
            pygame.draw.line(self.screen, color, self.world_to_screen(sx, y), self.world_to_screen(ex, y), 1)

    def draw_elements(self) -> None:
        for cell, element in self.elements.items():
            sx, sy = self.world_to_screen(cell[0] * CELL_SIZE, cell[1] * CELL_SIZE)
            size = int(CELL_SIZE * self.zoom)
            if size <= 2:
                continue
            icon = pygame.transform.smoothscale(self.draw_icon(element.kind, element.rotation), (size, size))
            self.screen.blit(icon, (sx, sy))
            if element.tag and self.supports_context_menu(element):
                tag_txt = self.small_font.render(element.tag, True, GREEN)
                self.screen.blit(tag_txt, (sx + 6, sy + 4))
            if element.has_error:
                warn = self.font.render("!", True, RED)
                self.screen.blit(warn, (sx + size - 16, sy + 2))
            if cell in self.selected_cells:
                pygame.draw.rect(self.screen, YELLOW, (sx, sy, size, size), 2)

    def draw_boxes(self) -> None:
        box_size = max(6, int(110 * self.zoom))
        for box in self.boxes.values():
            sx, sy = self.world_to_screen(box.x, box.y)
            rect = pygame.Rect(0, 0, box_size, box_size)
            rect.center = (sx, sy)
            pygame.draw.rect(self.screen, BLUE, rect)
            visible = box.box_id[-4:]
            tid = self.small_font.render(visible, True, (20, 20, 20))
            self.screen.blit(tid, tid.get_rect(center=(sx, sy)))

    def draw_ui(self) -> None:
        panel = pygame.Rect(WINDOW_W // 2 - 140, 10, 280, 44)
        pygame.draw.rect(self.screen, (30, 30, 36), panel, border_radius=8)
        pygame.draw.rect(self.screen, (95, 95, 105), panel, 1, border_radius=8)
        play_rect = pygame.Rect(WINDOW_W // 2 - 120, 16, 92, 32)
        stop_rect = pygame.Rect(WINDOW_W // 2 - 18, 16, 72, 32)
        conf_rect = pygame.Rect(WINDOW_W // 2 + 64, 16, 60, 32)
        for rect, label in [(play_rect, "Pause" if self.is_running else "Play"), (stop_rect, "Stop"), (conf_rect, "⚙")]:
            pygame.draw.rect(self.screen, (55, 55, 66), rect, border_radius=6)
            pygame.draw.rect(self.screen, (100, 100, 112), rect, 1, border_radius=6)
            txt = self.font.render(label, True, WHITE)
            self.screen.blit(txt, txt.get_rect(center=rect.center))

        bar = pygame.Rect(0, WINDOW_H - 78, WINDOW_W, 78)
        pygame.draw.rect(self.screen, (20, 20, 24), bar)
        pygame.draw.line(self.screen, (80, 80, 90), (0, WINDOW_H - 78), (WINDOW_W, WINDOW_H - 78), 1)
        x = 16
        for key, label in self.toolbar_buttons:
            rect = pygame.Rect(x, WINDOW_H - 66, 150, 48)
            active = (self.place_kind == key and self.mode == "placing") or (key == "eraser" and self.mode == "eraser")
            pygame.draw.rect(self.screen, (74, 95, 125) if active else (52, 52, 62), rect, border_radius=8)
            pygame.draw.rect(self.screen, (108, 108, 120), rect, 1, border_radius=8)
            txt = self.small_font.render(label, True, WHITE)
            self.screen.blit(txt, txt.get_rect(center=rect.center))
            x += 160

        if self.mode == "placing" and self.place_kind:
            msg = f"Instanciando {self.place_kind}. ESC cancela | Click derecho rota"
            self.screen.blit(self.small_font.render(msg, True, WHITE), (16, WINDOW_H - 96))

        if self.show_config:
            cpanel = pygame.Rect(10, 10, 320, 220)
            pygame.draw.rect(self.screen, (25, 25, 30), cpanel, border_radius=8)
            pygame.draw.rect(self.screen, (100, 100, 110), cpanel, 1, border_radius=8)
            self.screen.blit(self.font.render("Configuración", True, WHITE), (24, 20))
            self.draw_config_row("Velocidad", self.settings["sim_speed_cells"], 56)
            self.draw_config_row("Poll inducción", self.settings["induction_poll_interval"], 106)
            self.draw_config_row("Grid gray", self.settings["grid_gray"], 156)

        if self.error_message:
            err_txt = self.small_font.render(self.error_message, True, RED)
            self.screen.blit(err_txt, (WINDOW_W - 520, 38))

        log_y = 60
        for item in list(self.logs)[:7]:
            self.screen.blit(self.small_font.render(item, True, (180, 180, 180)), (WINDOW_W - 520, log_y))
            log_y += 18

        self.draw_context_menu()

    def draw_config_row(self, label: str, value: float, y: int) -> None:
        text = self.small_font.render(f"{label}: {value:.2f}" if isinstance(value, float) else f"{label}: {value}", True, WHITE)
        self.screen.blit(text, (24, y))
        minus, plus = pygame.Rect(230, y - 4, 34, 26), pygame.Rect(272, y - 4, 34, 26)
        for rect, char in [(minus, "-"), (plus, "+")]:
            pygame.draw.rect(self.screen, (60, 60, 70), rect, border_radius=5)
            pygame.draw.rect(self.screen, (98, 98, 108), rect, 1, border_radius=5)
            self.screen.blit(self.font.render(char, True, WHITE), self.font.render(char, True, WHITE).get_rect(center=rect.center))

    def context_menu_rect(self) -> pygame.Rect:
        if not self.context_menu:
            return pygame.Rect(0, 0, 0, 0)
        x, y = self.context_menu.screen_pos
        return pygame.Rect(x, y, 260, 110)

    def draw_context_menu(self) -> None:
        if not self.context_menu:
            return
        rect = self.context_menu_rect()
        pygame.draw.rect(self.screen, (28, 28, 34), rect, border_radius=6)
        pygame.draw.rect(self.screen, (110, 110, 120), rect, 1, border_radius=6)
        if self.context_menu.menu_type == "element":
            self.screen.blit(self.small_font.render("Tag", True, WHITE), (rect.x + 12, rect.y + 10))
            input_rect = pygame.Rect(rect.x + 12, rect.y + 32, 236, 28)
            pygame.draw.rect(self.screen, (40, 40, 50), input_rect, border_radius=4)
            pygame.draw.rect(self.screen, (140, 140, 155), input_rect, 1, border_radius=4)
            self.screen.blit(self.small_font.render(self.tag_input_value or "(vacío)", True, WHITE), (input_rect.x + 8, input_rect.y + 6))
            self.screen.blit(self.small_font.render("Enter guardar / Backspace borrar", True, (170, 170, 180)), (rect.x + 12, rect.y + 70))
        elif self.context_menu.menu_type == "box":
            self.screen.blit(self.small_font.render("Caja", True, WHITE), (rect.x + 12, rect.y + 10))
            self.screen.blit(self.small_font.render(self.context_menu.box_id or "", True, BLUE), (rect.x + 12, rect.y + 36))

    def draw_selection_rect(self) -> None:
        if self.select_drag:
            x1, y1 = self.select_start
            x2, y2 = self.select_end
            pygame.draw.rect(self.screen, (130, 170, 230), pygame.Rect(min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1)), 1)

    def draw_ghost(self) -> None:
        if self.mode != "placing" or not self.place_kind or self.place_kind in {"save", "load", "eraser"}:
            return
        wx, wy = self.screen_to_world(*pygame.mouse.get_pos())
        cell = self.world_to_cell(wx, wy)
        sx, sy = self.world_to_screen(cell[0] * CELL_SIZE, cell[1] * CELL_SIZE)
        size = int(CELL_SIZE * self.zoom)
        if size <= 2:
            return
        icon = pygame.transform.smoothscale(self.draw_icon(self.place_kind, self.place_rotation, alpha=140), (size, size))
        self.screen.blit(icon, (sx, sy))

    def clear_boxes(self) -> None:
        self.boxes.clear()
        self.occupants.clear()
        self.error_message = None
        for e in self.elements.values():
            e.fifo.clear()
            e.held_box_id = None
            e.held_tracking_id = None
            e.held_decision = None
            e.has_error = False

    def box_at_screen(self, pos: Tuple[int, int]) -> Optional[Box]:
        box_size = max(6, int(110 * self.zoom))
        for box in self.boxes.values():
            sx, sy = self.world_to_screen(box.x, box.y)
            rect = pygame.Rect(0, 0, box_size, box_size)
            rect.center = (sx, sy)
            if rect.collidepoint(pos):
                return box
        return None

    def element_tag_is_unique(self, tag: str, current_cell: Tuple[int, int]) -> bool:
        for cell, element in self.elements.items():
            if cell != current_cell and element.tag and element.tag.lower() == tag.lower():
                return False
        return True

    def save_context_tag(self) -> None:
        if not self.context_menu or self.context_menu.menu_type != "element" or not self.context_menu.cell:
            return
        element = self.elements.get(self.context_menu.cell)
        if not element:
            return
        value = self.tag_input_value.strip()
        if not value:
            element.tag = None
            self.log("Tag eliminado")
            self.context_menu = None
            return
        if not self.element_tag_is_unique(value, self.context_menu.cell):
            self.log("Tag duplicado: debe ser único")
            return
        element.tag = value
        self.log(f"Tag guardado: {value}")
        self.context_menu = None

    def handle_toolbar_click(self, pos: Tuple[int, int]) -> bool:
        x = 16
        for key, _label in self.toolbar_buttons:
            rect = pygame.Rect(x, WINDOW_H - 66, 150, 48)
            if rect.collidepoint(pos):
                self.context_menu = None
                if key in {"induction", "belt", "belt_input", "diverter"}:
                    self.mode = "placing"
                    self.place_kind = key
                    self.place_rotation = 0
                elif key == "eraser":
                    self.mode = "eraser"
                    self.place_kind = None
                elif key == "save":
                    self.save_layout()
                    self.save_config()
                elif key == "load":
                    self.load_layout()
                    self.load_config()
                return True
            x += 160
        return False

    def modify_config(self, pos: Tuple[int, int]) -> bool:
        if not self.show_config:
            return False
        rows = [(56, "sim_speed_cells", 0.1), (106, "induction_poll_interval", 0.5), (156, "grid_gray", 3)]
        x, y = pos
        for ry, key, step in rows:
            minus, plus = pygame.Rect(230, ry - 4, 34, 26), pygame.Rect(272, ry - 4, 34, 26)
            if minus.collidepoint((x, y)):
                self.settings[key] = max(0.1 if key != "grid_gray" else 20, self.settings[key] - step)
                if key == "grid_gray":
                    self.settings[key] = int(self.settings[key])
                self.save_config()
                return True
            if plus.collidepoint((x, y)):
                self.settings[key] = min(220 if key == "grid_gray" else 20.0, self.settings[key] + step)
                if key == "grid_gray":
                    self.settings[key] = int(self.settings[key])
                self.save_config()
                return True
        return False

    def handle_mouse_down(self, event: pygame.event.Event) -> None:
        pos = event.pos
        if self.handle_toolbar_click(pos):
            return
        play_rect = pygame.Rect(WINDOW_W // 2 - 120, 16, 92, 32)
        stop_rect = pygame.Rect(WINDOW_W // 2 - 18, 16, 72, 32)
        conf_rect = pygame.Rect(WINDOW_W // 2 + 64, 16, 60, 32)

        if play_rect.collidepoint(pos):
            self.is_running = not self.is_running
            return
        if stop_rect.collidepoint(pos):
            self.clear_boxes()
            self.is_running = False
            return
        if conf_rect.collidepoint(pos):
            self.show_config = not self.show_config
            return
        if self.modify_config(pos):
            return

        if self.mode == "placing" and self.place_kind:
            if event.button == 1:
                cell = self.world_to_cell(*self.screen_to_world(*pos))
                self.elements[cell] = Element(kind=self.place_kind, rotation=self.place_rotation)
            elif event.button == 3:
                self.place_rotation = (self.place_rotation + 90) % 360
            return

        if self.mode == "eraser" and event.button == 1:
            self.eraser_drag = True
            cell = self.world_to_cell(*self.screen_to_world(*pos))
            self.elements.pop(cell, None)
            return

        if self.mode == "idle":
            if event.button == 3 and not self.click_over_ui(pos):
                box = self.box_at_screen(pos)
                if box:
                    self.context_menu = ContextMenu(menu_type="box", box_id=box.box_id, screen_pos=pos)
                    return
                cell = self.world_to_cell(*self.screen_to_world(*pos))
                element = self.elements.get(cell)
                if element and self.supports_context_menu(element):
                    self.context_menu = ContextMenu(menu_type="element", cell=cell, screen_pos=pos)
                    self.tag_input_value = element.tag or ""
                    return
                self.context_menu = None
                self.pan_drag = True
                self.pan_prev = pos
            elif event.button == 1 and not self.click_over_ui(pos):
                self.context_menu = None
                self.select_drag = True
                self.select_start = pos
                self.select_end = pos

    def handle_mouse_up(self, event: pygame.event.Event) -> None:
        if event.button == 1:
            if self.select_drag and self.mode == "idle":
                x1, y1 = self.select_start
                x2, y2 = self.select_end
                rect = pygame.Rect(min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))
                self.selected_cells.clear()
                if rect.w < 5 and rect.h < 5:
                    cell = self.world_to_cell(*self.screen_to_world(*event.pos))
                    if cell in self.elements:
                        self.selected_cells.add(cell)
                else:
                    for cell in self.elements:
                        sx, sy = self.world_to_screen(cell[0] * CELL_SIZE, cell[1] * CELL_SIZE)
                        size = int(CELL_SIZE * self.zoom)
                        if rect.colliderect(pygame.Rect(sx, sy, size, size)):
                            self.selected_cells.add(cell)
            self.select_drag = False
            self.eraser_drag = False
        if event.button == 3:
            self.pan_drag = False

    def handle_mouse_motion(self, event: pygame.event.Event) -> None:
        if self.pan_drag:
            self.camera_x -= (event.pos[0] - self.pan_prev[0]) / self.zoom
            self.camera_y -= (event.pos[1] - self.pan_prev[1]) / self.zoom
            self.pan_prev = event.pos
        if self.select_drag:
            self.select_end = event.pos
        if self.mode == "eraser" and self.eraser_drag:
            cell = self.world_to_cell(*self.screen_to_world(*event.pos))
            self.elements.pop(cell, None)

    def handle_events(self) -> bool:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN:
                if self.context_menu and self.context_menu.menu_type == "element":
                    if event.key == pygame.K_RETURN:
                        self.save_context_tag()
                        continue
                    if event.key == pygame.K_ESCAPE:
                        self.context_menu = None
                        continue
                    if event.key == pygame.K_BACKSPACE:
                        self.tag_input_value = self.tag_input_value[:-1]
                        continue
                    if event.unicode and event.unicode.isprintable() and len(self.tag_input_value) < 20:
                        self.tag_input_value += event.unicode
                        continue
                if event.key == pygame.K_ESCAPE:
                    self.mode = "idle"
                    self.place_kind = None
                    self.eraser_drag = False
                    self.context_menu = None
                if event.key == pygame.K_s and (event.mod & pygame.KMOD_CTRL):
                    self.save_layout()
                if event.key == pygame.K_o and (event.mod & pygame.KMOD_CTRL):
                    self.load_layout()
            if event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 4:
                    self.zoom_with_center_anchor(1.1)
                elif event.button == 5:
                    self.zoom_with_center_anchor(1 / 1.1)
                else:
                    self.handle_mouse_down(event)
            if event.type == pygame.MOUSEBUTTONUP:
                self.handle_mouse_up(event)
            if event.type == pygame.MOUSEMOTION:
                self.handle_mouse_motion(event)
        return True

    def run(self) -> None:
        running = True
        while running:
            dt = self.clock.tick(60) / 1000.0
            running = self.handle_events()
            self.update_simulation(dt)
            self.screen.fill(BG_COLOR)
            self.draw_grid()
            self.draw_elements()
            self.draw_boxes()
            self.draw_ghost()
            self.draw_selection_rect()
            self.draw_ui()
            pygame.display.flip()
        pygame.quit()


if __name__ == "__main__":
    WarehouseSim().run()
