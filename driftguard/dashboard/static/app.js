/**
 * DriftGuard Dashboard App
 * Loads analysis.json, powers interactive visualizations using Chart.js and D3.
 */

// Global State
let state = {
  data: null,
  currentCommitIdx: 0,
  isPlaying: false,
  playTimer: null,
  charts: {}
};

// Colors matching CSS tokens
const colors = {
  healthy: '#22d3a0',
  warning: '#f59e0b',
  risk: '#f97316',
  critical: '#ef4444',
  blue: '#6382ff',
  cyan: '#00d4ff',
  purple: '#a855f7',
  muted: '#3d4561',
  textSecondary: '#7b83a6',
  surface: '#0e1117'
};

const getScoreColor = (score) => {
  if (score >= 80) return colors.healthy;
  if (score >= 60) return colors.warning;
  if (score >= 40) return colors.risk;
  return colors.critical;
};

// -----------------------------------------------------------------------------
// Initialization
// -----------------------------------------------------------------------------
async function init() {
  initNavigation();
  
  try {
    const res = await fetch('analysis.json');
    if (!res.ok) throw new Error('Failed to load analysis.json');
    state.data = await res.json();
    
    if (!state.data.reports || state.data.reports.length === 0) {
      document.getElementById('repo-title').textContent = 'No analysis data found';
      return;
    }

    // Prepare UI bounds
    state.currentCommitIdx = state.data.reports.length - 1;
    document.getElementById('repo-title').textContent = 'Repository Analysis';
    document.getElementById('commit-count').textContent = `${state.data.summary.total_commits} commits`;
    
    const slider = document.getElementById('commit-slider');
    slider.max = state.data.reports.length - 1;
    slider.value = state.currentCommitIdx;
    
    // Global charts
    initGlobalCharts();
    
    // Initial Render
    renderCommit(state.currentCommitIdx);
    
    // Event Listeners
    setupEvents();
    
  } catch (err) {
    console.error(err);
    document.getElementById('repo-title').textContent = 'Error loading data';
  }
}

// -----------------------------------------------------------------------------
// Navigation & Events
// -----------------------------------------------------------------------------
function initNavigation() {
  const navItems = document.querySelectorAll('.nav-item');
  const panels = document.querySelectorAll('.panel');
  
  navItems.forEach(item => {
    item.addEventListener('click', (e) => {
      e.preventDefault();
      const targetId = item.getAttribute('data-panel');
      
      navItems.forEach(n => n.classList.remove('active'));
      item.classList.add('active');
      
      panels.forEach(p => {
        p.classList.remove('active');
        if (p.id === `panel-${targetId}`) p.classList.add('active');
      });

      // Special re-renders when panels become visible
      if (targetId === 'graph') renderGraph(state.data.reports[state.currentCommitIdx]);
      if (targetId === 'heatmap') renderHeatmap(state.data.reports[state.currentCommitIdx]);
    });
  });
}

function setupEvents() {
  const slider = document.getElementById('commit-slider');
  slider.addEventListener('input', (e) => {
    pausePlayback();
    renderCommit(parseInt(e.target.value));
  });

  document.getElementById('btn-play').addEventListener('click', startPlayback);
  document.getElementById('btn-pause').addEventListener('click', pausePlayback);
  document.getElementById('btn-reset').addEventListener('click', () => {
    pausePlayback();
    slider.value = state.data.reports.length - 1;
    renderCommit(state.data.reports.length - 1);
  });
  
  document.getElementById('graph-mode').addEventListener('change', () => {
    if (document.getElementById('panel-graph').classList.contains('active')) {
      renderGraph(state.data.reports[state.currentCommitIdx]);
    }
  });
}

