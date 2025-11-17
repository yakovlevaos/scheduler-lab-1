import json
from collections import defaultdict, deque

# -----------------------------------------------------------
#  РЕСУРС (сеть Петри): имеет capacity (число токенов),
#  список владельцев и методы захвата/освобождения.
# -----------------------------------------------------------
class PetriResource:
    def __init__(self, rid, name, capacity=1):
        self.id = rid
        self.name = name
        self.capacity = capacity
        self.tokens = capacity
        self.owners = []

    def try_acquire(self, tid):
        """Пытается выделить токен для потока tid."""
        if self.tokens > 0:
            self.tokens -= 1
            self.owners.append(tid)
            return True
        return False

    def release(self, tid):
        """Освобождает ресурс, если поток tid им владел."""
        if tid in self.owners:
            self.owners.remove(tid)
            self.tokens += 1

    def status_str(self):
        """Строка с владельцами ресурса (по методичке — либо id, либо 0)."""
        return ",".join(map(str, self.owners)) if self.owners else "0"


# -----------------------------------------------------------
#  ПОТОК (студент): хранит burst, приоритет, состояние и требования.
# -----------------------------------------------------------
class StudentThread:
    def __init__(self, tid, name, group, priority, burst, required_resources):
        self.id = tid
        self.name = name
        self.group = group
        self.priority = priority
        self.burst = burst
        self.remaining = burst
        self.required = required_resources[:]  # список id ресурсов
        self.state = "N"  # N — not started (на выходе READY/R/W/F)

    def finished(self):
        return self.remaining <= 0


# -----------------------------------------------------------
#  ОСНОВНОЙ СИМУЛЯТОР
# -----------------------------------------------------------
class SchedulerSimulator:
    def __init__(self, cfg):
        self.cfg = cfg
        self.PA = cfg.get("PA", 2)      # 1 = LCFS, 2 = MLQ
        self.QT = cfg.get("QT", 50)     # квант для MLQ
        self.resources = {}
        self.students = {}
        self.time = 0
        self.history = []               # сюда попадают снимки состояния
        self._parse(cfg)

    # Разбор входного JSON
    def _parse(self, cfg):
        rid = 1
        for r in cfg.get("resources", []):
            self.resources[rid] = PetriResource(
                rid,
                r.get("name", f"Resource{rid}"),
                r.get("count", 1)
            )
            rid += 1

        sid = 1
        for s in cfg.get("students", []):
            self.students[sid] = StudentThread(
                sid,
                s.get("name", f"Student{sid}"),
                s.get("group", ""),
                int(s.get("priority", 1)),
                int(s.get("burst", 1)),
                list(s.get("resources", []))
            )
            sid += 1

    def all_done(self):
        return all(s.finished() for s in self.students.values())

    # Попытка выделить все ресурсы потоку
    def try_acquire_all(self, s):
        acquired = []
        for rid in s.required:
            res = self.resources.get(rid)
            if not res:
                for a in acquired:
                    self.resources[a].release(s.id)
                return False
            if not res.try_acquire(s.id):
                for a in acquired:
                    self.resources[a].release(s.id)
                return False
            acquired.append(rid)
        return True

    def release_all(self, s):
        for rid in s.required:
            res = self.resources.get(rid)
            if res:
                res.release(s.id)

    # Снимок состояния (resources + threads)
    def snapshot(self):
        res_state = [self.resources[r].status_str() for r in sorted(self.resources)]
        thr_state = [f"{s.state}{s.id}" for s in self.students.values()]
        return (res_state, thr_state)

    # Главный цикл MLQ
    def run_mlq(self):
        queues = defaultdict(deque)
        for s in self.students.values():
            s.state = "READY"
            queues[s.priority].append(s.id)
        priorities = sorted(queues.keys(), reverse=True)

        self.history.append((self.time, *self.snapshot()))

        while not self.all_done():
            picked = None
            for p in priorities:
                while queues[p] and self.students[queues[p][0]].finished():
                    queues[p].popleft()
                if queues[p]:
                    picked = queues[p].popleft()
                    break

            if picked is None:
                if any(s.state == "W" for s in self.students.values()):
                    return {"T": "deadlock", "history": self.history}
                break

            s = self.students[picked]

            if not self.try_acquire_all(s):
                s.state = "W"
                queues[s.priority].append(picked)
            else:
                s.state = "R"
                step = min(self.QT, s.remaining)
                self.time += step
                s.remaining -= step
                self.history.append((self.time, *self.snapshot()))
                self.release_all(s)

                if s.finished():
                    s.state = "F"
                else:
                    s.state = "READY"
                    queues[s.priority].append(picked)

        self.history.append((self.time, *self.snapshot()))
        return {"T": self.time, "history": self.history}

    # Главный цикл LCFS (non-preemptive)
    def run_lcfs(self):
        stack = []
        for s in self.students.values():
            s.state = "READY"
            stack.append(s.id)

        self.history.append((self.time, *self.snapshot()))

        while not self.all_done():
            while stack and self.students[stack[-1]].finished():
                stack.pop()

            if not stack:
                if any(s.state == "W" for s in self.students.values()):
                    return {"T": "deadlock", "history": self.history}
                break

            tid = stack[-1]
            s = self.students[tid]

            if not self.try_acquire_all(s):
                s.state = "W"
                # LCFS не добавляет поток обратно, т.к. он в стеке на месте ожидания
                self.history.append((self.time, *self.snapshot()))
                # Ожидание, пока ресурсы освободятся
                continue

            s.state = "R"
            step = s.remaining  # non-preemptive - весь burst целиком
            self.time += step
            s.remaining = 0
            self.history.append((self.time, *self.snapshot()))
            self.release_all(s)
            s.state = "F"
            stack.pop()

        self.history.append((self.time, *self.snapshot()))
        return {"T": self.time, "history": self.history}

    # Основной метод run - переключается по PA
    def run(self):
        if self.PA == 1:
            return self.run_lcfs()
        else:
            return self.run_mlq()


