from dataclasses import dataclass, field


@dataclass
class DanceResult:
    event_id: int
    event_name: str
    round_id: int
    round_name: str
    dance_id: int
    dance_name: str
    session_id: int
    heat_number: int
    time: str
    competitors: list[str] = field(default_factory=list)
    partners: dict[str, str] = field(default_factory=dict)
    placements: dict[str, int] = field(default_factory=dict)

    @property
    def sort_key(self) -> tuple:
        return (self.session_id, self.heat_number, self.time)

    def is_contested(self) -> bool:
        return len(self.placements) >= 2
