// Card editor modal. Replaces the old image-only zoom.
//
// openEditor(cards, index, { onSave, getVocab }):
//   cards         array of card records (id, set, name, element[], type)
//   index         starting index into `cards`
//   opts.onSave   called with the updated card record after a successful save
//   opts.getVocab returns a Promise that resolves to {types, elements, sets}

let _modal = null;
let _state = null;

function _build() {
  const modal = document.createElement("div");
  modal.className = "editor-modal";
  modal.innerHTML = `
    <button class="ed-close" aria-label="close" title="Close (Esc)">×</button>
    <div class="editor-stage">
      <button class="ed-nav prev" aria-label="previous">◀</button>
      <div class="editor-body">
        <div class="editor-image"><img alt=""></div>
        <div class="editor-form">
          <div class="ed-head">
            <span class="ed-id"></span>
            <span class="ed-pos"></span>
          </div>
          <label>Name <input type="text" class="ed-name" autocomplete="off"></label>
          <div class="ed-set-block">
            <div class="ed-set-label">
              Set
              <button type="button" class="ed-add-set" title="Add a new set">+ new</button>
            </div>
            <div class="ed-set-rows"></div>
          </div>
          <label>Type
            <select class="ed-type"></select>
          </label>
          <div class="ed-element-block">
            <div class="ed-element-label">Attribute</div>
            <div class="ed-element-chips"></div>
          </div>
          <div class="ed-actions">
            <button type="button" class="ed-save" disabled>Save</button>
            <div class="ed-status"></div>
          </div>
        </div>
      </div>
      <button class="ed-nav next" aria-label="next">▶</button>
    </div>`;
  document.body.appendChild(modal);
  // Close on click of: backdrop, stage gaps, or the X button.
  // NOT on .editor-body — clicks inside the body (between or near the
  // image and form panels) should never dismiss the editor.
  modal.addEventListener("click", (e) => {
    if (e.target === modal
        || e.target.classList.contains("editor-stage")) {
      close();
    }
  });
  modal.querySelector(".ed-close").addEventListener("click", close);
  modal.querySelector(".prev").addEventListener("click", () => move(-1));
  modal.querySelector(".next").addEventListener("click", () => move(+1));
  // Edits only flag the form dirty (enabling Save); nothing persists until the
  // user clicks Save.
  modal.querySelector(".ed-name").addEventListener("input", refreshDirty);
  modal.querySelector(".ed-add-set").addEventListener("click", onAddNewSet);
  modal.querySelector(".ed-type").addEventListener("change", onTypeChange);
  modal.querySelector(".ed-save").addEventListener("click", doSave);
  return modal;
}

function _ensure() {
  if (!_modal) _modal = _build();
  return _modal;
}

function close() {
  // Nothing is auto-persisted, so warn before throwing away unsaved edits.
  if (_state && isDirty()
      && !window.confirm("Discard unsaved changes?")) return;
  if (_modal) _modal.classList.remove("open");
  _state = null;
  document.removeEventListener("keydown", _onKey);
}

function _onKey(e) {
  if (!_state) return;
  if (e.key === "Escape") { close(); return; }
  if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
  // While the name field is focused, let arrows move the text caret instead
  // of navigating cards.
  const ae = document.activeElement;
  if (ae && ae.classList && ae.classList.contains("ed-name")) return;
  // preventDefault so the same keystroke can't ALSO mutate a focused control
  // (e.g. the Type <select>, where arrows silently change the selection and
  // would write that change onto every card you scroll past).
  e.preventDefault();
  move(e.key === "ArrowRight" ? +1 : -1);
}

function setStatus(text, kind) {
  const el = _modal.querySelector(".ed-status");
  el.textContent = text;
  el.dataset.kind = kind || "";
}

function move(delta) {
  const next = _state.index + delta;
  if (next < 0 || next >= _state.cards.length) return;
  // Don't silently drop edits when paging to another card.
  if (isDirty() && !window.confirm("Discard unsaved changes?")) return;
  _state.index = next;
  loadCurrent();
}

