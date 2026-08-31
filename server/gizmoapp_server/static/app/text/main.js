import { requestJson } from "../api.js";

let apiBase;
let articles = [];
let selectedId;
let activeView = "library";
let activeFilter = "all";
let selectedGraphId;
let chatMessages = [];
let chatBusy = false;
const storageKey = "storyline-library-v1";
const bookmarkStorageKey = "storyline-bookmarks-v1";

const $ = (selector) => document.querySelector(selector);
const escapeHtml = (value) => String(value || "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll("'", "&#39;").replaceAll(String.fromCharCode(34), "&quot;");
const formatDate = (date) => new Intl.DateTimeFormat("en", { month: "short", day: "numeric", year: "numeric" }).format(new Date(`${date}T12:00:00`));

function saveLibrary() {
  try { window.localStorage.setItem(storageKey, JSON.stringify(articles)); }
  catch (error) { console.warn("Storyline could not save this library in the browser.", error); }
  saveBookmarks();
}

function saveBookmarks() {
  try { window.localStorage.setItem(bookmarkStorageKey, JSON.stringify(articles.filter((article) => article.bookmarked).map((article) => article.id))); }
  catch (error) { console.warn("Storyline could not save bookmarks in the browser.", error); }
}

function loadBookmarks() {
  try {
    const stored = window.localStorage.getItem(bookmarkStorageKey);
    if (stored === null) return null;
    const ids = JSON.parse(stored);
    return Array.isArray(ids) ? new Set(ids.map(Number).filter(Number.isFinite)) : new Set();
  } catch (error) {
    console.warn("Storyline could not read browser bookmarks.", error);
    return null;
  }
}

function loadLibrary() {
  try {
    const stored = window.localStorage.getItem(storageKey);
    if (!stored) return null;
    const library = JSON.parse(stored);
    if (!Array.isArray(library)) return null;
    const bookmarkIds = loadBookmarks();
    if (bookmarkIds) library.forEach((article) => { article.bookmarked = bookmarkIds.has(Number(article.id)); });
    return library;
  } catch (error) {
    console.warn("Storyline could not read the browser library.", error);
    return null;
  }
}

function nextArticleId() {
  return articles.reduce((highest, article) => Math.max(highest, Number(article.id) || 0), 0) + 1;
}

function setDarkMode(enabled) {
  document.body.classList.toggle("dark-mode", enabled);
  const button = $("#theme-button");
  if (button) { button.textContent = enabled ? "Light mode" : "Dark mode"; button.setAttribute("aria-pressed", String(enabled)); }
}

function visibleArticles() {
  const query = $("#search-input").value.trim().toLowerCase();
  return articles.filter((article) => {
    const matchesQuery = !query || `${article.title} ${article.source} ${article.topic} ${article.summary} ${(article.tags || []).join(" ")}`.toLowerCase().includes(query);
    return matchesQuery && (activeFilter !== "bookmarked" || article.bookmarked);
  });
}

function renderList() {
  const list = visibleArticles();
  $("#article-count").textContent = `${articles.length} stor${articles.length === 1 ? "y" : "ies"}`;
  $("#bookmark-count").textContent = articles.filter((article) => article.bookmarked).length;
  $("#all-filter").classList.toggle("active", activeFilter === "all");
  $("#bookmarked-filter").classList.toggle("active", activeFilter === "bookmarked");
  $("#article-list").innerHTML = list.length ? list.map((article) => `
    <button class="article-card ${article.id === selectedId ? "selected" : ""}" data-id="${article.id}">
      <div class="article-meta"><span class="article-tag">${escapeHtml(article.topic)}</span><span>${article.bookmarked ? "★ Bookmarked" : formatDate(article.published_at)}</span></div>
      <h2>${escapeHtml(article.title)}</h2>
    </button>`).join("") : `<p class="empty-reading">No stories match that search.</p>`;
  document.querySelectorAll(".article-card").forEach((button) => button.addEventListener("click", () => selectArticle(Number(button.dataset.id))));
}

function renderReading() {
  const article = articles.find((item) => item.id === selectedId);
  if (!article) { $("#reading-panel").innerHTML = `<div class="empty-reading">Choose a story from your library.</div>`; return; }
  const relationship = article.relationship ? `<div class="relationship"><div class="relationship-icon">${article.relationship_type === "contradiction" ? "!" : "↗"}</div><div><h3>${article.relationship_type === "contradiction" ? "A detail to question" : "A thread to follow"}</h3><p>${escapeHtml(article.relationship)}</p></div></div>` : "";
  const tags = (article.tags || []).map((tag) => `<span class="story-tag">${escapeHtml(tag)}</span>`).join("");
  $("#reading-panel").innerHTML = `<div class="story-inner">
    <div class="story-kicker"><span></span>${escapeHtml(article.topic)}</div>
    <h2 class="story-title">${escapeHtml(article.title)}</h2>
      <div class="story-source">${escapeHtml(article.source)} &nbsp;·&nbsp; <strong>${formatDate(article.published_at)}</strong>${article.url ? ` &nbsp;·&nbsp; <a class="source-link" href="${escapeHtml(article.url)}" target="_blank" rel="noopener">Read original ↗</a>` : ""}</div>
      <button class="bookmark-button ${article.bookmarked ? "bookmarked" : ""}" id="bookmark-button" type="button" aria-pressed="${Boolean(article.bookmarked)}">${article.bookmarked ? "★ Bookmarked" : "☆ Bookmark this story"}</button>
    <div class="story-rule"></div>
    <div class="simple-label">The simple version <span>Explain it like I'm 5</span></div>
     <div class="summary-box"><p>${escapeHtml(article.summary)}</p></div>
     <div class="story-tags"><span class="tags-label">AI TAGS</span>${tags || `<button class="tag-button" id="tag-button">✦ Generate tags with AI</button>`}</div>
     <button class="simplify-button" id="simplify-button">✦ Make this even simpler with AI</button>
     <section class="article-chat" aria-label="Ask AI about this story"><div class="chat-heading"><div><span class="simple-label">Ask about this story</span><p>Ask for context, definitions, or the article's main argument.</p></div><span class="chat-badge">AI COMPANION</span></div><div class="chat-messages" id="chat-messages">${chatMessages.length ? chatMessages.map((message) => `<div class="chat-message ${message.role}"><span>${message.role === "user" ? "You" : "Storyline"}</span><p>${escapeHtml(message.content).replaceAll("\n", "<br>")}</p></div>`).join("") : `<p class="chat-empty">What would you like to understand better?</p>`}</div><form class="chat-form" id="chat-form"><input id="chat-input" name="message" maxlength="2000" placeholder="Ask a question about this story..." autocomplete="off" ${chatBusy ? "disabled" : ""}><button type="submit" ${chatBusy ? "disabled" : ""}>${chatBusy ? "Thinking..." : "Ask"}</button></form></section>
     <button class="delete-button" id="delete-button">Delete this story</button>
    ${relationship}
  </div>`;
   $("#simplify-button").addEventListener("click", simplifySelected);
  $("#bookmark-button").addEventListener("click", toggleBookmark);
  $("#delete-button").addEventListener("click", deleteSelected);
  $("#tag-button")?.addEventListener("click", tagSelected);
  $("#chat-form").addEventListener("submit", askAboutSelected);
  const chatBox = $("#chat-messages"); chatBox.scrollTop = chatBox.scrollHeight;
}

function toggleBookmark() {
  const article = articles.find((item) => item.id === selectedId);
  if (!article) return;
  article.bookmarked = !article.bookmarked;
  saveLibrary();
  renderList();
  renderReading();
  renderOverview();
}

function renderOverview() {
  const topics = Object.entries(articles.reduce((counts, article) => {
    const topic = article.topic || "Uncategorized";
    counts[topic] = (counts[topic] || 0) + 1;
    return counts;
  }, {})).sort((left, right) => right[1] - left[1]);
  const tags = Object.entries(articles.flatMap((article) => article.tags || []).reduce((counts, tag) => {
    counts[tag] = (counts[tag] || 0) + 1;
    return counts;
  }, {})).sort((left, right) => right[1] - left[1]).slice(0, 8);
  const sources = new Set(articles.map((article) => article.source).filter(Boolean)).size;
  const tagged = articles.filter((article) => (article.tags || []).length).length;
  const maxTopicCount = topics[0]?.[1] || 1;
  const topicRows = topics.length ? topics.map(([topic, count]) => `<div class="topic-row"><div class="topic-row-label"><span>${escapeHtml(topic)}</span><strong>${count}</strong></div><div class="topic-bar"><span style="width: ${(count / maxTopicCount) * 100}%"></span></div></div>`).join("") : `<p class="overview-empty">Save a story to see topic patterns.</p>`;
  const tagCloud = tags.length ? tags.map(([tag, count]) => `<span class="overview-tag">${escapeHtml(tag)} <b>${count}</b></span>`).join("") : `<p class="overview-empty">Generate tags on a story to see recurring themes.</p>`;
  $("#overview-panel").innerHTML = `<div class="overview-inner"><div class="overview-heading"><div><div class="eyebrow">YOUR READING MEMORY</div><h2>At a glance</h2><p>See what your library is becoming.</p></div><span class="overview-updated">Based on ${articles.length} saved ${articles.length === 1 ? "story" : "stories"}</span></div><div class="overview-stats"><div class="overview-stat"><span>Stories saved</span><strong>${articles.length}</strong><small>in your library</small></div><div class="overview-stat"><span>Topics covered</span><strong>${topics.length}</strong><small>distinct subjects</small></div><div class="overview-stat"><span>Sources</span><strong>${sources}</strong><small>publications and people</small></div><div class="overview-stat"><span>Tagged stories</span><strong>${tagged}</strong><small>${articles.length ? Math.round((tagged / articles.length) * 100) : 0}% of your library</small></div></div><div class="overview-columns"><section class="overview-card"><div class="overview-card-heading"><span class="overview-label">TOPIC DISTRIBUTION</span><span>${topics.length} topics</span></div><div class="topic-list">${topicRows}</div></section><section class="overview-card"><div class="overview-card-heading"><span class="overview-label">RECURRING THEMES</span><span>top 8 tags</span></div><div class="overview-tags">${tagCloud}</div></section></div></div>`;
}

function selectArticle(id) { selectedId = id; chatMessages = []; chatBusy = false; renderList(); renderReading(); renderOverview(); }

async function askAboutSelected(event) {
  event.preventDefault();
  const input = $("#chat-input");
  const question = input.value.trim();
  if (!question || chatBusy) return;
  const article = articles.find((item) => item.id === selectedId);
  if (!article) return;
  chatMessages.push({ role: "user", content: question });
  chatBusy = true;
  renderReading();
  try {
    const result = await requestJson(`${apiBase}/articles/${selectedId}/chat`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ article, messages: chatMessages.slice(-10) }) });
    chatMessages.push({ role: "assistant", content: result.answer });
  } catch (error) {
    chatMessages.push({ role: "assistant", content: `I couldn't answer that right now: ${error.message}` });
  } finally {
    chatBusy = false;
    renderReading();
  }
}

