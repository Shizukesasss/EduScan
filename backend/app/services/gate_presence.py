"""Record once per camera visit instead of toggling attendance while standing still."""
import threading
import time


class GatePresence:
    def __init__(self, absence_seconds: float = 8.0, min_absence_observations: int = 2):
        self.absence_seconds = absence_seconds
        self.min_absence_observations = min_absence_observations
        self.lock = threading.RLock()
        self._states = {}

    def observe(self, station_id: str, person_ids: set[int], now: float | None = None,
                count_absence: bool = True):
        now = time.monotonic() if now is None else now
        with self.lock:
            for key, state in list(self._states.items()):
                if now - state['last_seen'] > 300:
                    del self._states[key]
                    continue
                if key[0] != station_id:
                    continue
                if key[1] in person_ids:
                    if (state['absent_since'] is not None
                            and state['missed_observations'] >= self.min_absence_observations
                            and now - state['absent_since'] >= self.absence_seconds):
                        state['recorded'] = False
                    state['last_seen'] = now
                    state['absent_since'] = None
                    state['missed_observations'] = 0
                elif count_absence:
                    if state['absent_since'] is None:
                        state['absent_since'] = now
                    state['missed_observations'] += 1
            for person_id in person_ids:
                self._states.setdefault((station_id, person_id), {'last_seen': now, 'absent_since': None,
                                                                  'missed_observations': 0, 'recorded': False})

    def already_recorded(self, station_id: str, person_id: int) -> bool:
        with self.lock:
            return self._states.get((station_id, person_id), {}).get('recorded', False)

    def current_visits(self, station_id: str) -> set[int]:
        now = time.monotonic()
        with self.lock:
            return {key[1] for key, state in self._states.items() if key[0] == station_id
                    and state['recorded'] and state['absent_since'] is None and now - state['last_seen'] < 5}

    def mark_recorded(self, station_id: str, person_id: int):
        with self.lock:
            self._states[(station_id, person_id)]['recorded'] = True

    def clear(self):
        with self.lock:
            self._states.clear()

    def forget_person(self, person_id: int):
        with self.lock:
            for key in list(self._states):
                if key[1] == person_id:
                    del self._states[key]


gate_presence = GatePresence()
