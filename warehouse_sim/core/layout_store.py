import json
from pathlib import Path
from typing import Dict, Tuple

from core.models import Element


class LayoutStore:
    def __init__(self, layout_path: Path) -> None:
        self.layout_path = layout_path

    def save(self, camera_x: float, camera_y: float, zoom: float, elements: Dict[Tuple[int, int], Element]) -> None:
        data = {
            "camera": {"x": camera_x, "y": camera_y, "zoom": zoom},
            "elements": [
                {"cell": [x, y], "kind": e.kind, "rotation": e.rotation, "capacity": e.capacity, "tag": e.tag}
                for (x, y), e in elements.items()
            ],
        }
        with self.layout_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def load(self) -> Dict:
        return json.loads(self.layout_path.read_text(encoding="utf-8"))

    def exists(self) -> bool:
        return self.layout_path.exists()