async function simplifySelected() {
  const button = $("#simplify-button");
  button.disabled = true;
  button.textContent = "✦ Asking the story editor...";
  try {
    const result = await requestJson(`${apiBase}/articles/${selectedId}/simplify`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ article: articles.find((item) => item.id === selectedId) }) });
    const article = articles.find((item) => item.id === selectedId);
    Object.assign(article, result.article);
    saveLibrary();
    renderReading();
  } catch (error) {
    button.disabled = false;
    button.textContent = `Couldn't simplify: ${error.message}`;
  }
}

async function tagSelected() {
  const button = $("#tag-button"); button.disabled = true; button.textContent = "✦ Finding the themes...";
  try { Object.assign(articles.find((item) => item.id === selectedId), (await requestJson(`${apiBase}/articles/${selectedId}/tags`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ article: articles.find((item) => item.id === selectedId) }) })).article); saveLibrary(); renderReading(); renderList(); renderOverview(); }
  catch (error) { button.disabled = false; button.textContent = `Couldn't tag: ${error.message}`; }
}

async function deleteSelected() {
  const article = articles.find((item) => item.id === selectedId);
  if (!article || !window.confirm(`Delete “${article.title}”?`)) return;
  try { articles = articles.filter((item) => item.id !== selectedId); saveLibrary(); selectedId = articles[0]?.id; renderList(); renderReading(); renderOverview(); renderGraph(); }
  catch (error) { window.alert(`Couldn't delete this story: ${error.message}`); }
}

