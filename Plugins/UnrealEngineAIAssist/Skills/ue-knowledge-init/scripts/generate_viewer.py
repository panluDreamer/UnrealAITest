#!/usr/bin/env python3
"""Generate a self-contained HTML viewer for the UE module knowledge graph.

Reads module_graph.json, submodule_index.json, and all .md summaries,
then embeds everything into a single static HTML file that works with file:// protocol.

Usage:
    python generate_viewer.py [--knowledge-dir PATH] [--output PATH]
"""

import json
import os
import sys
import glob
import argparse

def find_knowledge_dir():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    plugin_dir = os.path.abspath(os.path.join(script_dir, '..', '..', '..'))
    knowledge_dir = os.path.join(plugin_dir, 'Knowledge')
    if os.path.isdir(knowledge_dir):
        return knowledge_dir
    return None

def load_module_graph(knowledge_dir):
    path = os.path.join(knowledge_dir, 'module_graph.json')
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    compact = {}
    for name, mod in data.get('modules', {}).items():
        compact[name] = {
            't': mod.get('type', 'Runtime'),
            'l': mod.get('layer', 0),
            'p': mod.get('path', ''),
            'pd': mod.get('public_deps', []),
            'vd': mod.get('private_deps', []),
            'cd': mod.get('circular_deps', []),
        }
    return compact

def load_submodule_index(knowledge_dir):
    path = os.path.join(knowledge_dir, 'submodule_index.json')
    if not os.path.exists(path):
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    result = {}
    for name, info in data.get('modules', {}).items():
        result[name] = info.get('submodules', [])
    return result

def load_summaries(knowledge_dir):
    summaries = {}
    modules_dir = os.path.join(knowledge_dir, 'modules')
    for md_file in glob.glob(os.path.join(modules_dir, '*.md')):
        name = os.path.splitext(os.path.basename(md_file))[0]
        with open(md_file, 'r', encoding='utf-8') as f:
            summaries[name] = f.read()
    for sub_dir in os.listdir(modules_dir):
        sub_path = os.path.join(modules_dir, sub_dir)
        if not os.path.isdir(sub_path):
            continue
        for md_file in glob.glob(os.path.join(sub_path, '*.md')):
            sub_name = os.path.splitext(os.path.basename(md_file))[0]
            key = f"{sub_dir}/{sub_name}"
            with open(md_file, 'r', encoding='utf-8') as f:
                summaries[key] = f.read()
    return summaries

def compute_reverse_deps(module_graph):
    """Compute which modules depend on each module (reverse index)."""
    rdeps = {}
    for name, mod in module_graph.items():
        for dep in mod['pd'] + mod['vd']:
            if dep not in rdeps:
                rdeps[dep] = []
            rdeps[dep].append(name)
    return rdeps

def generate_html(module_graph, submodule_index, summaries):
    summarized = sorted([k for k in summaries.keys() if '/' not in k])
    rdeps = compute_reverse_deps(module_graph)

    graph_json = json.dumps(module_graph, ensure_ascii=False, separators=(',', ':'))
    submod_json = json.dumps(submodule_index, ensure_ascii=False, separators=(',', ':'))
    summaries_json = json.dumps(summaries, ensure_ascii=False)
    summarized_json = json.dumps(summarized, ensure_ascii=False)
    rdeps_json = json.dumps(rdeps, ensure_ascii=False, separators=(',', ':'))

    # The HTML template uses {{ and }} for literal braces in CSS/JS,
    # and {variable} for Python f-string interpolation
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>UE Module Knowledge Graph</title>
<script src="https://cdn.jsdelivr.net/npm/marked@12.0.0/marked.min.js"></script>
<style>
@import url('https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,300;8..60,400;8..60,600;8..60,700&family=DM+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');