// -----------------------------------------------------------------------------
// Playback
// -----------------------------------------------------------------------------
function startPlayback() {
  if (state.isPlaying) return;
  state.isPlaying = true;
  
  if (state.currentCommitIdx >= state.data.reports.length - 1) {
    state.currentCommitIdx = 0; // wrap around
  }
  
  state.playTimer = setInterval(() => {
    state.currentCommitIdx++;
    document.getElementById('commit-slider').value = state.currentCommitIdx;
    renderCommit(state.currentCommitIdx);
    
    if (state.currentCommitIdx >= state.data.reports.length - 1) {
      pausePlayback();
    }
  }, 1000); // 1 second per commit
}

function pausePlayback() {
  state.isPlaying = false;
  if (state.playTimer) clearInterval(state.playTimer);
}

// -----------------------------------------------------------------------------
// Rendering
// -----------------------------------------------------------------------------
function renderCommit(idx) {
  state.currentCommitIdx = idx;
  const commit = state.data.reports[idx];
  if (!commit) return;

  const score = commit.health?.overall_score || commit.overall_score || commit.metrics?.score || 0;
  
  // Topbar
  document.getElementById('slider-sha').textContent = commit.commit_sha;
  const topScoreEl = document.getElementById('top-score');
  topScoreEl.textContent = score.toFixed(1);
  topScoreEl.style.background = `linear-gradient(135deg, ${getScoreColor(score)}, ${colors.blue})`;

  // Timeline UI
  const dBox = document.getElementById('commit-detail-box');
  dBox.innerHTML = `
    <div style="display:flex; justify-content:space-between;">
      <div>
        <div class="cd-sha">${commit.commit_sha}</div>
        <div class="cd-auth">By ${commit.author || 'Unknown'} at ${new Date((commit.timestamp||0)*1000).toLocaleString()}</div>
      </div>
      <div class="cd-score" style="color: ${getScoreColor(score)}">${score.toFixed(1)}</div>
    </div>
    <div class="cd-msg">${(commit.commit_message || '').replace(/\n/g, '<br>')}</div>
  `;

  // Gauges
  const h = commit.health || {};
  drawGauge('gauge-canvas-overall', 'gauge-val-overall', score, 140);
  drawGauge('gauge-canvas-arch', 'gauge-val-arch', h.architecture_score || 0, 100);
  drawGauge('gauge-canvas-complexity', 'gauge-val-complexity', h.complexity_score || 0, 100);
  drawGauge('gauge-canvas-dep', 'gauge-val-dep', h.dependency_score || 0, 100);
  drawGauge('gauge-canvas-evo', 'gauge-val-evo', h.evolution_score || 0, 100);
  drawGauge('gauge-canvas-team', 'gauge-val-team', h.team_score || 0, 100);

  // Stats Row
  renderStats(commit);

  // Hotspots
  renderHotspots(commit);

  // Insights & Recs
  renderInsights(commit);
  renderRecommendations(commit);

  // Forecast
  renderForecast(commit);

  // Visualizations
  if (document.getElementById('panel-graph').classList.contains('active')) {
    renderGraph(commit);
  }
  if (document.getElementById('panel-heatmap').classList.contains('active')) {
    renderHeatmap(commit);
  }
  
  // Highlight point on timeline chart
  updateChartHighlight(idx);
}

// -----------------------------------------------------------------------------
// UI Components
// -----------------------------------------------------------------------------
function drawGauge(canvasId, labelId, val, size) {
  const canvas = document.getElementById(canvasId);
  const label = document.getElementById(labelId);
  if (!canvas || !label) return;
  
  const ctx = canvas.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  canvas.width = size * dpr;
  canvas.height = size * dpr;
  ctx.scale(dpr, dpr);
  canvas.style.width = `${size}px`;
  canvas.style.height = `${size}px`;

  const cx = size / 2;
  const cy = size / 2;
  const r = size * 0.4;
  const lw = size * 0.08;

  ctx.clearRect(0, 0, size, size);
  
  // BG Arc
  ctx.beginPath();
  ctx.arc(cx, cy, r, Math.PI * 0.8, Math.PI * 2.2);
  ctx.strokeStyle = colors.muted;
  ctx.lineWidth = lw;
  ctx.lineCap = 'round';
  ctx.stroke();

  // Value Arc
  const pct = Math.max(0, Math.min(100, val)) / 100;
  const endAngle = Math.PI * 0.8 + (Math.PI * 1.4 * pct);
  
  ctx.beginPath();
  ctx.arc(cx, cy, r, Math.PI * 0.8, endAngle);
  ctx.strokeStyle = getScoreColor(val);
  ctx.lineWidth = lw;
  ctx.lineCap = 'round';
  ctx.stroke();

  label.textContent = val.toFixed(1);
  label.style.color = getScoreColor(val);
}