function renderGraph() {
  const width = 1280, height = 650, centerX = width / 2, centerY = height / 2;
  const centerId = selectedGraphId || selectedId;
  const activeId = selectedId || centerId;
  const selectedArticle = articles.find((article) => article.id === activeId);
  const centerArticle = articles.find((article) => article.id === centerId);
  const orbitArticles = articles.filter((article) => article.id !== centerId);
  const radius = Math.min(235, 118 + orbitArticles.length * 19);
  const nodes = centerArticle ? [{ article: centerArticle, x: centerX, y: centerY, selected: centerArticle.id === activeId }, ...orbitArticles.map((article, index) => {
    const angle = (index / Math.max(orbitArticles.length, 1)) * Math.PI * 2 - Math.PI / 2;
    return { article, x: centerX + Math.cos(angle) * radius, y: centerY + Math.sin(angle) * radius, selected: false };
  })] : [];
  const connectedIds = new Set();
  const edges = [];
  nodes.forEach((left, index) => nodes.slice(index + 1).forEach((right) => {
    const shared = connectionReasons(left.article, right.article);
    if (!shared.length) return;
    const direct = shared.some((reason) => reason.type === "topic");
    const active = left.article.id === activeId || right.article.id === activeId;
    if (active) { connectedIds.add(left.article.id); connectedIds.add(right.article.id); }
    const label = shared.length > 1 ? `${shared.length} shared signals` : shared[0].label;
    const midX = (left.x + right.x) / 2, midY = (left.y + right.y) / 2;
    edges.push(`<g class="graph-connection ${direct ? "direct" : ""} ${active ? "active" : "dimmed"}"><line x1="${left.x}" y1="${left.y}" x2="${right.x}" y2="${right.y}" /><text x="${midX}" y="${midY - 8}" text-anchor="middle">${escapeHtml(label)}</text></g>`);
  }));
  const status = articles.length ? `${articles.length} ${articles.length === 1 ? "story" : "stories"} in your map` : "Save a story to start your map";
  const selectedTags = (selectedArticle?.tags || []).map((tag) => `<span class="story-tag">${escapeHtml(tag)}</span>`).join("");
  const selectedConnections = selectedArticle ? articles.filter((article) => article.id !== selectedArticle.id && connectionReasons(selectedArticle, article).length).length : 0;
  const inspector = selectedArticle ? `<aside class="graph-inspector" aria-live="polite"><div class="inspector-kicker"><span class="inspector-number">${String(selectedArticle.id).padStart(2, "0")}</span><span>${selectedConnections} ${selectedConnections === 1 ? "connection" : "connections"}</span></div><h3>${escapeHtml(selectedArticle.title)}</h3><p class="inspector-source">${escapeHtml(selectedArticle.source)} · ${formatDate(selectedArticle.published_at)}</p><p class="inspector-summary">${escapeHtml(selectedArticle.summary)}</p>${selectedTags ? `<div class="inspector-tags">${selectedTags}</div>` : ""}${selectedArticle.relationship ? `<div class="inspector-relationship"><strong>${selectedArticle.relationship_type === "contradiction" ? "Question this" : "AI note"}</strong><p>${escapeHtml(selectedArticle.relationship)}</p></div>` : ""}</aside>` : "";
  $("#graph-panel").innerHTML = `<div class="graph-stage"><div class="graph-topline"><div><div class="eyebrow">YOUR READING MEMORY</div><h2>Connections</h2><p>Follow the ideas that keep showing up.</p></div><span>${escapeHtml(status)}</span></div><div class="graph-layout"><div class="graph-wrap"><div class="graph-legend"><span><i class="legend-dot theme"></i> shared tags</span><span><i class="legend-dot direct"></i> same topic</span><span class="graph-hint">Select a story to focus its orbit</span></div><div class="graph-canvas"><svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Interactive graph of connections between saved stories"><defs><radialGradient id="graph-glow"><stop stop-color="#f3b09b" stop-opacity=".28"></stop><stop offset="1" stop-color="#f3b09b" stop-opacity="0"></stop></radialGradient><linearGradient id="graph-line" x1="0" x2="1"><stop stop-color="#b6cdbb"></stop><stop offset="1" stop-color="#d9d5ec"></stop></linearGradient></defs><circle class="graph-halo" cx="${centerX}" cy="${centerY}" r="${radius + 60}"></circle>${edges.join("")}${nodes.map(({ article, x, y }) => { const selected = article.id === activeId; const connected = connectedIds.has(article.id); const title = escapeHtml(article.title); return `<g class="graph-node ${selected ? "active" : ""} ${connected ? "connected" : ""}" data-id="${article.id}" tabindex="0" role="button" aria-label="Explore ${title}"><circle class="node-ring" cx="${x}" cy="${y}" r="${selected ? 48 : 34}" /><circle class="node-core" cx="${x}" cy="${y}" r="${selected ? 31 : 23}" /><text class="node-index" x="${x}" y="${y + 5}" text-anchor="middle">${String(article.id).padStart(2, "0")}</text><text class="node-title" x="${x}" y="${y + (selected ? 63 : 57)}" text-anchor="middle">${title.slice(0, 32)}${article.title.length > 32 ? "…" : ""}</text><text class="node-topic" x="${x}" y="${y + (selected ? 81 : 75)}" text-anchor="middle">${escapeHtml(article.topic)}</text></g>`; }).join("")}</svg></div>${articles.length > 1 && !edges.length ? `<div class="graph-empty-note"><strong>No threads yet</strong><br>No shared tags or topics connect these stories.</div>` : ""}${!articles.length ? `<div class="graph-empty-note"><strong>Your map is empty</strong><br>Save a story to begin finding threads.</div>` : ""}</div>${inspector}</div></div>`;
  $(".graph-hint").textContent = "Select a story to inspect its connections";
  document.querySelectorAll(".graph-node").forEach((node) => { const choose = () => { selectedId = Number(node.dataset.id); renderGraph(); }; node.addEventListener("click", choose); node.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); choose(); } }); });
}