:root {{
  --bg: #F9F8F6;
  --surface: #FFFFFF;
  --border: #E8E5E0;
  --border-light: #F0EDE8;
  --text: #1B1B18;
  --text-secondary: #7C7C72;
  --text-tertiary: #A8A89E;
  --accent: #C7502E;
  --accent-light: #FDF2EE;
  --accent-hover: #A8401F;
  --blue: #2B5EA7;
  --blue-light: #EEF3FB;
  --green: #3D7A4A;
  --green-light: #EDF6EF;
  --purple: #6B4C9A;
  --purple-light: #F3EFF8;
  --orange: #B8601A;
  --orange-light: #FFF5EC;
  --gray: #8B8B80;
  --gray-light: #F3F2F0;
  --serif: 'Source Serif 4', Georgia, 'Times New Roman', serif;
  --sans: 'DM Sans', system-ui, -apple-system, sans-serif;
  --mono: 'JetBrains Mono', 'Consolas', monospace;
  --radius: 12px;
  --radius-sm: 8px;
  --shadow: 0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04);
  --shadow-lg: 0 4px 12px rgba(0,0,0,0.08), 0 1px 3px rgba(0,0,0,0.06);
}}

* {{ margin: 0; padding: 0; box-sizing: border-box; }}
html {{ scroll-behavior: smooth; }}
body {{
  font-family: var(--sans);
  background: var(--bg);
  color: var(--text);
  line-height: 1.6;
  -webkit-font-smoothing: antialiased;
}}

/* ── Header ── */
header {{
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  padding: 20px 0;
  position: sticky; top: 0; z-index: 50;
}}
.header-inner {{
  max-width: 1200px; margin: 0 auto; padding: 0 32px;
  display: flex; align-items: center; justify-content: space-between;
}}
.logo {{
  font-family: var(--serif); font-size: 22px; font-weight: 600;
  color: var(--text); text-decoration: none; letter-spacing: -0.02em;
}}
.logo span {{ color: var(--accent); }}
.back-btn {{
  display: none; align-items: center; gap: 6px;
  font-size: 14px; color: var(--text-secondary); text-decoration: none;
  cursor: pointer; padding: 6px 12px; border-radius: var(--radius-sm);
  border: 1px solid var(--border); background: var(--surface);
  transition: all 0.15s;
}}
.back-btn:hover {{ border-color: var(--accent); color: var(--accent); }}
.back-btn svg {{ width: 16px; height: 16px; }}

#search-box {{
  font-family: var(--sans); font-size: 15px; padding: 10px 16px 10px 40px;
  border: 1px solid var(--border); border-radius: var(--radius);
  background: var(--bg); width: 320px; outline: none;
  transition: border-color 0.15s, box-shadow 0.15s;
}}
#search-box:focus {{
  border-color: var(--accent);
  box-shadow: 0 0 0 3px rgba(199,80,46,0.1);
}}
.search-wrap {{
  position: relative;
}}
.search-wrap svg {{
  position: absolute; left: 14px; top: 50%; transform: translateY(-50%);
  width: 16px; height: 16px; color: var(--text-tertiary);
}}

/* ── Content ── */
.container {{ max-width: 1200px; margin: 0 auto; padding: 0 32px; }}

/* ── Home Page ── */
#home-page {{ padding: 40px 0 80px; }}

.hero {{
  margin-bottom: 40px;
}}
.hero h1 {{
  font-family: var(--serif); font-size: 36px; font-weight: 600;
  letter-spacing: -0.03em; color: var(--text); margin-bottom: 8px;
}}
.hero p {{
  font-size: 16px; color: var(--text-secondary); max-width: 600px;
}}

/* Tabs */
.tabs {{
  display: flex; gap: 4px; margin-bottom: 28px;
  border-bottom: 1px solid var(--border); padding-bottom: -1px;
}}
.tab {{
  padding: 10px 18px; font-size: 14px; font-weight: 500;
  color: var(--text-secondary); cursor: pointer; border: none; background: none;
  border-bottom: 2px solid transparent; transition: all 0.15s;
  font-family: var(--sans);
}}
.tab:hover {{ color: var(--text); }}
.tab.active {{
  color: var(--accent); border-bottom-color: var(--accent);
}}
.tab .count {{
  font-size: 12px; color: var(--text-tertiary); margin-left: 4px;
}}