function renderStats(commit) {
  const row = document.getElementById('stats-row');
  if (!row) return;
  
  const m = commit.metrics || {};
  const c = commit.complexity || {};
  const d = commit.dependency || {};
  const drift = commit.drift || {};

  const stats = [
    { title: 'Modules', val: m.nodes || 0, d: (drift.deltas?.nodes_delta) },
    { title: 'Dependencies', val: m.edges || 0, d: (drift.deltas?.edges_delta) },
    { title: 'Cycles', val: d.circular_dependency_count || 0 },
    { title: 'Duplication', val: `${(c.duplication_percentage||0).toFixed(1)}%` },
    { title: 'Maintainability', val: (c.avg_maintainability||0).toFixed(1) },
    { title: 'Avg Instability', val: (d.avg_instability||0).toFixed(2) }
  ];

  let html = '';
  stats.forEach(s => {
    let deltaHtml = '';
    if (s.d !== undefined && s.d !== 0) {
      const isUp = s.d > 0;
      deltaHtml = `<div class="stat-delta ${isUp?'up':'down'}">${isUp?'+':''}${s.d}</div>`;
    }
    html += `
      <div class="stat-card">
        <div class="stat-title">${s.title}</div>
        <div class="stat-value">${s.val}</div>
        ${deltaHtml}
      </div>
    `;
  });
  row.innerHTML = html;
}

function renderHotspots(commit) {
  const container = document.getElementById('hotspot-list');
  const evo = commit.evolution || {};
  const hotspots = evo.hotspots || [];
  
  if (hotspots.length === 0) {
    container.innerHTML = '<div class="muted">No significant hotspots detected.</div>';
    return;
  }

  let html = '';
  hotspots.forEach((h, i) => {
    const pct = 100 - (i * 15); // visual fake for now since raw score isn't in hotspots array
    html += `
      <div class="hotspot-item">
        <div class="hotspot-rank">#${i+1}</div>
        <div style="flex:1; overflow:hidden; text-overflow:ellipsis;" title="${h}">${h}</div>
        <div class="hotspot-bar" style="width:${Math.max(10, pct)}%"></div>
      </div>
    `;
  });
  container.innerHTML = html;
}

function renderInsights(commit) {
  const insights = commit.insights || [];
  const list = document.getElementById('insights-list');
  const prev = document.getElementById('overview-insights');
  
  const html = insights.map(i => `
    <div class="insight-card ${i.severity}">
      <div class="insight-emoji">${i.emoji || '💡'}</div>
      <div class="insight-body">
        <div class="insight-title">
          <span class="insight-badge ${i.severity}">${i.severity}</span>
          ${i.title}
        </div>
        <div class="insight-detail">${i.detail}</div>
      </div>
    </div>
  `).join('') || '<div class="muted">No insights for this commit.</div>';

  if (list) list.innerHTML = html;
  if (prev) prev.innerHTML = html;
}

function renderRecommendations(commit) {
  const recs = commit.recommendations || [];
  const list = document.getElementById('recommendations-list');
  if (!list) return;

  const html = recs.map((r, i) => `
    <div class="rec-card">
      <div class="rec-priority">${i+1}</div>
      <div>
        <div class="rec-action">${r.action}</div>
        <div class="rec-rationale">${r.rationale}</div>
        <div class="rec-modules">
          ${(r.modules||[]).map(m => `<span class="rec-module-tag">${m}</span>`).join('')}
        </div>
      </div>
      <div class="effort-badge ${r.effort}">${r.effort} EFFORT</div>
    </div>
  `).join('') || '<div class="muted">Architecture is healthy. No refactoring required.</div>';

  list.innerHTML = html;
}