# ===========================================================
#  Форматирование вывода
# ===========================================================

def _col(val, width, align="right"):
    val = str(val)
    if align == "right":
        return val.rjust(width)
    return val.ljust(width)


def run_simulation(json_str):

    try:
        cfg = json.loads(json_str)
    except Exception as e:
        return f"JSON parse error: {e}"

    sim = SchedulerSimulator(cfg)
    result = sim.run()

    lines = []
    lines.append(f"NR {len(sim.resources)}")
    for rid in sorted(sim.resources):
        r = sim.resources[rid]
        lines.append(
            f"RES id={rid:<2} name={_col(r.name,20,'left')} count={r.capacity}"
        )
    lines.append("")
    lines.append(f"NP {len(sim.students)}")
    for sid in sorted(sim.students):
        s = sim.students[sid]
        lines.append(
            f"ST id={sid:<2} name={_col(s.name,20,'left')} "
            f"priority={s.priority:<2} burst={s.burst:<4} group={s.group}"
        )
    lines.append("")
    lines.append(f"T {result.get('T')}")
    lines.append("")
    res_ids = sorted(sim.resources.keys())
    thr_ids = sorted(sim.students.keys())
    header = (
        "TIME   | "
        + " ".join([_col(f"R{rid}", 4) for rid in res_ids])
        + " || "
        + " ".join([_col(f"TH{sid}", 8) for sid in thr_ids])
    )
    lines.append(header)
    for time_ms, res_vals, thr_vals in result["history"]:
        r_cols = " ".join([_col(v, 4) for v in res_vals])
        t_cols = " ".join([_col(v, 8, "left") for v in thr_vals])
        lines.append(f"{time_ms:06d} | {r_cols} || {t_cols}")
    return "\n".join(lines)