/* Card Grid */
.card-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 16px;
}}
.card {{
  background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 20px; cursor: pointer;
  transition: all 0.2s ease;
  text-decoration: none; color: inherit; display: block;
}}
.card:hover {{
  border-color: var(--accent);
  box-shadow: var(--shadow-lg);
  transform: translateY(-1px);
}}
.card-name {{
  font-family: var(--serif); font-size: 18px; font-weight: 600;
  color: var(--text); margin-bottom: 8px; letter-spacing: -0.01em;
}}
.card-meta {{
  display: flex; gap: 8px; align-items: center; flex-wrap: wrap;
}}
.tag {{
  display: inline-flex; align-items: center; padding: 3px 10px;
  border-radius: 20px; font-size: 12px; font-weight: 500;
}}
.tag-Runtime {{ background: var(--blue-light); color: var(--blue); }}
.tag-Editor {{ background: var(--green-light); color: var(--green); }}
.tag-Plugin {{ background: var(--orange-light); color: var(--orange); }}
.tag-Developer {{ background: var(--purple-light); color: var(--purple); }}
.tag-ThirdParty {{ background: var(--gray-light); color: var(--gray); }}
.tag-Program {{ background: var(--gray-light); color: var(--gray); }}
.tag-layer {{ background: var(--bg); color: var(--text-secondary); font-size: 11px; }}
.card-desc {{
  margin-top: 10px; font-size: 13px; color: var(--text-secondary);
  line-height: 1.5; display: -webkit-box; -webkit-line-clamp: 2;
  -webkit-box-orient: vertical; overflow: hidden;
}}
.card-footer {{
  margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--border-light);
  font-size: 12px; color: var(--text-tertiary);
  display: flex; gap: 12px;
}}

/* ── Detail Page ── */
#detail-page {{ display: none; padding: 40px 0 80px; }}

.detail-header {{
  margin-bottom: 32px;
}}
.detail-header h1 {{
  font-family: var(--serif); font-size: 32px; font-weight: 600;
  letter-spacing: -0.03em; margin-bottom: 10px;
}}
.detail-header .meta-row {{
  display: flex; gap: 10px; align-items: center; flex-wrap: wrap;
}}
.detail-header .path {{
  font-family: var(--mono); font-size: 13px; color: var(--text-tertiary);
  margin-top: 6px;
}}

/* Dep Graph */
.dep-graph-section {{
  background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 24px; margin-bottom: 32px;
}}
.dep-graph-section h3 {{
  font-family: var(--sans); font-size: 13px; font-weight: 600;
  color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.05em;
  margin-bottom: 16px;
}}
.dep-graph {{
  display: flex; flex-direction: column; align-items: center; gap: 20px;
}}
.dep-row {{
  display: flex; gap: 10px; flex-wrap: wrap; justify-content: center;
}}
.dep-node {{
  padding: 6px 14px; border-radius: var(--radius-sm); font-size: 13px;
  font-weight: 500; cursor: pointer; border: 1px solid var(--border);
  background: var(--surface); color: var(--text); transition: all 0.15s;
  text-decoration: none; white-space: nowrap;
}}
.dep-node:hover {{ border-color: var(--accent); color: var(--accent); transform: translateY(-1px); box-shadow: var(--shadow); }}
.dep-node.has-summary {{ font-weight: 600; }}
.dep-node.center {{
  background: var(--accent); color: white; border-color: var(--accent);
  font-size: 15px; padding: 8px 20px; cursor: default;
}}
.dep-node.center:hover {{ transform: none; box-shadow: none; }}
.dep-label {{
  font-size: 11px; color: var(--text-tertiary); text-transform: uppercase;
  letter-spacing: 0.08em; text-align: center;
}}
.dep-arrow {{
  color: var(--text-tertiary); font-size: 18px; text-align: center;
}}

/* Summary Content */
.summary-section {{
  background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 32px; margin-bottom: 32px;
}}
.md-content {{ font-family: var(--sans); font-size: 15px; line-height: 1.7; color: var(--text); }}
.md-content h1 {{ font-family: var(--serif); font-size: 24px; font-weight: 600; margin: 28px 0 12px; letter-spacing: -0.02em; color: var(--text); border-bottom: 1px solid var(--border-light); padding-bottom: 8px; }}
.md-content h1:first-child {{ margin-top: 0; }}
.md-content h2 {{ font-family: var(--serif); font-size: 19px; font-weight: 600; margin: 24px 0 10px; color: var(--text); }}
.md-content h3 {{ font-size: 15px; font-weight: 600; margin: 18px 0 6px; color: var(--text-secondary); }}
.md-content p {{ margin: 8px 0; }}
.md-content ul, .md-content ol {{ padding-left: 24px; margin: 8px 0; }}
.md-content li {{ margin: 4px 0; }}
.md-content code {{
  font-family: var(--mono); font-size: 13px;
  background: var(--bg); padding: 2px 6px; border-radius: 4px;
  color: var(--accent); border: 1px solid var(--border-light);
}}
.md-content pre {{
  background: #1B1B18; color: #E8E5E0; padding: 16px 20px;
  border-radius: var(--radius-sm); overflow-x: auto; margin: 12px 0;
  font-size: 13px; line-height: 1.5;
}}
.md-content pre code {{
  background: none; border: none; padding: 0; color: inherit;
}}
.md-content strong {{ color: var(--text); font-weight: 600; }}
.md-content a {{ color: var(--blue); text-decoration: underline; text-underline-offset: 2px; }}
.md-content hr {{ border: none; border-top: 1px solid var(--border-light); margin: 20px 0; }}