function renderForecast(commit) {
  const f = commit.forecast;
  if (!f) return;

  const fbox = document.getElementById('forecast-box');
  if (fbox) {
    const trendClass = f.is_declining ? 'danger' : 'safe';
    fbox.innerHTML = `
      <div class="forecast-metric">
        <span class="fm-label">Current Trend</span>
        <span class="fm-value ${trendClass}">${f.is_declining ? 'DEGRADING' : 'STABLE'}</span>
      </div>
      <div class="forecast-metric">
        <span class="fm-label">Estimated Time to Collapse</span>
        <span class="fm-value ${f.commits_to_critical !== null ? 'danger' : 'safe'}">${f.commits_to_critical !== null ? f.commits_to_critical + ' commits' : 'Stable'}</span>
      </div>
    `;
  }

  const dz = document.getElementById('danger-zones');
  if (dz) {
    dz.innerHTML = (f.danger_zones || []).map(r => `
      <div class="danger-zone-item">
        <div class="dz-dot"></div>
        <div>${r}</div>
      </div>
    `).join('') || '<div class="muted">No immediate risk factors.</div>';
  }
}

// -----------------------------------------------------------------------------
// Charts (Chart.js)
// -----------------------------------------------------------------------------
Chart.defaults.color = colors.textSecondary;
Chart.defaults.font.family = 'Inter';