function connectionReasons(left, right) {
  const reasons = [];
  // Edges use saved, inspectable metadata rather than guessing from prose.
  const leftTags = new Set((left.tags || []).map((tag) => tag.toLowerCase()));
  const shared = (right.tags || []).filter((tag) => leftTags.has(tag.toLowerCase()));
  shared.forEach((value) => reasons.push({ type: "theme", label: `tag: ${value}` }));
  const leftTopic = String(left.topic || "").trim().toLowerCase();
  const rightTopic = String(right.topic || "").trim().toLowerCase();
  if (leftTopic && leftTopic === rightTopic) reasons.push({ type: "topic", label: `topic: ${left.topic}` });
  return reasons;
}

function showLibrary() { activeView = "library"; $(".app-shell").classList.remove("graph-mode", "overview-mode"); $("#reading-panel").hidden = false; $("#overview-panel").hidden = true; $("#graph-panel").hidden = true; $(".library-panel").hidden = false; $("#library-view").classList.add("active"); $("#overview-view").classList.remove("active"); $("#graph-view").classList.remove("active"); }
function showOverview() { activeView = "overview"; $(".app-shell").classList.remove("graph-mode"); $(".app-shell").classList.add("overview-mode"); $("#reading-panel").hidden = true; $("#overview-panel").hidden = false; $("#graph-panel").hidden = true; $(".library-panel").hidden = true; $("#library-view").classList.remove("active"); $("#overview-view").classList.add("active"); $("#graph-view").classList.remove("active"); renderOverview(); }
function showGraph() { activeView = "graph"; selectedGraphId = selectedId; $(".app-shell").classList.add("graph-mode"); $(".app-shell").classList.remove("overview-mode"); $("#reading-panel").hidden = true; $("#overview-panel").hidden = true; $("#graph-panel").hidden = false; $(".library-panel").hidden = true; $("#library-view").classList.remove("active"); $("#overview-view").classList.remove("active"); $("#graph-view").classList.add("active"); renderGraph(); }

