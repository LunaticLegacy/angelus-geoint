/** Registry-driven permission view; changes update a profile draft through an intent. */
export function renderToolPermissions(host, catalog, policy, onChange) {
  host.replaceChildren();
  for (const group of catalog.categories || []) {
    const section = document.createElement('section'); section.className = 'tool-category';
    const label = document.createElement('label'); label.className = 'tool-category-toggle';
    const toggle = document.createElement('input'); toggle.type = 'checkbox';
    toggle.checked = policy.categories?.[group.id] === true;
    const title = document.createElement('strong'); title.textContent = group.title || group.id;
    label.append(toggle, title); section.append(label);
    const items = document.createElement('div'); items.className = 'tool-items'; items.hidden = !toggle.checked;
    const change = (id, enabled, category = false) => {
      const next = { categories: { ...policy.categories }, tools: { ...policy.tools } };
      if (category) { next.categories[id] = enabled; for (const tool of group.tools || []) next.tools[tool.id] = enabled; }
      else next.tools[id] = enabled;
      onChange(next);
    };
    toggle.onchange = () => change(group.id, toggle.checked, true);
    for (const tool of group.tools || []) {
      const row = document.createElement('label'); row.className = 'tool-toggle'; row.title = tool.description || '';
      const checkbox = document.createElement('input'); checkbox.type = 'checkbox'; checkbox.checked = policy.tools?.[tool.id] === true;
      checkbox.onchange = () => change(tool.id, checkbox.checked);
      const text = document.createElement('span'); text.textContent = tool.title || tool.id;
      row.append(checkbox, text); items.append(row);
    }
    section.append(items); host.append(section);
  }
  if (!host.children.length) host.textContent = '当前后端未注册工具。';
}
