import json
import threading
import time


# -------------------------
# СЕТЬ ПЕТРИ
# -------------------------
class PetriNet:
    def __init__(self, resources):
        self.lock = threading.Lock()
        self.places = resources.copy()  # маркировка μ

    def fire(self, rid, tid):
        """Попытка захвата ресурса rid потоком tid"""
        with self.lock:
            if self.places[rid] > 0:
                self.places[rid] -= 1
                return True
            return False

    def release(self, rid):
        """Освобождение ресурса rid"""
        with self.lock:
            self.places[rid] += 1

    def snapshot(self):
        """Текущее распределение токенов по ресурсам"""
        with self.lock:
            return self.places.copy()


# -------------------------
# ПОТОК-СТУДЕНТ
# -------------------------
class StudentThread(threading.Thread):
    def __init__(self, sid, name, burst, resources, petri, history):
        super().__init__()
        self.sid = sid
        self.name = name
        self.burst = burst
        self.resources = resources
        self.petri = petri
        self.state = "READY"
        self.history = history

    def run(self):
        # Захват ресурсов
        for r in self.resources:
            while not self.petri.fire(r, self.sid):
                self.state = "W"  # ожидание
                self.record_snapshot()
                time.sleep(0.01)

        # Выполнение лабораторной
        self.state = "R"
        self.record_snapshot()
        time.sleep(self.burst / 1000)

        # Освобождение ресурсов
        for r in self.resources:
            self.petri.release(r)

        self.state = "F"
        self.record_snapshot()

    def record_snapshot(self):
        res_state = self.petri.snapshot()
        self.history.append(
            {
                "time": round(time.time() * 1000),
                "student_id": self.sid,
                "student_name": self.name,
                "student_state": self.state,
                "resources": res_state.copy(),
            }
        )


# -------------------------
# ЗАПУСК СИМУЛЯЦИИ
# -------------------------
def run_simulation(json_str):
    cfg = json.loads(json_str)

    # Проверка NR и NP
    if "NR" not in cfg:
        cfg["NR"] = len(cfg.get("resources", []))
    if "NP" not in cfg:
        cfg["NP"] = len(cfg.get("students", []))

    # Генерация ресурсов
    resources = {}
    for i, r in enumerate(cfg.get("resources", []), start=1):
        resources[i] = r["count"]

    # Инициализация сети Петри
    petri = PetriNet(resources)

    # История работы
    history = []

    # Создание потоков студентов
    students = []
    for i, s in enumerate(cfg.get("students", []), start=1):
        students.append(
            StudentThread(
                i,
                s["name"],
                s["burst"],
                s["resources"],
                petri,
                history,
            )
        )

    # Запуск потоков
    for t in students:
        t.start()
    for t in students:
        t.join()

    # Формирование вывода
    out = []
    out.append(f"NR {cfg['NR']}")
    for i, r in enumerate(cfg.get("resources", []), start=1):
        out.append(f"RES id={i:<2} name={r['name']:<20} count={r['count']}")
    out.append("")
    out.append(f"NP {cfg['NP']}")
    for i, s in enumerate(cfg.get("students", []), start=1):
        out.append(
            f"ST id={i:<2} name={s['name']:<20} priority={s['priority']} burst={s['burst']} group={s['group']}"
        )
    out.append("")
    out.append("HISTORY:")
    for entry in history:
        res_str = " ".join(f"{k}:{v}" for k, v in entry["resources"].items())
        out.append(
            f"{entry['time']} | Student {entry['student_name']} ({entry['student_state']}) | {res_str}"
        )

    return "\n".join(out)