function openModal() {
  const modal = document.createElement("div");
  modal.className = "modal";
   modal.innerHTML = `<form class="modal-card" id="story-form"><h2>Bring in a story</h2>
     <p class="modal-hint">Paste a public article link. Storyline will read it, extract the important details, and make an explain-like-I'm-5 summary with AI.</p>
     <label class="form-field">Article link <span>(recommended)</span><input name="url" type="url" placeholder="https://news.example.com/article"></label>
     <details class="manual-entry"><summary>Or enter it yourself</summary>
       <label class="form-field">Headline<input name="title" maxlength="240" placeholder="What happened?"></label>
       <label class="form-field">Source<input name="source" maxlength="120" placeholder="Publication or person"></label>
       <label class="form-field">Your note <span>(optional)</span><input name="summary" placeholder="Why does this matter to you?"></label>
     </details>
     <div class="modal-actions"><button type="button" id="cancel-story">Cancel</button><button class="save">Extract with AI</button></div></form>`;
  document.body.append(modal);
  $("#cancel-story").addEventListener("click", () => modal.remove());
  $("#story-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(event.currentTarget));
    const save = event.currentTarget.querySelector(".save"); save.disabled = true; save.textContent = "Saving...";
     try {
       const importing = Boolean(data.url);
       if (!importing && (!data.title || !data.source)) throw new Error("Add a link, or provide both a headline and source.");
       save.textContent = importing ? "Reading and simplifying..." : "Saving...";
        const result = importing
          ? await requestJson(`${apiBase}/articles/import`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) })
          : { article: { ...data, id: nextArticleId(), published_at: new Date().toISOString().slice(0, 10), topic: "Saved story", summary: data.summary || "Not simplified yet.", body: "", tags: [], relationship: "", relationship_type: "" } };
        articles.unshift(result.article); modal.remove(); selectArticle(result.article.id);
        saveLibrary();
     } catch (error) { save.disabled = false; save.textContent = error.message; }
  });
}