function loadCurrent() {
  const card = _state.cards[_state.index];
  const m = _modal;
  m.querySelector(".ed-id").textContent = card.id;
  m.querySelector(".ed-pos").textContent = `${_state.index + 1} / ${_state.cards.length}`;
  m.querySelector(".editor-image img").src =
    `/api/card/${encodeURIComponent(card.id)}/view`;

  m.querySelector(".ed-name").value = card.name || "";

  populateSet(card.set || []);
  populateType(card.type || "");
  populateElement(card.element || []);
  toggleElementBlock(card.type);

  m.querySelector(".prev").disabled = _state.index === 0;
  m.querySelector(".next").disabled = _state.index === _state.cards.length - 1;
  setStatus("", "");
  refreshDirty();  // freshly loaded form matches stored card → Save disabled
}

function populateSet(currentList) {
  const box = _modal.querySelector(".ed-set-rows");
  box.innerHTML = "";
  const checked = new Set(currentList);
  // Show every vocab set plus any set the card already has that's not in
  // vocab yet (e.g. just-added one being shown for the first time).
  const allSets = _state.vocab.sets.slice();
  for (const s of currentList) {
    if (s && !allSets.includes(s)) allSets.push(s);
  }
  for (const s of allSets) {
    const wrap = document.createElement("label");
    wrap.className = "ed-set-row";
    const cb = document.createElement("input");
    cb.type = "checkbox"; cb.value = s; cb.checked = checked.has(s);
    cb.addEventListener("change", refreshDirty);
    const txt = document.createElement("span"); txt.textContent = s;
    wrap.appendChild(cb); wrap.appendChild(txt);
    box.appendChild(wrap);
  }
}

function onAddNewSet() {
  const name = (window.prompt("New set name:") || "").trim();
  if (!name) return;
  if (!_state.vocab.sets.includes(name)) {
    _state.vocab.sets.push(name);
  }
  // Re-render with this set checked, preserving everything else.
  const current = readForm().set;
  if (!current.includes(name)) current.push(name);
  populateSet(current);
  refreshDirty();
}

function populateType(currentType) {
  const sel = _modal.querySelector(".ed-type");
  sel.innerHTML = "";
  const blank = document.createElement("option");
  blank.value = ""; blank.textContent = "—";
  sel.appendChild(blank);
  for (const t of _state.vocab.types) {
    const o = document.createElement("option"); o.value = t; o.textContent = t;
    sel.appendChild(o);
  }
  if (currentType && !_state.vocab.types.includes(currentType)) {
    const o = document.createElement("option");
    o.value = currentType; o.textContent = currentType + " (off-vocab)";
    sel.appendChild(o);
  }
  sel.value = currentType || "";
}

function populateElement(currentList) {
  const box = _modal.querySelector(".ed-element-chips");
  box.innerHTML = "";
  const set = new Set(currentList.map(e => e.toLowerCase()));
  for (const el of _state.vocab.elements) {
    const wrap = document.createElement("label");
    wrap.className = "ed-element-row";
    const cb = document.createElement("input");
    cb.type = "checkbox"; cb.value = el; cb.checked = set.has(el);
    cb.addEventListener("change", refreshDirty);
    const txt = document.createElement("span");
    txt.textContent = el.charAt(0).toUpperCase() + el.slice(1);
    wrap.appendChild(cb); wrap.appendChild(txt);
    box.appendChild(wrap);
  }
}

function toggleElementBlock(type) {
  const block = _modal.querySelector(".ed-element-block");
  const hide = type === "Command" || type === "Skill";
  block.style.display = hide ? "none" : "";
  if (hide) {
    for (const cb of _modal.querySelectorAll(".ed-element-chips input")) {
      cb.checked = false;
    }
  }
}

function onTypeChange(e) {
  toggleElementBlock(e.target.value);
  refreshDirty();
}

function readForm() {
  const m = _modal;
  const elements = Array.from(
    m.querySelectorAll(".ed-element-chips input:checked"),
    cb => cb.value
  );
  const sets = Array.from(
    m.querySelectorAll(".ed-set-rows input:checked"),
    cb => cb.value
  );
  return {
    name: m.querySelector(".ed-name").value.trim(),
    set: sets,
    type: m.querySelector(".ed-type").value,
    element: elements,
  };
}

