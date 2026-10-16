async function loadAtlas() {
  const status = document.getElementById("sample-status");
  const box = document.getElementById("atlas");
  const response = await fetch("/api/atlas");
  const data = await response.json();
  box.innerHTML = "";
  const glyphs = data.glyphs || [];
  if (!glyphs.length) {
    status.textContent = "Азбуки пока нет. Сначала загрузи фото.";
    return;
  }
  status.textContent = "Букв в азбуке: " + glyphs.length + ". Пустых клеток: " + (data.empty || []).length + ".";
  for (const item of glyphs) {
    const cell = document.createElement("div");
    cell.className = "cell";
    const img = document.createElement("img");
    const code = item.char.codePointAt(0).toString(16).toUpperCase().padStart(4, "0");
    img.src = "/glyph/" + code;
    img.alt = item.char;
    const caption = document.createElement("div");
    caption.textContent = item.char;
    cell.appendChild(img);
    cell.appendChild(caption);
    box.appendChild(cell);
  }
  if (data.empty && data.empty.length) {
    const note = document.createElement("p");
    note.className = "empty";
    note.textContent = "Пустые клетки, допиши их: " + data.empty.join(" ");
    box.appendChild(note);
  }
}

document.getElementById("samples").addEventListener("submit", async (event) => {
  event.preventDefault();
  const status = document.getElementById("sample-status");
  status.textContent = "Собираю азбуку…";
  const form = new FormData(event.target);
  const response = await fetch("/api/samples", { method: "POST", body: form });
  const data = await response.json();
  if (!data.ok) {
    status.textContent = data.message || "Не получилось";
    return;
  }
  await loadAtlas();
});

document.getElementById("render").addEventListener("submit", async (event) => {
  event.preventDefault();
  const status = document.getElementById("render-status");
  const result = document.getElementById("result");
  status.textContent = "Собираю страницы…";
  result.innerHTML = "";
  const form = new FormData(event.target);
  const response = await fetch("/api/render", { method: "POST", body: form });
  const data = await response.json();
  if (!data.ok) {
    status.textContent = data.message || "Не получилось";
    return;
  }
  status.textContent = "Готово. Страниц: " + data.pages.length + ".";
  if (data.missing && data.missing.length) {
    const warn = document.createElement("p");
    warn.className = "empty";
    warn.textContent = "Не хватает знаков, на странице они жёлтые: " + data.missing.join(" ");
    result.appendChild(warn);
  }
  const pdf = document.createElement("a");
  pdf.className = "link-btn";
  pdf.href = "/file/" + data.job + "/" + data.pdf;
  pdf.textContent = "Скачать PDF";
  result.appendChild(pdf);
  for (const name of data.pages) {
    const link = document.createElement("a");
    link.className = "page";
    link.href = "/file/" + data.job + "/" + name;
    link.textContent = name;
    const img = document.createElement("img");
    img.src = link.href;
    img.style.maxWidth = "320px";
    img.alt = name;
    result.appendChild(link);
    result.appendChild(img);
  }
});

loadAtlas();