async function importLibrary(file) {
  const input = $("#import-input");
  try {
    const payload = JSON.parse(await file.text());
    if (payload.format !== "storyline-articles" || payload.version !== 1) throw new Error("Choose a Storyline JSON export.");
    const imported = payload.articles.filter((article) => article && article.title && article.source).map((article, index) => ({ ...article, id: nextArticleId() + index }));
    const existing = new Set(articles.map((article) => `${article.title}\u0000${article.source}`));
    const fresh = imported.filter((article) => !existing.has(`${article.title}\u0000${article.source}`));
    const result = { imported: fresh.length, skipped: imported.length - fresh.length, invalid: payload.articles.length - imported.length };
    articles = [...fresh, ...articles];
    saveLibrary();
    selectedId = articles[0]?.id;
    renderList(); renderReading(); renderOverview();
    const detail = [`Imported ${result.imported}`, result.skipped ? `${result.skipped} already in library` : "", result.invalid ? `${result.invalid} invalid` : ""].filter(Boolean).join(" · ");
    window.alert(detail || "No new articles were imported.");
    if (result.errors?.length) window.alert(result.errors.join("\n"));
  } catch (error) {
    window.alert(`Couldn't import library: ${error.message}`);
  } finally {
    input.value = "";
  }
}

async function bootstrap() {
  const runtime = window.GizmoAppRuntime;
  if (!runtime) throw new Error("The shared app runtime did not load.");
  const config = runtime.readConfig(); apiBase = config.apiBase;
   articles = loadLibrary();
   if (!articles) {
     try { articles = (await requestJson(`${apiBase}/articles`)).articles; saveLibrary(); }
     catch (error) { articles = []; console.warn("Starting with an empty browser library.", error); }
   }
  selectedId = articles[0]?.id;
    renderList(); renderReading(); renderOverview(); runtime.markReady();
   $("#search-input").addEventListener("input", renderList);
   $("#all-filter").addEventListener("click", () => { activeFilter = "all"; renderList(); });
   $("#bookmarked-filter").addEventListener("click", () => { activeFilter = "bookmarked"; renderList(); });
   $("#new-story-button").addEventListener("click", openModal);
    $("#export-button").addEventListener("click", () => { const blob = new Blob([JSON.stringify({ format: "storyline-articles", version: 1, articles }, null, 2)], { type: "application/json" }); const link = document.createElement("a"); link.href = URL.createObjectURL(blob); link.download = "storyline-articles.json"; link.click(); URL.revokeObjectURL(link.href); });
    $("#import-button").addEventListener("click", () => $("#import-input").click());
   $("#import-input").addEventListener("change", (event) => { const file = event.target.files?.[0]; if (file) importLibrary(file); });
    $("#library-view").addEventListener("click", showLibrary); $("#overview-view").addEventListener("click", showOverview); $("#graph-view").addEventListener("click", showGraph);
   $("#theme-button").addEventListener("click", () => setDarkMode(!document.body.classList.contains("dark-mode")));
  $("#help-button").addEventListener("click", () => window.alert("Storyline is your personal reading memory. Save a story, then use the AI editor when you want a gentler explanation."));
}

bootstrap().catch((error) => window.GizmoAppRuntime?.showFatalError(error));
