# ── Domain Models & Data Structures ────────────────────────────────────
class TodoItem:
    id: int
    completed: bool

    def __init__(self, id: int):
        self.id = id
        self.completed = False

    def mark_done(self) -> None:
        self.completed = True

    def is_completed(self) -> bool:
        return self.completed

class Counter:
    count: int

    def __init__(self, start: int):
        self.count = start

    def increment(self) -> None:
        self.count = self.count + 1

    def get_value(self) -> int:
        return self.count
