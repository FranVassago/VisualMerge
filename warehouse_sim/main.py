import json
import math
import configparser
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pygame

CELL_SIZE = 124
WINDOW_W, WINDOW_H = 1400, 900
BG_COLOR = (8, 8, 10)
GRID_COLOR = (65, 65, 70)
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


@dataclass
class Box:
    box_id: int
    x: float
    y: float
    direction: Tuple[int, int]
    current_cell: Tuple[int, int]
    current_element: Optional[Tuple[int, int]]
    next_diverter_dir: Optional[Tuple[int, int]] = None
    pending_direction: Optional[Tuple[int, int]] = None
    pending_turn_cell: Optional[Tuple[int, int]] = None


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
        self.boxes: Dict[int, Box] = {}
        self.occupants: Dict[Tuple[int, int], deque] = {}
        self.logs: deque = deque(maxlen=8)
        self.next_box_id = 1

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
            "spawn_interval": 1.8,
            "grid_gray": 65,
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

    def log(self, message: str) -> None:
        self.logs.appendleft(message)

    def load_config(self) -> None:
        if not CONFIG_PATH.exists():
            self.save_config()
            return
        cfg = configparser.ConfigParser()
        cfg.read(CONFIG_PATH)
        if "sim" in cfg:
            self.settings["sim_speed_cells"] = cfg.getfloat("sim", "sim_speed_cells", fallback=self.settings["sim_speed_cells"])
            self.settings["spawn_interval"] = cfg.getfloat("sim", "spawn_interval", fallback=self.settings["spawn_interval"])
            self.settings["grid_gray"] = cfg.getint("sim", "grid_gray", fallback=self.settings["grid_gray"])

    def save_config(self) -> None:
        cfg = configparser.ConfigParser()
        cfg["sim"] = {
            "sim_speed_cells": str(self.settings["sim_speed_cells"]),
            "spawn_interval": str(self.settings["spawn_interval"]),
            "grid_gray": str(int(self.settings["grid_gray"])),
        }
        with CONFIG_PATH.open("w", encoding="utf-8") as f:
            cfg.write(f)
        self.log("Configuración guardada")

    def world_to_screen(self, wx: float, wy: float) -> Tuple[int, int]:
        sx = int((wx - self.camera_x) * self.zoom)
        sy = int((wy - self.camera_y) * self.zoom)
        return sx, sy

    def screen_to_world(self, sx: int, sy: int) -> Tuple[float, float]:
        wx = sx / self.zoom + self.camera_x
        wy = sy / self.zoom + self.camera_y
        return wx, wy

    def world_to_cell(self, wx: float, wy: float) -> Tuple[int, int]:
        return math.floor(wx / CELL_SIZE), math.floor(wy / CELL_SIZE)

    def cell_center(self, cell: Tuple[int, int]) -> Tuple[float, float]:
        return (cell[0] * CELL_SIZE + CELL_SIZE / 2, cell[1] * CELL_SIZE + CELL_SIZE / 2)

    def zoom_with_center_anchor(self, factor: float, anchor: Optional[Tuple[int, int]] = None) -> None:
        if anchor is None:
            anchor = (WINDOW_W // 2, WINDOW_H // 2)

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
        if 10 <= x <= 300 and 10 <= y <= 210 and self.show_config:
            return True
        if WINDOW_W // 2 - 120 <= x <= WINDOW_W // 2 + 200 and 10 <= y <= 54:
            return True
        return False

    def element_capacity(self, element: Element) -> int:
        if element.kind == "induction":
            return 4
        return element.capacity

    def spawn_box(self, cell: Tuple[int, int], element: Element) -> None:
        if len(self.occupants.get(cell, deque())) >= self.element_capacity(element):
            return
        cx, cy = self.cell_center(cell)
        direction = DIRS.get(element.rotation, (1, 0))
        box = Box(
            box_id=self.next_box_id,
            x=cx,
            y=cy,
            direction=direction,
            current_cell=cell,
            current_element=cell,
        )
        self.next_box_id += 1
        self.boxes[box.box_id] = box
        self.occupants.setdefault(cell, deque()).append(box.box_id)
        element.fifo.append(box.box_id)
        self.log(f"Caja {box.box_id} aparece en inducción {cell}")

    def element_direction(self, cell: Tuple[int, int], element: Element, box: Box) -> Tuple[int, int]:
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
        new_x = box.x + dx * speed * dt
        new_y = box.y + dy * speed * dt

        cur_cell = self.world_to_cell(box.x, box.y)
        next_cell = self.world_to_cell(new_x, new_y)

        if next_cell != cur_cell:
            target_el = self.elements.get(next_cell)
            if target_el is not None:
                occ = self.occupants.setdefault(next_cell, deque())
                if len(occ) >= self.element_capacity(target_el):
                    if dx > 0:
                        box.x = next_cell[0] * CELL_SIZE - 1
                    elif dx < 0:
                        box.x = (next_cell[0] + 1) * CELL_SIZE + 1
                    if dy > 0:
                        box.y = next_cell[1] * CELL_SIZE - 1
                    elif dy < 0:
                        box.y = (next_cell[1] + 1) * CELL_SIZE + 1
                    return

            old_element_cell = box.current_element
            box.x = new_x
            box.y = new_y
            box.current_cell = next_cell

            if old_element_cell != next_cell:
                if old_element_cell is not None and old_element_cell in self.occupants:
                    if box.box_id in self.occupants[old_element_cell]:
                        self.occupants[old_element_cell].remove(box.box_id)
                    old_el = self.elements.get(old_element_cell)
                    if old_el is not None and box.box_id in old_el.fifo:
                        old_el.fifo.remove(box.box_id)
                    self.log(f"Caja {box.box_id} sale de {old_element_cell}")

                if target_el is not None:
                    self.occupants.setdefault(next_cell, deque()).append(box.box_id)
                    target_el.fifo.append(box.box_id)
                    box.current_element = next_cell
                    self.log(f"Caja {box.box_id} entra en {target_el.kind} {next_cell}")
                    box.pending_turn_cell = next_cell
                    box.pending_direction = self.element_direction(next_cell, target_el, box)
                    if target_el.kind != "diverter":
                        box.next_diverter_dir = None
                else:
                    box.current_element = None
                    box.pending_turn_cell = None
                    box.pending_direction = None
        else:
            box.x = new_x
            box.y = new_y

        if box.pending_turn_cell is not None and box.pending_direction is not None:
            center_x, center_y = self.cell_center(box.pending_turn_cell)
            dir_x, dir_y = box.direction
            crossed_center = False
            if dir_x > 0:
                crossed_center = box.x >= center_x
            elif dir_x < 0:
                crossed_center = box.x <= center_x
            elif dir_y > 0:
                crossed_center = box.y >= center_y
            elif dir_y < 0:
                crossed_center = box.y <= center_y

            if crossed_center:
                box.direction = box.pending_direction
                box.pending_direction = None
                box.pending_turn_cell = None

    def update_simulation(self, dt: float) -> None:
        if not self.is_running:
            return

        for cell, el in self.elements.items():
            if el.kind == "induction":
                el.spawn_timer += dt
                if el.spawn_timer >= self.settings["spawn_interval"]:
                    el.spawn_timer = 0.0
                    self.spawn_box(cell, el)

        for box in list(self.boxes.values()):
            self.try_move_box(box, dt)

            bx, by = box.x, box.y
            if abs(bx) > CELL_SIZE * 200 or abs(by) > CELL_SIZE * 200:
                if box.current_element in self.occupants and box.box_id in self.occupants[box.current_element]:
                    self.occupants[box.current_element].remove(box.box_id)
                self.boxes.pop(box.box_id, None)

    def save_layout(self) -> None:
        data = {
            "camera": {"x": self.camera_x, "y": self.camera_y, "zoom": self.zoom},
            "elements": [
                {"cell": [x, y], "kind": e.kind, "rotation": e.rotation, "capacity": e.capacity}
                for (x, y), e in self.elements.items()
            ],
        }
        with LAYOUT_PATH.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        self.log(f"Layout guardado en {LAYOUT_PATH.name}")

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
            kind = item["kind"]
            rot = int(item.get("rotation", 0)) % 360
            cap = int(item.get("capacity", 1))
            self.elements[cell] = Element(kind=kind, rotation=rot, capacity=cap)
        self.log(f"Layout cargado ({len(self.elements)} elementos)")

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
            p1 = self.world_to_screen(x, sy)
            p2 = self.world_to_screen(x, ey)
            pygame.draw.line(self.screen, color, p1, p2, 1)
        for y in range(int(sy), int(ey) + 1, CELL_SIZE):
            p1 = self.world_to_screen(sx, y)
            p2 = self.world_to_screen(ex, y)
            pygame.draw.line(self.screen, color, p1, p2, 1)

    def draw_elements(self) -> None:
        for cell, element in self.elements.items():
            wx = cell[0] * CELL_SIZE
            wy = cell[1] * CELL_SIZE
            sx, sy = self.world_to_screen(wx, wy)
            size = int(CELL_SIZE * self.zoom)
            if size <= 2:
                continue
            icon = self.draw_icon(element.kind, element.rotation)
            icon = pygame.transform.smoothscale(icon, (size, size))
            self.screen.blit(icon, (sx, sy))

            if cell in self.selected_cells:
                pygame.draw.rect(self.screen, YELLOW, (sx, sy, size, size), 2)

    def draw_boxes(self) -> None:
        box_size = max(6, int(110 * self.zoom))
        for box in self.boxes.values():
            sx, sy = self.world_to_screen(box.x, box.y)
            rect = pygame.Rect(0, 0, box_size, box_size)
            rect.center = (sx, sy)
            pygame.draw.rect(self.screen, BLUE, rect)
            tid = self.small_font.render(str(box.box_id), True, (20, 20, 20))
            rect = tid.get_rect(center=(sx, sy))
            self.screen.blit(tid, rect)

    def draw_ui(self) -> None:
        # Top controls
        panel = pygame.Rect(WINDOW_W // 2 - 140, 10, 280, 44)
        pygame.draw.rect(self.screen, (30, 30, 36), panel, border_radius=8)
        pygame.draw.rect(self.screen, (95, 95, 105), panel, 1, border_radius=8)

        play_label = "Pause" if self.is_running else "Play"
        play_rect = pygame.Rect(WINDOW_W // 2 - 120, 16, 92, 32)
        stop_rect = pygame.Rect(WINDOW_W // 2 - 18, 16, 72, 32)
        conf_rect = pygame.Rect(WINDOW_W // 2 + 64, 16, 60, 32)

        for rect, label in [(play_rect, play_label), (stop_rect, "Stop"), (conf_rect, "⚙")]:
            pygame.draw.rect(self.screen, (55, 55, 66), rect, border_radius=6)
            pygame.draw.rect(self.screen, (100, 100, 112), rect, 1, border_radius=6)
            txt = self.font.render(label, True, WHITE)
            self.screen.blit(txt, txt.get_rect(center=rect.center))

        # bottom toolbar
        bar = pygame.Rect(0, WINDOW_H - 78, WINDOW_W, 78)
        pygame.draw.rect(self.screen, (20, 20, 24), bar)
        pygame.draw.line(self.screen, (80, 80, 90), (0, WINDOW_H - 78), (WINDOW_W, WINDOW_H - 78), 1)

        x = 16
        y = WINDOW_H - 66
        for key, label in self.toolbar_buttons:
            rect = pygame.Rect(x, y, 150, 48)
            active = (self.place_kind == key and self.mode == "placing") or (key == "eraser" and self.mode == "eraser")
            color = (74, 95, 125) if active else (52, 52, 62)
            pygame.draw.rect(self.screen, color, rect, border_radius=8)
            pygame.draw.rect(self.screen, (108, 108, 120), rect, 1, border_radius=8)
            txt = self.small_font.render(label, True, WHITE)
            self.screen.blit(txt, txt.get_rect(center=rect.center))
            x += 160

        if self.mode == "placing" and self.place_kind:
            msg = f"Instanciando {self.place_kind}. ESC cancela | Click derecho rota"
            line = self.small_font.render(msg, True, WHITE)
            self.screen.blit(line, (16, WINDOW_H - 96))
        elif self.mode == "eraser":
            line = self.small_font.render("Modo borrador. Arrastra click izq para eliminar. ESC para salir.", True, WHITE)
            self.screen.blit(line, (16, WINDOW_H - 96))

        if self.show_config:
            cpanel = pygame.Rect(10, 10, 300, 210)
            pygame.draw.rect(self.screen, (25, 25, 30), cpanel, border_radius=8)
            pygame.draw.rect(self.screen, (100, 100, 110), cpanel, 1, border_radius=8)
            title = self.font.render("Configuración", True, WHITE)
            self.screen.blit(title, (24, 20))
            self.draw_config_row("Velocidad", self.settings["sim_speed_cells"], 56)
            self.draw_config_row("Spawn", self.settings["spawn_interval"], 106)
            self.draw_config_row("Grid gray", self.settings["grid_gray"], 156)

        log_y = 60
        for item in list(self.logs)[:7]:
            txt = self.small_font.render(item, True, (180, 180, 180))
            self.screen.blit(txt, (WINDOW_W - 450, log_y))
            log_y += 18

    def draw_config_row(self, label: str, value: float, y: int) -> None:
        text = self.small_font.render(f"{label}: {value:.2f}" if isinstance(value, float) else f"{label}: {value}", True, WHITE)
        self.screen.blit(text, (24, y))
        minus = pygame.Rect(210, y - 4, 34, 26)
        plus = pygame.Rect(252, y - 4, 34, 26)
        for rect, char in [(minus, "-"), (plus, "+")]:
            pygame.draw.rect(self.screen, (60, 60, 70), rect, border_radius=5)
            pygame.draw.rect(self.screen, (98, 98, 108), rect, 1, border_radius=5)
            t = self.font.render(char, True, WHITE)
            self.screen.blit(t, t.get_rect(center=rect.center))

    def draw_selection_rect(self) -> None:
        if self.select_drag:
            x1, y1 = self.select_start
            x2, y2 = self.select_end
            rect = pygame.Rect(min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))
            pygame.draw.rect(self.screen, (130, 170, 230), rect, 1)

    def draw_ghost(self) -> None:
        if self.mode != "placing" or not self.place_kind or self.place_kind in {"save", "load", "eraser"}:
            return
        mx, my = pygame.mouse.get_pos()
        wx, wy = self.screen_to_world(mx, my)
        cell = self.world_to_cell(wx, wy)
        world_x = cell[0] * CELL_SIZE
        world_y = cell[1] * CELL_SIZE
        sx, sy = self.world_to_screen(world_x, world_y)
        size = int(CELL_SIZE * self.zoom)
        if size <= 2:
            return
        icon = self.draw_icon(self.place_kind, self.place_rotation, alpha=140)
        icon = pygame.transform.smoothscale(icon, (size, size))
        self.screen.blit(icon, (sx, sy))

    def clear_boxes(self) -> None:
        self.boxes.clear()
        self.occupants.clear()
        for e in self.elements.values():
            e.fifo.clear()
        self.log("Stop: cajas eliminadas")

    def handle_toolbar_click(self, pos: Tuple[int, int]) -> bool:
        x = 16
        y = WINDOW_H - 66
        for key, _label in self.toolbar_buttons:
            rect = pygame.Rect(x, y, 150, 48)
            if rect.collidepoint(pos):
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
        x, y = pos
        rows = [
            (56, "sim_speed_cells", 0.1),
            (106, "spawn_interval", 0.1),
            (156, "grid_gray", 3),
        ]
        for ry, key, step in rows:
            minus = pygame.Rect(210, ry - 4, 34, 26)
            plus = pygame.Rect(252, ry - 4, 34, 26)
            if minus.collidepoint((x, y)):
                self.settings[key] = max(0.1 if key != "grid_gray" else 20, self.settings[key] - step)
                if key == "grid_gray":
                    self.settings[key] = int(self.settings[key])
                self.save_config()
                return True
            if plus.collidepoint((x, y)):
                limit = 220 if key == "grid_gray" else 8.0
                self.settings[key] = min(limit, self.settings[key] + step)
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
                wx, wy = self.screen_to_world(*pos)
                cell = self.world_to_cell(wx, wy)
                self.elements[cell] = Element(kind=self.place_kind, rotation=self.place_rotation)
            elif event.button == 3:
                self.place_rotation = (self.place_rotation + 90) % 360
            return

        if self.mode == "eraser":
            if event.button == 1:
                self.eraser_drag = True
                wx, wy = self.screen_to_world(*pos)
                cell = self.world_to_cell(wx, wy)
                self.elements.pop(cell, None)
            return

        if self.mode == "idle":
            if event.button == 1 and not self.click_over_ui(pos):
                self.select_drag = True
                self.select_start = pos
                self.select_end = pos
            elif event.button == 3 and not self.click_over_ui(pos):
                self.pan_drag = True
                self.pan_prev = pos

    def handle_mouse_up(self, event: pygame.event.Event) -> None:
        if event.button == 1:
            if self.select_drag and self.mode == "idle":
                x1, y1 = self.select_start
                x2, y2 = self.select_end
                rect = pygame.Rect(min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))
                self.selected_cells.clear()
                if rect.w < 5 and rect.h < 5:
                    wx, wy = self.screen_to_world(*event.pos)
                    cell = self.world_to_cell(wx, wy)
                    if cell in self.elements:
                        self.selected_cells.add(cell)
                else:
                    for cell in self.elements:
                        wx = cell[0] * CELL_SIZE
                        wy = cell[1] * CELL_SIZE
                        sx, sy = self.world_to_screen(wx, wy)
                        size = int(CELL_SIZE * self.zoom)
                        erec = pygame.Rect(sx, sy, size, size)
                        if rect.colliderect(erec):
                            self.selected_cells.add(cell)
            self.select_drag = False
            self.eraser_drag = False

        if event.button == 3:
            self.pan_drag = False

    def handle_mouse_motion(self, event: pygame.event.Event) -> None:
        if self.pan_drag:
            dx = event.pos[0] - self.pan_prev[0]
            dy = event.pos[1] - self.pan_prev[1]
            self.camera_x -= dx / self.zoom
            self.camera_y -= dy / self.zoom
            self.pan_prev = event.pos

        if self.select_drag:
            self.select_end = event.pos

        if self.mode == "eraser" and self.eraser_drag:
            wx, wy = self.screen_to_world(*event.pos)
            cell = self.world_to_cell(wx, wy)
            self.elements.pop(cell, None)

    def handle_events(self) -> bool:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.mode = "idle"
                    self.place_kind = None
                    self.eraser_drag = False
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
