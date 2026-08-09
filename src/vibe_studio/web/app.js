// Vibe Studio 4.0 Cosmic Web Application Script
document.addEventListener('DOMContentLoaded', () => {
  initTabs();
  initWebSocket();
  loadPredictiveSuggestions();
  loadMarketplace();

  document.getElementById('run-task-btn').addEventListener('click', runAgentTask);
  document.getElementById('task-input').addEventListener('keypress', (e) => {
    if (e.key === 'Enter') runAgentTask();
  });
  document.getElementById('clear-log-btn').addEventListener('click', () => {
    document.getElementById('log-stream').innerHTML = '';
  });
  document.getElementById('marketplace-search').addEventListener('input', (e) => {
    loadMarketplace(e.target.value);
  });
});

function initTabs() {
  const tabs = document.querySelectorAll('.nav-tab');
  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      tabs.forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
      tab.classList.add('active');
      const targetId = 'tab-' + tab.dataset.tab;
      document.getElementById(targetId).classList.add('active');
    });
  });
}

function initWebSocket() {
  const wsHost = window.location.hostname || '127.0.0.1';
  const ws = new WebSocket(`ws://${wsHost}:8001`);

  ws.onopen = () => {
    appendLog('System connected to WebSocket event stream (ws://' + wsHost + ':8001)', 'system');
  };

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.type === 'agent_progress') {
        appendLog(`[Agent Progress] Stage: ${data.data.stage}`, 'step');
      } else {
        appendLog(`[Event: ${data.type}] ${JSON.stringify(data.data)}`, 'system');
      }
    } catch (e) {
      appendLog(event.data, 'system');
    }
  };

  ws.onerror = () => {
    appendLog('WebSocket connection fallback / offline', 'error');
  };
}

function appendLog(msg, type = 'system') {
  const stream = document.getElementById('log-stream');
  const entry = document.createElement('div');
  entry.className = `log-entry ${type}`;
  entry.textContent = `[${new Date().toLocaleTimeString()}] ${msg}`;
  stream.appendChild(entry);
  stream.scrollTop = stream.scrollHeight;
}

async function runAgentTask() {
  const input = document.getElementById('task-input');
  const prompt = input.value.trim();
  if (!prompt) return;

  appendLog(`Submitting task: "${prompt}"`, 'step');
  input.value = '';

  try {
    const res = await fetch('/api/v1/execute', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt: prompt })
    });
    const data = await res.json();
    appendLog(`Task execution completed. ${data.summary || ''}`, 'system');
  } catch (err) {
    appendLog(`Task request failed: ${err.message}`, 'error');
  }
}

async function loadPredictiveSuggestions() {
  try {
    const res = await fetch('/api/v1/predict', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ current_file: 'src/main.py' })
    });
    const data = await res.json();
    const container = document.getElementById('predictive-list');
    container.innerHTML = '';

    (data.suggestions || []).forEach(item => {
      const div = document.createElement('div');
      div.className = 'predictive-item';
      div.innerHTML = `<div class="title">${item.title} (${Math.round(item.confidence * 100)}%)</div><div class="desc">${item.description}</div>`;
      div.addEventListener('click', () => {
        document.getElementById('task-input').value = item.title;
      });
      container.appendChild(div);
    });
  } catch (e) {
    console.log('Predictive load exception:', e);
  }
}

async function loadMarketplace(query = '') {
  try {
    const url = query ? `/api/v1/plugins/search?q=${encodeURIComponent(query)}` : '/api/v1/plugins';
    const res = await fetch(url);
    const data = await res.json();
    const grid = document.getElementById('plugin-grid');
    grid.innerHTML = '';

    const plugins = data.plugins || [];
    document.getElementById('plugin-count').textContent = plugins.length;

    plugins.forEach(p => {
      const card = document.createElement('div');
      card.className = 'plugin-card';
      card.innerHTML = `
        <span class="badge">${p.category || 'General'}</span>
        <h4>${p.name}</h4>
        <p>${p.description}</p>
        <button class="install-btn ${p.installed ? 'installed' : ''}">
          ${p.installed ? '✓ Installed' : 'Install Plugin'}
        </button>
      `;
      const btn = card.querySelector('.install-btn');
      btn.addEventListener('click', async () => {
        if (p.installed) return;
        btn.textContent = 'Installing...';
        const installRes = await fetch(`/api/v1/plugins/install`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: p.name })
        });
        const installData = await installRes.json();
        if (installData.success) {
          btn.textContent = '✓ Installed';
          btn.classList.add('installed');
        } else {
          btn.textContent = 'Failed';
        }
      });
      grid.appendChild(card);
    });
  } catch (e) {
    console.log('Marketplace load exception:', e);
  }
}