/* Submodule Grid */
.submodules-section {{
  margin-bottom: 32px;
}}
.submodules-section h3 {{
  font-family: var(--sans); font-size: 13px; font-weight: 600;
  color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.05em;
  margin-bottom: 14px;
}}
.sub-grid {{
  display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 10px;
}}
.sub-chip {{
  padding: 10px 14px; background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius-sm); cursor: pointer; transition: all 0.15s;
  font-size: 14px; font-weight: 500; color: var(--text);
}}
.sub-chip:hover {{ border-color: var(--accent); color: var(--accent); box-shadow: var(--shadow); }}
.sub-chip.active {{ border-color: var(--accent); background: var(--accent-light); color: var(--accent); }}

/* Sub detail */
#sub-detail {{
  background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 32px; margin-bottom: 32px;
  display: none;
}}
#sub-detail.open {{ display: block; }}

/* Responsive */
@media (max-width: 768px) {{
  .header-inner {{ padding: 0 16px; }}
  .container {{ padding: 0 16px; }}
  #search-box {{ width: 200px; }}
  .hero h1 {{ font-size: 28px; }}
  .card-grid {{ grid-template-columns: 1fr; }}
}}

/* No-summary indicator */
.no-summary {{
  padding: 32px; text-align: center; color: var(--text-tertiary);
  font-style: italic;
}}

/* Transition */
.fade-in {{
  animation: fadeIn 0.3s ease;
}}
@keyframes fadeIn {{
  from {{ opacity: 0; transform: translateY(8px); }}
  to {{ opacity: 1; transform: translateY(0); }}
}}

/* Tier Sections */
.tier-section {{
  margin-bottom: 36px;
}}
.tier-header {{
  display: flex; align-items: center; gap: 10px; margin-bottom: 16px;
}}
.tier-header h2 {{
  font-family: var(--serif); font-size: 20px; font-weight: 600;
  color: var(--text); letter-spacing: -0.01em;
}}
.tier-header .tier-desc {{
  font-size: 13px; color: var(--text-tertiary);
}}
.expand-btn {{
  display: inline-flex; align-items: center; gap: 6px;
  font-family: var(--sans); font-size: 14px; font-weight: 500;
  color: var(--accent); background: var(--accent-light);
  border: 1px solid rgba(199,80,46,0.2); border-radius: var(--radius-sm);
  padding: 8px 18px; cursor: pointer; transition: all 0.15s;
  margin-top: 8px;
}}
.expand-btn:hover {{
  background: var(--accent); color: white; border-color: var(--accent);
}}
.expand-btn svg {{
  width: 14px; height: 14px; transition: transform 0.2s;
}}
.expand-btn.expanded svg {{
  transform: rotate(180deg);
}}
</style>
</head>
<body>

<header>
  <div class="header-inner">
    <div style="display:flex;align-items:center;gap:16px;">
      <a class="back-btn" id="back-btn" onclick="navigateTo('')">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
        Back
      </a>
      <a class="logo" onclick="navigateTo('')" style="cursor:pointer">
        UE Module <span>Knowledge</span>
      </a>
    </div>
    <div class="search-wrap">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
      <input type="text" id="search-box" placeholder="Search modules..." oninput="onSearch()">
    </div>
  </div>
</header>

<div id="home-page" class="container">
  <div class="hero">
    <h1>Module Knowledge Graph</h1>
    <p id="hero-stats"></p>
  </div>

  <div class="tabs" id="tabs"></div>
  <div id="card-sections"></div>
</div>

