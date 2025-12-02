import json
from collections import defaultdict, deque

# -----------------------------------------------------------
# СХЕМА СЕТИ ПЕТРИ (имитация мульти-семафора)
# -----------------------------------------------------------
class PetriNet:
    def __init__(self, resources):
        self.P = list(resources.keys())        # позиции — ресурсы
        self.T = list(resources.keys())        # переходы, нумеруем для простоты
        self.mu = {r: resources[r].capacity for r in resources}  # маркировка
        self.I = {t: [t] for t in self.T}      # входы
        self.O = {t: [t] for t in self.T}      # выходы

    def fire(self, tid):
        """Попытка запустить переход для потока tid"""
        if all(self.mu[r] > 0 for r in self.I[tid]):
            for r in self.I[tid]:
                self.mu[r] -= 1
            for r in self.O[tid]:
                self.mu[r] += 1
            return True
        return False

# -----------------------------------------------------------
# РЕСУРС (сеть Петри)
# -----------------------------------------------------------
class PetriResource:
    def __init__(self, rid, name, capacity=1):
        self.id = rid
        self.name = name
        self.capacity = capacity
        self.tokens = capacity
        self.owners = []

    def try_acquire(self, tid):
        if self.tokens > 0:
            self.tokens -= 1
            self.owners.append(tid)
            return True
        return False

    def release(self, tid):
        if tid in self.owners:
            self.owners.remove(tid)
            self.tokens += 1

    def status_str(self):
        return ",".join(map(str, self.owners)) if self.owners else "0"

# -----------------------------------------------------------
# ПОТОК (студент)
# -----------------------------------------------------------
class StudentThread:
    def __init__(self, tid, name, group, priority, burst, required_resources):
        self.id = tid
        self.name = name
        self.group = group
        self.priority = priority
        self.burst = burst
        self.remaining = burst
        self.required = required_resources[:]
        self.state = "N"  # N — not started

    def finished(self):
        return self.remaining <= 0

# -----------------------------------------------------------
# ОСНОВНОЙ СИМУЛЯТОР
# -----------------------------------------------------------
class SchedulerSimulator:
    def __init__(self, cfg):
        self.cfg = cfg
        self.PA = cfg.get("PA", 2)  # 1 = LCFS, 2 = MLQ
        self.QT = cfg.get("QT", 50)
        self.resources = {}
        self.students = {}
        self.time = 0
        self.history = []

        self._parse(cfg)
        self.petri = PetriNet(self.resources)

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

    def try_acquire_all(self, s):
        acquired = []
        for rid in s.required:
            res = self.resources.get(rid)
            if not res or not res.try_acquire(s.id):
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

    def snapshot(self):
        res_state = [self.resources[r].status_str() for r in sorted(self.resources)]
        thr_state = [f"{s.state}{s.id}" for s in self.students.values()]
        return (res_state, thr_state)

    # MLQ
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

    # LCFS
    def run_lcfs(self):
        stack = [s.id for s in self.students.values()]
        for s in self.students.values():
            s.state = "READY"
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
                self.history.append((self.time, *self.snapshot()))
                continue
            s.state = "R"
            step = s.remaining
            self.time += step
            s.remaining = 0
            self.history.append((self.time, *self.snapshot()))
            self.release_all(s)
            s.state = "F"
            stack.pop()

        self.history.append((self.time, *self.snapshot()))
        return {"T": self.time, "history": self.history}

    def run(self):
        if self.PA == 1:
            return self.run_lcfs()
        return self.run_mlq()

def _col(val, width, align="right"):
    val = str(val)
    return val.rjust(width) if align == "right" else val.ljust(width)

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
            f"ST id={sid:<2} name={_col(s.name,20,'left')} priority={s.priority:<2} burst={s.burst:<4} group={s.group}"
        )

    lines.append("")
    lines.append(f"T {result.get('T')}")
    lines.append("")

    res_ids = sorted(sim.resources.keys())
    thr_ids = sorted(sim.students.keys())
    header = "TIME   | " + " ".join([_col(f"R{rid}", 4) for rid in res_ids]) + " || " + " ".join([_col(f"TH{sid}", 8) for sid in thr_ids])
    lines.append(header)

    for time_ms, res_vals, thr_vals in result["history"]:
        r_cols = " ".join([_col(v, 4) for v in res_vals])
        t_cols = " ".join([_col(v, 8, "left") for v in thr_vals])
        lines.append(f"{time_ms:06d} | {r_cols} || {t_cols}")

    return "\n".join(lines)