function initGlobalCharts() {
  const history = state.data.reports;
  const labels = history.map(c => c.commit_sha.substring(0, 7));
  const scores = history.map(c => c.health?.overall_score || c.overall_score || c.metrics?.score || 0);

  // Mini Timeline
  const ctxMini = document.getElementById('mini-timeline-chart');
  if (ctxMini) {
    state.charts.mini = new Chart(ctxMini, {
      type: 'line',
      data: {
        labels,
        datasets: [{
          label: 'Health Score',
          data: scores,
          borderColor: colors.cyan,
          backgroundColor: 'rgba(0, 212, 255, 0.1)',
          fill: true,
          tension: 0.4,
          pointRadius: 0,
          pointHoverRadius: 4
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { display: false },
          y: { min: 0, max: 100, grid: { color: 'rgba(255,255,255,0.05)' } }
        }
      }
    });
  }

  // Main Timeline
  const ctxTime = document.getElementById('timeline-chart');
  if (ctxTime) {
    state.charts.timeline = new Chart(ctxTime, {
      type: 'line',
      data: {
        labels,
        datasets: [{
          label: 'Overall Score',
          data: scores,
          borderColor: colors.cyan,
          borderWidth: 2,
          pointBackgroundColor: colors.surface,
          pointBorderColor: colors.cyan,
          pointRadius: 3,
          tension: 0.3
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        onClick: (e, elements) => {
          if (elements.length > 0) {
            const idx = elements[0].index;
            document.getElementById('commit-slider').value = idx;
            pausePlayback();
            renderCommit(idx);
          }
        },
        scales: {
          x: { grid: { display: false } },
          y: { min: 0, max: 100, grid: { color: 'rgba(255,255,255,0.05)' } }
        }
      }
    });
  }

  // Domain Breakdowns
  const ctxDom = document.getElementById('domain-chart');
  if (ctxDom) {
    const ds = (key) => history.map(c => c.health?.domain_scores?.[key] || 0);
    state.charts.domain = new Chart(ctxDom, {
      type: 'line',
      data: {
        labels,
        datasets: [
          { label: 'Architecture', data: ds('architecture'), borderColor: colors.purple, tension: 0.3, pointRadius:0, borderWidth:1 },
          { label: 'Complexity', data: ds('complexity'), borderColor: colors.blue, tension: 0.3, pointRadius:0, borderWidth:1 },
          { label: 'Dependency', data: ds('dependency'), borderColor: colors.warning, tension: 0.3, pointRadius:0, borderWidth:1 },
          { label: 'Evolution', data: ds('evolution'), borderColor: colors.healthy, tension: 0.3, pointRadius:0, borderWidth:1 }
        ]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        scales: { y: { min:0, max:100 } }
      }
    });
  }
}

function updateChartHighlight(idx) {
  ['mini', 'timeline', 'domain'].forEach(key => {
    const chart = state.charts[key];
    if (chart) {
      chart.setActiveElements([{datasetIndex: 0, index: idx}]);
      chart.update();
    }
  });
}

// -----------------------------------------------------------------------------
// D3 Graph Render
// -----------------------------------------------------------------------------
let svgSelection = null;
let simulation = null;

function renderGraph(commit) {
  const containerId = '#graph-svg-container';
  const container = document.querySelector(containerId);
  if (!container) return;
  
  const width = container.clientWidth;
  const height = container.clientHeight;
  const mode = document.getElementById('graph-mode').value;
  
  const gdata = commit.graph || {nodes:[], edges:[]};
  
  // Clone to avoid d3 mutation side-effects
  const nodes = gdata.nodes.map(n => ({...n}));
  const links = gdata.edges.map(e => ({source: e.source, target: e.target}));

  d3.select(containerId).selectAll('*').remove();
  
  if (simulation) simulation.stop();

  const svg = d3.select(containerId)
    .append('svg')
    .attr('viewBox', [0, 0, width, height]);
    
  const g = svg.append('g');

  const zoom = d3.zoom()
    .scaleExtent([0.1, 4])
    .on('zoom', (e) => g.attr('transform', e.transform));
  svg.call(zoom);

  // Force layout
  simulation = d3.forceSimulation(nodes)
    .force('link', d3.forceLink(links).id(d => d.id).distance(60))
    .force('charge', d3.forceManyBody().strength(-300))
    .force('center', d3.forceCenter(width / 2, height / 2))
    .force('collide', d3.forceCollide().radius(20));

  // Edges
  const link = g.append('g')
    .attr('stroke', 'rgba(99,130,255,0.2)')
    .attr('stroke-width', 1.5)
    .selectAll('line')
    .data(links)
    .join('line');

  // Node coloring
  const getColor = (d) => {
    if (mode === 'instability') {
      const v = d.instability || 0;
      if (v > 0.8) return colors.critical;
      if (v > 0.5) return colors.warning;
      return colors.healthy;
    }
    if (mode === 'pagerank') {
      return d.pagerank > 0.05 ? colors.purple : colors.cyan;
    }
    if (mode === 'risk') {
      return d.risk > 0.5 ? colors.critical : d.risk > 0.2 ? colors.warning : colors.healthy;
    }
    return colors.blue;
  };

  // Nodes
  const node = g.append('g')
    .selectAll('circle')
    .data(nodes)
    .join('circle')
    .attr('r', d => 5 + (d.pagerank || 0) * 100)
    .attr('fill', getColor)
    .attr('stroke', colors.surface)
    .attr('stroke-width', 1.5)
    .call(drag(simulation));

  // Tooltips
  const tt = d3.select('#graph-tooltip');
  node.on('mouseover', (e, d) => {
    tt.classed('hidden', false)
      .html(`
        <div class="tt-id">${d.id}</div>
        <div class="tt-row">Layer: ${d.layer || 'unknown'}</div>
        <div class="tt-row">Instability: ${(d.instability||0).toFixed(2)}</div>
        <div class="tt-row">PageRank: ${(d.pagerank||0).toFixed(4)}</div>
        <div class="tt-row">Risk: ${(d.risk||0).toFixed(4)}</div>
      `);
  }).on('mousemove', (e) => {
    tt.style('left', (e.pageX + 15) + 'px')
      .style('top', (e.pageY + 15) + 'px');
  }).on('mouseout', () => {
    tt.classed('hidden', true);
  });

  // Labels
  const label = g.append('g')
    .selectAll('text')
    .data(nodes)
    .join('text')
    .attr('dy', 15)
    .attr('text-anchor', 'middle')
    .attr('fill', colors.textSecondary)
    .attr('font-size', '10px')
    .attr('font-family', 'JetBrains Mono')
    .text(d => d.id.split('.').pop());

  simulation.on('tick', () => {
    link
      .attr('x1', d => d.source.x)
      .attr('y1', d => d.source.y)
      .attr('x2', d => d.target.x)
      .attr('y2', d => d.target.y);
    node
      .attr('cx', d => d.x)
      .attr('cy', d => d.y);
    label
      .attr('x', d => d.x)
      .attr('y', d => d.y);
  });

  function drag(simulation) {
    function dragstarted(event) {
      if (!event.active) simulation.alphaTarget(0.3).restart();
      event.subject.fx = event.subject.x;
      event.subject.fy = event.subject.y;
    }
    function dragged(event) {
      event.subject.fx = event.x;
      event.subject.fy = event.y;
    }
    function dragended(event) {
      if (!event.active) simulation.alphaTarget(0);
      event.subject.fx = null;
      event.subject.fy = null;
    }
    return d3.drag()
      .on('start', dragstarted)
      .on('drag', dragged)
      .on('end', dragended);
  }
}

// -----------------------------------------------------------------------------
// Heatmap Render
// -----------------------------------------------------------------------------
function renderHeatmap(commit) {
  const containerId = '#heatmap-container';
  const container = document.querySelector(containerId);
  if (!container) return;

  d3.select(containerId).selectAll('*').remove();
  
  const gdata = commit.graph || {nodes:[], edges:[]};
  const nodes = gdata.nodes.map(n => n.id).sort();
  if (nodes.length === 0 || nodes.length > 50) {
    container.innerHTML = `<div class="muted" style="padding:20px;">${nodes.length === 0 ? 'No modules.' : 'Graph too large for heatmap (>50 nodes).'}</div>`;
    return;
  }

  const margin = {top: 100, right: 30, bottom: 30, left: 150};
  const cellSize = 20;
  const width = nodes.length * cellSize;
  const height = nodes.length * cellSize;

  const svg = d3.select(containerId)
    .append('svg')
    .attr('width', width + margin.left + margin.right)
    .attr('height', height + margin.top + margin.bottom)
    .append('g')
    .attr('transform', `translate(${margin.left},${margin.top})`);

  const x = d3.scaleBand().range([0, width]).domain(nodes).padding(0.05);
  const y = d3.scaleBand().range([0, height]).domain(nodes).padding(0.05);

  // X Axis
  svg.append('g')
    .call(d3.axisTop(x))
    .selectAll('text')
    .attr('transform', 'rotate(-45)')
    .attr('dx', '5px')
    .attr('dy', '-5px')
    .style('text-anchor', 'start')
    .style('fill', colors.textSecondary);

  // Y Axis
  svg.append('g')
    .call(d3.axisLeft(y))
    .selectAll('text')
    .style('fill', colors.textSecondary);
    
  svg.selectAll('.domain').remove();
  svg.selectAll('.tick line').remove();

  // Matrix
  const matrix = [];
  const edgeMap = {};
  gdata.edges.forEach(e => { edgeMap[`${e.source}|${e.target}`] = true; });

  nodes.forEach(u => {
    nodes.forEach(v => {
      matrix.push({source: u, target: v, val: edgeMap[`${u}|${v}`] ? 1 : 0});
    });
  });

  svg.selectAll('rect')
    .data(matrix)
    .join('rect')
    .attr('x', d => x(d.target))
    .attr('y', d => y(d.source))
    .attr('width', x.bandwidth())
    .attr('height', y.bandwidth())
    .style('fill', d => d.val ? colors.purple : 'rgba(255,255,255,0.03)')
    .style('rx', 2)
    .style('ry', 2);
}

// Boot
window.addEventListener('DOMContentLoaded', init);