<div id="detail-page" class="container">
  <div id="detail-content"></div>
</div>

<script>
// ═══════════════════════ EMBEDDED DATA ═══════════════════════
const G={graph_json};
const SI={submod_json};
const S={summaries_json};
const SM={summarized_json};
const RD={rdeps_json};
</script>

<script>
// ═══════════════════════ APPLICATION ═══════════════════════

const SUMMARIZED_SET = new Set(SM);
let currentTab = 'documented';
let searchQuery = '';

// ── Helpers ──
function getTypeColor(t) {{
  return {{Runtime:'blue',Editor:'green',Plugin:'orange',Developer:'purple',ThirdParty:'gray',Program:'gray'}}[t]||'gray';
}}

function extractPurpose(md) {{
  if (!md) return '';
  const m = md.match(/##\\s*Purpose\\n+([^\\n]+)/);
  return m ? m[1].trim() : '';
}}

// ── Routing ──
function navigateTo(hash) {{
  window.location.hash = hash ? '#/' + hash : '#/';
}}

function handleRoute() {{
  const hash = window.location.hash.replace('#/', '').replace('#', '');
  const parts = hash.split('/');

  if (!hash || hash === '') {{
    showHome();
  }} else if (parts.length === 1) {{
    showDetail(parts[0]);
  }} else if (parts.length === 2) {{
    showDetail(parts[0], parts[1]);
  }}
}}
window.addEventListener('hashchange', handleRoute);

// ── Home Page ──
function showHome() {{
  document.getElementById('home-page').style.display = 'block';
  document.getElementById('detail-page').style.display = 'none';
  document.getElementById('back-btn').style.display = 'none';

  const totalMods = Object.keys(G).length;
  const docMods = SM.length;
  const totalSubs = Object.values(SI).reduce((a, b) => a + b.length, 0);
  document.getElementById('hero-stats').textContent =
    `${{totalMods}} modules in graph \u00b7 ${{docMods}} documented \u00b7 ${{totalSubs}} submodules`;

  renderTabs();
  renderCards();
}}

function renderTabs() {{
  const types = {{}};
  SM.forEach(name => {{
    const t = G[name]?.t || 'Runtime';
    types[t] = (types[t] || 0) + 1;
  }});

  let html = `<button class="tab ${{currentTab === 'documented' ? 'active' : ''}}" onclick="setTab('documented')">All Documented<span class="count">${{SM.length}}</span></button>`;

  for (const [t, count] of Object.entries(types).sort((a,b) => b[1]-a[1])) {{
    html += `<button class="tab ${{currentTab === t ? 'active' : ''}}" onclick="setTab('${{t}}')">${{t}}<span class="count">${{count}}</span></button>`;
  }}

  document.getElementById('tabs').innerHTML = html;
}}

function setTab(tab) {{
  currentTab = tab;
  renderTabs();
  renderCards();
}}

const TIER1 = new Set(['Core','CoreUObject','Engine','RHI','RenderCore','Renderer','ApplicationCore','SlateCore','Slate','InputCore']);
const TIER2 = new Set(['NavigationSystem','AIModule','PhysicsCore','Chaos','AnimationCore','AnimGraphRuntime','Landscape','Niagara','UMG','MovieScene']);
let showOther = false;

function renderCards() {{
  let modules = SM.filter(name => {{
    const mod = G[name];
    if (!mod) return false;
    if (currentTab !== 'documented' && mod.t !== currentTab) return false;
    if (searchQuery && !name.toLowerCase().includes(searchQuery)) return false;
    return true;
  }});

  modules.sort((a, b) => {{
    const la = G[a]?.l || 0, lb = G[b]?.l || 0;
    if (la !== lb) return la - lb;
    return a.localeCompare(b);
  }});

  const tier1 = modules.filter(n => TIER1.has(n));
  const tier2 = modules.filter(n => TIER2.has(n));
  const other = modules.filter(n => !TIER1.has(n) && !TIER2.has(n));

  // If searching, show everything flat
  if (searchQuery) {{
    let html = '<div class="card-grid">';
    for (const name of modules) html += renderCard(name);
    html += '</div>';
    if (!modules.length) html = '<div class="no-summary">No modules match your search.</div>';
    document.getElementById('card-sections').innerHTML = html;
    return;
  }}

  let html = '';

  if (tier1.length) {{
    html += `<div class="tier-section">
      <div class="tier-header"><h2>Core Infrastructure</h2><span class="tier-desc">Tier 1 \u2014 foundation modules everything depends on</span></div>
      <div class="card-grid">${{tier1.map(renderCard).join('')}}</div>
    </div>`;
  }}

  if (tier2.length) {{
    html += `<div class="tier-section">
      <div class="tier-header"><h2>Key Systems</h2><span class="tier-desc">Tier 2 \u2014 gameplay, physics, animation, particles, UI</span></div>
      <div class="card-grid">${{tier2.map(renderCard).join('')}}</div>
    </div>`;
  }}

  if (other.length) {{
    html += `<div class="tier-section">
      <button class="expand-btn ${{showOther ? 'expanded' : ''}}" onclick="toggleOther()">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 9l6 6 6-6"/></svg>
        ${{showOther ? 'Hide' : 'Show'}} ${{other.length}} more modules (Editor, Tools, Utilities)
      </button>
      ${{showOther ? '<div class="card-grid" style="margin-top:16px">' + other.map(renderCard).join('') + '</div>' : ''}}
    </div>`;
  }}

  if (!html) html = '<div class="no-summary">No modules match the current filter.</div>';
  document.getElementById('card-sections').innerHTML = html;
}}

function renderCard(name) {{
  const mod = G[name];
  const subs = SI[name] || [];
  const purpose = extractPurpose(S[name]);
  const depCount = mod.pd.length + mod.vd.length;
  const rdepCount = (RD[name] || []).length;

  return `
    <div class="card" onclick="navigateTo('${{name}}')">
      <div class="card-name">${{name}}</div>
      <div class="card-meta">
        <span class="tag tag-${{mod.t}}">${{mod.t}}</span>
        <span class="tag tag-layer">Layer ${{mod.l}}</span>
      </div>
      ${{purpose ? `<div class="card-desc">${{purpose}}</div>` : ''}}
      <div class="card-footer">
        <span>${{depCount}} deps</span>
        <span>${{rdepCount}} dependents</span>
        ${{subs.length ? `<span>${{subs.length}} submodules</span>` : ''}}
      </div>
    </div>
  `;
}}

function toggleOther() {{
  showOther = !showOther;
  renderCards();
}}

function onSearch() {{
  searchQuery = document.getElementById('search-box').value.toLowerCase();
  const hash = window.location.hash.replace('#/', '').replace('#', '');
  if (!hash) {{
    renderCards();
  }}
}}

// ── Detail Page ──
function showDetail(moduleName, subName) {{
  document.getElementById('home-page').style.display = 'none';
  document.getElementById('detail-page').style.display = 'block';
  document.getElementById('back-btn').style.display = 'flex';

  const mod = G[moduleName];
  if (!mod) {{
    document.getElementById('detail-content').innerHTML = '<div class="no-summary">Module not found.</div>';
    return;
  }}

  const subs = SI[moduleName] || [];
  const allDeps = [...new Set([...mod.pd, ...mod.vd])];
  const revDeps = (RD[moduleName] || []).slice(0, 20); // limit to 20

  let html = `<div class="fade-in">`;

  // Header
  html += `
    <div class="detail-header">
      <h1>${{moduleName}}</h1>
      <div class="meta-row">
        <span class="tag tag-${{mod.t}}">${{mod.t}}</span>
        <span class="tag tag-layer">Layer ${{mod.l}}</span>
        <span class="tag tag-layer">${{mod.pd.length}} public + ${{mod.vd.length}} private deps</span>
        ${{mod.cd.length ? '<span class="tag" style="background:#FEE;color:#C44;">Circular: ' + mod.cd.join(', ') + '</span>' : ''}}
      </div>
      <div class="path">${{mod.p}}</div>
    </div>
  `;

  // Dependency graph
  html += `
    <div class="dep-graph-section">
      <h3>Dependencies</h3>
      <div class="dep-graph">
  `;

  if (allDeps.length > 0) {{
    html += `<div class="dep-label">depends on</div><div class="dep-row">`;
    for (const dep of allDeps.sort()) {{
      const hasSummary = SUMMARIZED_SET.has(dep);
      const isPublic = mod.pd.includes(dep);
      html += `<div class="dep-node ${{hasSummary ? 'has-summary' : ''}}" onclick="navigateTo('${{dep}}')" title="${{isPublic ? 'public' : 'private'}} dependency">${{dep}}</div>`;
    }}
    html += `</div>`;
  }}

  html += `<div class="dep-arrow">\u2191</div>`;
  html += `<div class="dep-row"><div class="dep-node center">${{moduleName}}</div></div>`;
  html += `<div class="dep-arrow">\u2193</div>`;

  if (revDeps.length > 0) {{
    html += `<div class="dep-label">used by${{(RD[moduleName]||[]).length > 20 ? ' (showing 20 of ' + (RD[moduleName]||[]).length + ')' : ''}}</div><div class="dep-row">`;
    for (const dep of revDeps.sort()) {{
      const hasSummary = SUMMARIZED_SET.has(dep);
      html += `<div class="dep-node ${{hasSummary ? 'has-summary' : ''}}" onclick="navigateTo('${{dep}}')">${{dep}}</div>`;
    }}
    html += `</div>`;
  }} else {{
    html += `<div class="dep-label" style="color:var(--text-tertiary)">no known dependents</div>`;
  }}

  html += `</div></div>`;

  // Summary
  if (S[moduleName]) {{
    html += `<div class="summary-section"><div class="md-content">${{marked.parse(S[moduleName])}}</div></div>`;
  }} else {{
    html += `<div class="summary-section"><div class="no-summary">No summary available for this module.</div></div>`;
  }}

  // Submodules
  if (subs.length > 0) {{
    html += `
      <div class="submodules-section">
        <h3>Submodules (${{subs.length}})</h3>
        <div class="sub-grid">
          ${{subs.map(s => `<div class="sub-chip ${{subName === s ? 'active' : ''}}" onclick="navigateTo('${{moduleName}}/${{s}}')">${{s}}</div>`).join('')}}
        </div>
      </div>
    `;
  }}

  // Sub detail
  if (subName && S[moduleName + '/' + subName]) {{
    html += `<div id="sub-detail" class="open"><div class="md-content">${{marked.parse(S[moduleName + '/' + subName])}}</div></div>`;
  }}

  html += `</div>`;
  document.getElementById('detail-content').innerHTML = html;

  window.scrollTo(0, 0);

  // If submodule was specified, scroll to it
  if (subName) {{
    const subDetail = document.getElementById('sub-detail');
    if (subDetail) setTimeout(() => subDetail.scrollIntoView({{ behavior: 'smooth' }}), 100);
  }}
}}

// ── Init ──
window.addEventListener('DOMContentLoaded', function() {{
  handleRoute();
}});
</script>
</body>
</html>'''

    return html

def main():
    parser = argparse.ArgumentParser(description='Generate UE Knowledge Graph HTML viewer')
    parser.add_argument('--knowledge-dir', help='Path to Knowledge/ directory')
    parser.add_argument('--output', help='Output HTML file path')
    args = parser.parse_args()

    knowledge_dir = args.knowledge_dir or find_knowledge_dir()
    if not knowledge_dir or not os.path.isdir(knowledge_dir):
        print("Error: Cannot find Knowledge/ directory. Use --knowledge-dir.", file=sys.stderr)
        sys.exit(1)

    output_path = args.output or os.path.join(knowledge_dir, 'index.html')

    print(f"Knowledge dir: {knowledge_dir}")

    print("Loading module graph...")
    module_graph = load_module_graph(knowledge_dir)
    print(f"  {len(module_graph)} modules")

    print("Loading submodule index...")
    submodule_index = load_submodule_index(knowledge_dir)
    print(f"  {len(submodule_index)} modules with submodules")

    print("Loading summaries...")
    summaries = load_summaries(knowledge_dir)
    module_count = sum(1 for k in summaries if '/' not in k)
    sub_count = sum(1 for k in summaries if '/' in k)
    print(f"  {module_count} module summaries, {sub_count} submodule summaries")

    print("Generating HTML...")
    html = generate_html(module_graph, submodule_index, summaries)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)

    size_kb = os.path.getsize(output_path) / 1024
    print(f"\nWrote {output_path}")
    print(f"Size: {size_kb:.0f} KB")
    print(f"\nOpen in browser: file:///{output_path.replace(os.sep, '/')}")

if __name__ == '__main__':
    main()
