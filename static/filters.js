// Shared filter pipeline for the card grid (used by cards.html and deck.html).
//
// A card has the shape: { id, set, name, element, type } where any of
// set/name/element/type may be null when the card is unlabeled.

function buildChipRows(meta) {
  return {
    set: meta.sets || [],
    element: meta.elements || [],
    type: meta.types || [],
  };
}

// state = { selectedSets, selectedElements, selectedTypes: Set<string lowercase>,
//           search: string, hideUnlabeled: bool }
function cardPasses(card, state) {
  if (state.hideUnlabeled && !card.name && !card.set) return false;

  if (state.selectedSets.size && !state.selectedSets.has((card.set || "").toLowerCase())) return false;
  if (state.selectedElements.size
      && !state.selectedElements.has((card.element || "").toLowerCase())) return false;
  if (state.selectedTypes.size
      && !state.selectedTypes.has((card.type || "").toLowerCase())) return false;

  const q = (state.search || "").trim().toLowerCase();
  if (q) {
    const hay = `${card.id} ${card.name || ""}`.toLowerCase();
    if (!hay.includes(q)) return false;
  }
  return true;
}

function renderChipRow(container, label, values, selected, onToggle) {
  container.innerHTML = "";
  if (!values.length) {
    container.innerHTML = `<span class="chip-empty">${label}: —</span>`;
    return;
  }
  const lbl = document.createElement("span");
  lbl.className = "chip-label";
  lbl.textContent = label;
  container.appendChild(lbl);
  for (const v of values) {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "chip" + (selected.has(v.toLowerCase()) ? " on" : "");
    chip.textContent = v;
    chip.addEventListener("click", () => {
      const key = v.toLowerCase();
      if (selected.has(key)) selected.delete(key); else selected.add(key);
      chip.classList.toggle("on");
      onToggle();
    });
    container.appendChild(chip);
  }
}

function renderStandardChips(meta, state, onChange) {
  const chips = buildChipRows(meta);
  state.selectedSets = new Set();
  state.selectedElements = new Set();
  state.selectedTypes = new Set();
  renderChipRow(document.getElementById("chipSet"), "Set",
                chips.set, state.selectedSets, onChange);
  renderChipRow(document.getElementById("chipElement"), "Element",
                chips.element, state.selectedElements, onChange);
  renderChipRow(document.getElementById("chipType"), "Type",
                chips.type, state.selectedTypes, onChange);
}
