let pyodide = null;
let loadedJson = null;

const $ = (id) => document.getElementById(id);

async function ensurePyodide() {
  if (pyodide) return pyodide;

  $("status").textContent = "Загрузка Pyodide...";
  pyodide = await loadPyodide({
    indexURL: "https://cdn.jsdelivr.net/pyodide/v0.23.4/full/"
  });

  $("status").textContent = "Загрузка scheduler.py...";
  const resp = await fetch("scheduler.py");
  const code = await resp.text();
  await pyodide.runPythonAsync(code);

  $("status").textContent = "Готово";
  return pyodide;
}

// Загрузка примера JSON
async function loadExampleJson() {
  try {
    const resp = await fetch("input1.json");
    if (!resp.ok) throw new Error("Не удалось загрузить input1.json");
    const exampleJson = await resp.json();
    loadedJson = exampleJson;
    $("inputJsonPreview").value = JSON.stringify(exampleJson, null, 2);
    $("status").textContent = "Пример JSON загружен";
  } catch (err) {
    $("inputJsonPreview").value = "JSON не загружен";
    $("status").textContent = "Ошибка загрузки примера JSON";
    console.error(err);
  }
}

window.addEventListener("DOMContentLoaded", loadExampleJson);

// Загрузка JSON пользователем
$("jsonFileInput").addEventListener("change", (evt) => {
  const file = evt.target.files[0];
  if (!file) return;

  const reader = new FileReader();
  reader.onload = (e) => {
    try {
      loadedJson = JSON.parse(e.target.result);
      $("inputJsonPreview").value = JSON.stringify(loadedJson, null, 2);
      $("status").textContent = "JSON загружен";
    } catch {
      $("status").textContent = "Ошибка JSON";
    }
  };
  reader.readAsText(file, "utf-8");
});

// Запуск симуляции
$("runBtn").addEventListener("click", async () => {
  const txt = $("inputJsonPreview").value.trim();
  if (!txt || txt === "JSON не загружен") {
    $("status").textContent = "Окно JSON пустое";
    return;
  }

  try {
    loadedJson = JSON.parse(txt);
  } catch (err) {
    $("status").textContent = "Ошибка JSON: " + err;
    return;
  }

  // Выбор алгоритма в JSON -- PA
  loadedJson.PA = parseInt($("algorithm").value, 10);

  await ensurePyodide();

  $("status").textContent = "Выполнение...";
  $("output").textContent = "";

  try {
    const runSim = pyodide.globals.get("run_simulation");
    const result = runSim(JSON.stringify(loadedJson));
    $("output").textContent = result.toString();
    $("status").textContent = "Готово";
    runSim.destroy && runSim.destroy();
  } catch (err) {
    $("status").textContent = "Ошибка выполнения";
    console.error(err);
  }
});

// Сохранение результата
$("saveOutputBtn").addEventListener("click", () => {
  const txt = $("output").textContent || "";
  const blob = new Blob([txt], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);

  const a = document.createElement("a");
  a.href = url;
  a.download = "output.txt";
  document.body.appendChild(a);
  a.click();
  a.remove();

  URL.revokeObjectURL(url);
});