// True when the form differs from the stored card. Nothing is persisted on
// edit, so this drives the Save button's enabled state and the discard guards.
function isDirty() {
  if (!_state) return false;
  const card = _state.cards[_state.index];
  return _normalizeLabel(card) !== _normalizeLabel(readForm());
}

// Reflect the current dirty state into the Save button + status hint. Never
// clobbers an in-flight "Saving…" or a terminal "Saved ✓"/"Save failed".
function refreshDirty() {
  if (!_state) return;
  const dirty = isDirty();
  _modal.querySelector(".ed-save").disabled = !dirty;
  const kind = _modal.querySelector(".ed-status").dataset.kind;
  if (kind === "saving") return;
  if (dirty) setStatus("Unsaved changes", "dirty");
  else if (kind === "dirty") setStatus("", "");
}

// Normalize a label into the canonical shape the server persists, so we can
// compare the form against the stored card and skip no-op writes. Mirrors
// catalog.save_label: trim name, dedupe + sort sets, drop elements for
// element-less types, otherwise lowercase + dedupe + sort elements. (Sets are
// sorted only for this comparison; the editor can't reorder them anyway.)
const _TYPES_WITHOUT_ELEMENT = new Set(["Command", "Skill"]);
function _normalizeLabel(label) {
  const name = (label.name || "").trim();
  const set = [];
  for (let s of (label.set || [])) {
    s = (s || "").trim();
    if (s && !set.includes(s)) set.push(s);
  }
  // Sets are presented as order-independent checkboxes, so compare them
  // order-insensitively — otherwise a card stored in a different order than
  // the vocab render order would look "changed" the moment it loads.
  set.sort();
  const type = (label.type || "").trim();
  let element = [];
  if (!_TYPES_WITHOUT_ELEMENT.has(type)) {
    const seen = new Set();
    for (let el of (label.element || [])) {
      el = (el || "").trim().toLowerCase();
      if (el) seen.add(el);
    }
    element = Array.from(seen).sort();
  }
  return JSON.stringify({ name, set, type, element });
}

// The ONLY path that writes metadata. Invoked solely by the Save button.
async function doSave() {
  if (!_state) return;
  // Capture the target card up-front; navigation can move _state.index
  // before the fetch resolves, and we must not let the response land on
  // the wrong card.
  const savedIndex = _state.index;
  const card = _state.cards[savedIndex];
  const cardId = card.id;
  const payload = readForm();
  // The button is only enabled when dirty, but double-check so a stray call
  // can never rewrite the shared labels file with identical data.
  if (_normalizeLabel(card) === _normalizeLabel(payload)) return;
  const btn = _modal.querySelector(".ed-save");
  btn.disabled = true;
  setStatus("Saving…", "saving");
  try {
    const res = await fetch(`/api/labels/${encodeURIComponent(cardId)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error("HTTP " + res.status);
    const updated = await res.json();
    if (!_state) return;  // modal closed mid-save; server still recorded it
    _state.cards[savedIndex] = updated;
    if (_state.onSave) _state.onSave(updated);
    // Only touch the visible status/button if we're still on the saved card.
    if (_state.index === savedIndex) {
      setStatus("Saved ✓", "saved");
      refreshDirty();  // now clean → keeps Save disabled
    }
  } catch (err) {
    if (_state && _state.index === savedIndex) {
      setStatus("Save failed: " + err.message, "error");
      btn.disabled = false;  // let the user retry
    }
  }
}

async function openEditor(cards, index, opts) {
  opts = opts || {};
  const modal = _ensure();
  const vocab = await opts.getVocab();
  _state = {
    cards: cards.slice(),
    index,
    vocab,
    onSave: opts.onSave,
  };
  modal.classList.add("open");
  document.addEventListener("keydown", _onKey);
  loadCurrent();
  // Intentionally do NOT autofocus the name field: it's a text input, so
  // focusing it would capture the arrow keys (caret movement) and block the
  // open-then-arrow-to-browse flow. Click the field when you want to edit.
}

// Tiny memoized vocab fetcher; pages can pass this as opts.getVocab.
let _vocabPromise = null;
function fetchVocab() {
  if (!_vocabPromise) {
    _vocabPromise = fetch("/api/vocab").then(r => r.json());
  }
  return _vocabPromise;
}
