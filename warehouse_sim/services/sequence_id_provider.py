class SequenceIdProvider:
    """Generador local de idCaja y trackingId para entornos sin BBDD."""

    def __init__(self, box_seed: int = 1000000000, tracking_seed: int = 250) -> None:
        self._box_seq = box_seed
        self._tracking_seq = tracking_seed

    def get_next_box_id(self) -> str:
        self._box_seq += 1
        return str(self._box_seq)

    def get_next_tracking_id(self) -> int:
        self._tracking_seq += 1
        return self._tracking_seq

    def get_reinduction_box_id(self, related_scan: str):
        return None
