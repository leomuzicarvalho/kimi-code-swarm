"""Live web dashboard for swarm monitoring.

A self-contained module using only stdlib. Serves a beautiful real-time
HTML dashboard via a threaded HTTP server with Server-Sent Events.
"""

from __future__ import annotations

import json
import os
import queue
import signal
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

DEFAULT_STATE_PATH = Path.home() / ".kimi" / "kimi-swarm-state.json"
DASHBOARD_META_PATH = Path.home() / ".kimi" / "kimi-swarm-dashboard.json"

# ---------------------------------------------------------------------------
# HTML Dashboard (embedded so zero external deps)
# ---------------------------------------------------------------------------

_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>🐝 Kimi Swarm Dashboard</title>
<style>
:root {
  --bg: #0b0c15;
  --panel: rgba(20, 22, 36, 0.75);
  --border: rgba(255,255,255,0.06);
  --text: #e2e4f0;
  --muted: #8b8fa3;
  --accent: #00d4ff;
  --accent2: #7c3aed;
  --success: #22c55e;
  --warning: #f59e0b;
  --danger: #ef4444;
  --idle: #64748b;
  --spawning: #a78bfa;
  --planning: #fbbf24;
  --executing: #00d4ff;
  --reviewing: #f472b6;
  --waiting: #94a3b8;
  --completed: #22c55e;
  --failed: #ef4444;
  --terminated: #475569;
  --radius: 16px;
  --shadow: 0 8px 32px rgba(0,0,0,0.35);
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: var(--bg);
  color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
  min-height: 100vh;
  overflow-x: hidden;
}
#particles {
  position: fixed;
  top: 0; left: 0; width: 100%; height: 100%;
  z-index: 0;
  pointer-events: none;
}
.container {
  position: relative;
  z-index: 1;
  max-width: 1400px;
  margin: 0 auto;
  padding: 32px 24px;
}
header {
  text-align: center;
  margin-bottom: 32px;
  animation: fadeInDown 0.8s ease-out;
}
header h1 {
  font-size: 2.4rem;
  font-weight: 800;
  background: linear-gradient(90deg, var(--accent), var(--accent2));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  letter-spacing: -1px;
}
header p {
  color: var(--muted);
  margin-top: 6px;
  font-size: 0.95rem;
}
.grid {
  display: grid;
  gap: 20px;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
}
.card {
  background: var(--panel);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 24px;
  box-shadow: var(--shadow);
  transition: transform 0.3s ease, box-shadow 0.3s ease;
  animation: fadeInUp 0.6s ease-out both;
}
.card:hover {
  transform: translateY(-4px);
  box-shadow: 0 16px 48px rgba(0,0,0,0.45);
}
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}
.card-title {
  font-size: 0.85rem;
  text-transform: uppercase;
  letter-spacing: 1.5px;
  color: var(--muted);
  font-weight: 700;
}
.stat-value {
  font-size: 2rem;
  font-weight: 800;
  color: var(--text);
}
.stat-value.accent { color: var(--accent); }
.stat-value.success { color: var(--success); }
.stat-value.warning { color: var(--warning); }

/* Iteration badge */
.iteration-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: linear-gradient(90deg, var(--accent), var(--accent2));
  color: #fff;
  font-size: 0.75rem;
  font-weight: 700;
  padding: 4px 12px;
  border-radius: 20px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  animation: pulseGlow 2s infinite;
}
.iteration-badge.static {
  animation: none;
  background: rgba(255,255,255,0.06);
  color: var(--muted);
}

/* Verification status */
.verification-pill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 0.7rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  padding: 3px 10px;
  border-radius: 20px;
  border: 1px solid rgba(255,255,255,0.08);
}
.verification-pill.passed { background: rgba(34,197,94,0.12); color: var(--success); border-color: rgba(34,197,94,0.2); }
.verification-pill.failed { background: rgba(239,68,68,0.12); color: var(--danger); border-color: rgba(239,68,68,0.2); }
.verification-pill.pending { background: rgba(245,158,11,0.12); color: var(--warning); border-color: rgba(245,158,11,0.2); }

/* Progress ring */
.ring-wrap {
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  width: 140px;
  height: 140px;
  margin: 0 auto 16px;
}
.ring-wrap svg {
  transform: rotate(-90deg);
}
.ring-bg { fill: none; stroke: rgba(255,255,255,0.06); stroke-width: 10; }
.ring-progress {
  fill: none;
  stroke: url(#ringGradient);
  stroke-width: 10;
  stroke-linecap: round;
  stroke-dasharray: 377;
  stroke-dashoffset: 377;
  transition: stroke-dashoffset 1s cubic-bezier(0.4, 0, 0.2, 1);
}
.ring-text {
  position: absolute;
  text-align: center;
}
.ring-text .percent {
  font-size: 1.8rem;
  font-weight: 800;
  color: var(--accent);
}
.ring-text .label {
  font-size: 0.7rem;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 1px;
}

/* Agent cards */
.agent-card {
  background: var(--panel);
  backdrop-filter: blur(20px);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px;
  box-shadow: var(--shadow);
  transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
  animation: fadeInUp 0.5s ease-out both;
  position: relative;
  overflow: hidden;
}
.agent-card::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0; height: 3px;
  background: var(--phase-color, var(--idle));
  opacity: 0.8;
  transition: background 0.4s ease;
}
.agent-card.pulse {
  animation: pulseGlow 2s infinite, fadeInUp 0.5s ease-out both;
}
.agent-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
}
.agent-avatar {
  width: 44px; height: 44px;
  border-radius: 12px;
  display: flex; align-items: center; justify-content: center;
  font-size: 1.3rem;
  background: rgba(255,255,255,0.05);
  flex-shrink: 0;
}
.agent-meta { flex: 1; min-width: 0; }
.agent-name {
  font-weight: 700;
  font-size: 1.05rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.agent-type {
  font-size: 0.78rem;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.phase-badge {
  font-size: 0.7rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  padding: 4px 10px;
  border-radius: 20px;
  background: rgba(255,255,255,0.06);
  color: var(--phase-color, var(--text));
  border: 1px solid rgba(255,255,255,0.08);
  white-space: nowrap;
}

/* Bars */
.bar-group { margin-bottom: 10px; }
.bar-label {
  display: flex; justify-content: space-between;
  font-size: 0.78rem; color: var(--muted);
  margin-bottom: 4px;
}
.bar-track {
  height: 8px;
  background: rgba(255,255,255,0.05);
  border-radius: 4px;
  overflow: hidden;
}
.bar-fill {
  height: 100%;
  border-radius: 4px;
  transition: width 0.8s cubic-bezier(0.4, 0, 0.2, 1);
  background: linear-gradient(90deg, var(--bar-color), var(--bar-color2));
}

/* Mini grid for context tokens */
.mini-grid {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 10px;
  margin-top: 12px;
}
.mini-stat {
  background: rgba(255,255,255,0.03);
  border-radius: 10px;
  padding: 10px 12px;
}
.mini-stat .val {
  font-size: 1rem;
  font-weight: 700;
  color: var(--text);
}
.mini-stat .lbl {
  font-size: 0.7rem;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

/* Details grid */
.details-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--border);
}
.detail-item .dlbl {
  font-size: 0.65rem;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--muted);
  opacity: 0.7;
  margin-bottom: 2px;
}
.detail-item .dval {
  color: var(--text);
  font-size: 0.78rem;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.detail-item.full {
  grid-column: 1 / -1;
}

/* Legend */
.legend {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 20px;
  justify-content: center;
}
.legend-item {
  display: flex; align-items: center; gap: 6px;
  font-size: 0.75rem; color: var(--muted);
  background: rgba(255,255,255,0.03);
  padding: 4px 10px;
  border-radius: 20px;
}
.legend-dot {
  width: 8px; height: 8px;
  border-radius: 50%;
}

/* Offline overlay */
.offline-overlay {
  position: fixed;
  inset: 0;
  background: rgba(11,12,21,0.92);
  backdrop-filter: blur(8px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.4s ease;
}
.offline-overlay.show {
  opacity: 1;
  pointer-events: all;
}
.offline-box {
  text-align: center;
}
.offline-box h2 {
  font-size: 1.8rem;
  margin-bottom: 8px;
  color: var(--danger);
}
.offline-box p { color: var(--muted); }

/* Connection status */
.conn-status {
  position: fixed;
  top: 16px; right: 16px;
  z-index: 50;
  display: flex; align-items: center; gap: 8px;
  background: var(--panel);
  border: 1px solid var(--border);
  padding: 6px 14px;
  border-radius: 20px;
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  transition: all 0.3s ease;
}
.conn-dot {
  width: 8px; height: 8px;
  border-radius: 50%;
  background: var(--success);
  box-shadow: 0 0 8px var(--success);
  transition: background 0.3s ease, box-shadow 0.3s ease;
}
.conn-status.disconnected .conn-dot {
  background: var(--danger);
  box-shadow: 0 0 8px var(--danger);
  animation: blink 1s infinite;
}

/* State freshness indicator */
.freshness-indicator {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 0.7rem;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 12px;
  background: rgba(34,197,94,0.1);
  color: var(--success);
  transition: all 0.3s ease;
}
.freshness-indicator.stale {
  background: rgba(239,68,68,0.1);
  color: var(--danger);
}

@keyframes fadeInDown {
  from { opacity: 0; transform: translateY(-20px); }
  to { opacity: 1; transform: translateY(0); }
}
@keyframes fadeInUp {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}
@keyframes pulseGlow {
  0% { box-shadow: 0 0 0 0 rgba(0,212,255,0.15); }
  70% { box-shadow: 0 0 0 12px rgba(0,212,255,0); }
  100% { box-shadow: 0 0 0 0 rgba(0,212,255,0); }
}
@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}
</style>
</head>
<body>
<canvas id="particles"></canvas>

<div class="conn-status" id="connStatus">
  <div class="conn-dot"></div>
  <span id="connText">Live</span>
</div>

<div class="offline-overlay" id="offlineOverlay">
  <div class="offline-box">
    <h2>🔴 Swarm Offline</h2>
    <p>No active swarm detected. Initialize or restore a swarm to see live data.</p>
  </div>
</div>

<div class="container">
  <header>
    <h1>🐝 Kimi Swarm</h1>
    <p id="swarmMeta">Loading...</p>
  </header>

  <div class="grid" id="topGrid">
    <div class="card" style="display:flex;flex-direction:column;align-items:center;justify-content:center;">
      <div class="ring-wrap">
        <svg width="140" height="140" viewBox="0 0 140 140">
          <defs>
            <linearGradient id="ringGradient" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" style="stop-color:#00d4ff;stop-opacity:1" />
              <stop offset="100%" style="stop-color:#7c3aed;stop-opacity:1" />
            </linearGradient>
          </defs>
          <circle class="ring-bg" cx="70" cy="70" r="60"/>
          <circle class="ring-progress" id="progressRing" cx="70" cy="70" r="60"/>
        </svg>
        <div class="ring-text">
          <div class="percent" id="overallPercent">0%</div>
          <div class="label">Overall</div>
        </div>
      </div>
      <div class="card-title">Overall Progress</div>
    </div>

    <div class="card">
      <div class="card-header">
        <span class="card-title">Swarm Overview</span>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;">
        <div>
          <div class="stat-value accent" id="activeAgents">0</div>
          <div style="font-size:0.8rem;color:var(--muted);">Active Agents</div>
        </div>
        <div>
          <div class="stat-value" id="maxAgents">0</div>
          <div style="font-size:0.8rem;color:var(--muted);">Max Capacity</div>
        </div>
        <div>
          <div class="stat-value success" id="completedTasks">0</div>
          <div style="font-size:0.8rem;color:var(--muted);">Completed Tasks</div>
        </div>
        <div>
          <div class="stat-value warning" id="totalTasks">0</div>
          <div style="font-size:0.8rem;color:var(--muted);">Total Tasks</div>
        </div>
      </div>
      <div style="margin-top:14px;display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
        <span id="iterationBadge" class="iteration-badge static">Iter: 0</span>
        <span id="freshnessIndicator" class="freshness-indicator">State Fresh</span>
      </div>
    </div>

    <div class="card">
      <div class="card-header">
        <span class="card-title">Main Agent Context</span>
      </div>
      <div class="bar-group">
        <div class="bar-label"><span>Token Usage</span><span id="mainCtxLabel">0 / 0</span></div>
        <div class="bar-track"><div class="bar-fill" id="mainCtxBar" style="width:0%;--bar-color:#00d4ff;--bar-color2:#7c3aed;"></div></div>
      </div>
      <div class="mini-grid">
        <div class="mini-stat"><div class="val" id="mainUsed">0</div><div class="lbl">Used</div></div>
        <div class="mini-stat"><div class="val" id="mainAvail">0</div><div class="lbl">Available</div></div>
      </div>
    </div>
  </div>

  <div style="margin-top:32px;">
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:20px;">
      <h2 style="font-size:1.3rem;font-weight:700;">🤖 Agents</h2>
      <span style="font-size:0.85rem;color:var(--muted);" id="agentCount">0 agents</span>
    </div>
    <div class="grid" id="agentsGrid"></div>
  </div>

  <div class="legend" id="legend"></div>
</div>

<script>
const PHASE_COLORS = {
  idle: '#64748b',
  spawning: '#a78bfa',
  planning: '#fbbf24',
  executing: '#00d4ff',
  reviewing: '#f472b6',
  waiting: '#94a3b8',
  completed: '#22c55e',
  failed: '#ef4444',
  terminated: '#475569',
};
const PHASE_EMOJIS = {
  idle: '🆕', spawning: '🐣', planning: '⏳', executing: '⚡',
  reviewing: '👀', waiting: '⏸️', completed: '✅', failed: '❌', terminated: '🛑',
};
const PHASE_PULSE = ['executing', 'planning', 'reviewing', 'spawning'];

let evtSource = null;
let reconnectTimer = null;
let animationDelay = 0;
let lastUpdateTime = 0;

function setConnected(yes) {
  const el = document.getElementById('connStatus');
  const txt = document.getElementById('connText');
  if (yes) {
    el.classList.remove('disconnected');
    txt.textContent = 'Live';
  } else {
    el.classList.add('disconnected');
    txt.textContent = 'Reconnecting...';
  }
}

function formatDuration(seconds) {
  const s = Math.floor(seconds);
  if (s < 60) return s + 's';
  if (s < 3600) {
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return `${m}m ${sec}s`;
  }
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return `${h}h ${m}m`;
}

function formatTime(isoString) {
  if (!isoString) return '—';
  const d = new Date(isoString);
  const now = new Date();
  const diffMs = now - d;
  const diffMins = Math.floor(diffMs / 60000);
  if (diffMins < 1) return 'just now';
  if (diffMins < 60) return diffMins + 'm ago';
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return diffHours + 'h ago';
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function formatNum(n) {
  return Number(n).toLocaleString();
}

function updateRing(percent) {
  const ring = document.getElementById('progressRing');
  const circumference = 2 * Math.PI * 60; // ~377
  const offset = circumference - (percent / 100) * circumference;
  ring.style.strokeDashoffset = offset;
  document.getElementById('overallPercent').textContent = percent.toFixed(1) + '%';
}

function updateTop(data) {
  document.getElementById('swarmMeta').textContent =
    `Swarm ID: ${data.swarm_id}  ·  Topology: ${data.topology}  ·  Status: ${data.is_active ? 'Active' : 'Inactive'}`;
  document.getElementById('activeAgents').textContent = data.active_agents;
  document.getElementById('maxAgents').textContent = data.max_agents;
  document.getElementById('completedTasks').textContent = data.completed_tasks;
  document.getElementById('totalTasks').textContent = data.total_tasks;

  const mc = data.main_context || {};
  const mc_pct = (mc.usage_percent !== undefined ? mc.usage_percent : (mc.max_tokens ? (mc.used_tokens / mc.max_tokens) * 100 : 0));
  document.getElementById('mainCtxLabel').textContent = `${formatNum(mc.used_tokens || 0)} / ${formatNum(mc.max_tokens || 0)} (${mc_pct.toFixed(1)}%)`;
  document.getElementById('mainCtxBar').style.width = Math.min(mc_pct, 100) + '%';
  document.getElementById('mainUsed').textContent = formatNum(mc.used_tokens);
  document.getElementById('mainAvail').textContent = formatNum(Math.max(0, mc.max_tokens - mc.used_tokens));

  updateRing(data.overall_progress);

  // Iteration badge
  const iterBadge = document.getElementById('iterationBadge');
  const totalIter = data.total_iterations || 0;
  iterBadge.textContent = `Iter: ${totalIter}`;
  if (totalIter > 0) {
    iterBadge.classList.remove('static');
  } else {
    iterBadge.classList.add('static');
  }

  // Freshness indicator
  const freshness = document.getElementById('freshnessIndicator');
  const now = Date.now();
  const isFresh = data._last_update && (now - new Date(data._last_update).getTime() < 5000);
  if (isFresh) {
    freshness.textContent = 'State Fresh';
    freshness.classList.remove('stale');
  } else {
    freshness.textContent = 'State Stale';
    freshness.classList.add('stale');
  }

  const offline = document.getElementById('offlineOverlay');
  if (!data.is_active && data.swarm_id === 'not-initialized') {
    offline.classList.add('show');
  } else {
    offline.classList.remove('show');
  }
}

function renderAgents(agents) {
  const grid = document.getElementById('agentsGrid');
  document.getElementById('agentCount').textContent = `${agents.length} agent${agents.length !== 1 ? 's' : ''}`;

  // Simple diff: if same count, try to update in place for smoother animations
  const existing = Array.from(grid.children);
  const maxLen = Math.max(agents.length, existing.length);

  for (let i = 0; i < maxLen; i++) {
    const a = agents[i];
    let card = existing[i];

    if (!a) {
      if (card) card.remove();
      continue;
    }

    const phase = a.phase;
    const color = PHASE_COLORS[phase] || PHASE_COLORS.idle;
    const emoji = PHASE_EMOJIS[phase] || '❓';
    const progress = a.task ? a.task.progress_percent : 0;
    const ctx = a.context;
    const tokens = a.tokens;
    const modelLabel = a.resolved_model && a.resolved_model !== a.model ? `${a.model} → ${a.resolved_model}` : a.model;
    const shouldPulse = PHASE_PULSE.includes(phase);
    const task = a.task || {};
    const verifStatus = task.verification_status || 'pending';
    const attemptCount = task.attempt_count || 0;
    const maxAttempts = task.max_attempts || 3;

    if (!card) {
      card = document.createElement('div');
      card.className = 'agent-card' + (shouldPulse ? ' pulse' : '');
      card.style.animationDelay = (i * 0.08) + 's';
      card.innerHTML = `
        <div class="agent-header">
          <div class="agent-avatar">${emoji}</div>
          <div class="agent-meta">
            <div class="agent-name"></div>
            <div class="agent-type"></div>
          </div>
          <div class="phase-badge"></div>
        </div>
        <div class="bar-group">
          <div class="bar-label"><span>Task Progress</span><span class="prog-pct"></span></div>
          <div class="bar-track"><div class="bar-fill prog-bar" style="width:0%;--bar-color:#22c55e;--bar-color2:#00d4ff;"></div></div>
        </div>
        <div class="bar-group">
          <div class="bar-label"><span>Context Usage</span><span class="ctx-pct"></span></div>
          <div class="bar-track"><div class="bar-fill ctx-bar" style="width:0%;--bar-color:#f59e0b;--bar-color2:#ef4444;"></div></div>
        </div>
        <div style="display:flex;align-items:center;gap:8px;margin:8px 0;flex-wrap:wrap;">
          <span class="verification-pill pending">Verify: pending</span>
          <span style="font-size:0.7rem;color:var(--muted);">Attempt: <span class="attempt-count">0/3</span></span>
        </div>
        <div class="mini-grid">
          <div class="mini-stat"><div class="val tok-prompt">0</div><div class="lbl">Prompt</div></div>
          <div class="mini-stat"><div class="val tok-comp">0</div><div class="lbl">Completion</div></div>
          <div class="mini-stat"><div class="val tok-total">0</div><div class="lbl">Total</div></div>
          <div class="mini-stat"><div class="val ctx-used">0</div><div class="lbl">Ctx Used</div></div>
          <div class="mini-stat"><div class="val ctx-max">0</div><div class="lbl">Ctx Max</div></div>
          <div class="mini-stat"><div class="val msg-count">0</div><div class="lbl">Messages</div></div>
        </div>
        <div class="details-grid">
          <div class="detail-item"><div class="dlbl">Agent ID</div><div class="dval agent-id"></div></div>
          <div class="detail-item"><div class="dlbl">Uptime</div><div class="dval uptime"></div></div>
          <div class="detail-item"><div class="dlbl">Spawned</div><div class="dval spawn-time"></div></div>
          <div class="detail-item"><div class="dlbl">Last Active</div><div class="dval last-active"></div></div>
          <div class="detail-item"><div class="dlbl">Task Status</div><div class="dval task-status"></div></div>
          <div class="detail-item full"><div class="dlbl">Task</div><div class="dval task-desc"></div></div>
        </div>
        <div style="margin-top:10px;font-size:0.72rem;color:var(--muted);" class="model-line"></div>
      `;
      grid.appendChild(card);
    }

    card.style.setProperty('--phase-color', color);
    card.querySelector('.agent-name').textContent = a.name;
    card.querySelector('.agent-type').textContent = a.agent_type;
    const badge = card.querySelector('.phase-badge');
    badge.textContent = phase;
    badge.style.color = color;
    badge.style.borderColor = color + '33';
    badge.style.background = color + '11';

    card.querySelector('.prog-pct').textContent = progress.toFixed(0) + '%';
    card.querySelector('.prog-bar').style.width = Math.min(progress, 100) + '%';
    const ctx_pct = (ctx && ctx.usage_percent !== undefined) ? ctx.usage_percent : (ctx && ctx.max_tokens ? (ctx.used_tokens / ctx.max_tokens) * 100 : 0);
    card.querySelector('.ctx-pct').textContent = ctx_pct.toFixed(1) + '%';
    card.querySelector('.ctx-bar').style.width = Math.min(ctx_pct, 100) + '%';
    const uptimeSec = a.spawn_time ? Math.floor((Date.now() - new Date(a.spawn_time).getTime()) / 1000) : 0;
    const taskDesc = task.description ? task.description : 'No task assigned';
    const taskStatus = task.status ? task.status : '—';

    // Update verification pill
    const verifPill = card.querySelector('.verification-pill');
    verifPill.textContent = 'Verify: ' + verifStatus;
    verifPill.className = 'verification-pill ' + verifStatus;
    card.querySelector('.attempt-count').textContent = `${attemptCount}/${maxAttempts}`;

    card.querySelector('.tok-prompt').textContent = formatNum(tokens.prompt_tokens || 0);
    card.querySelector('.tok-comp').textContent = formatNum(tokens.completion_tokens || 0);
    card.querySelector('.tok-total').textContent = formatNum(tokens.total_tokens || 0);
    card.querySelector('.ctx-used').textContent = formatNum(ctx.used_tokens);
    card.querySelector('.ctx-max').textContent = formatNum(ctx.max_tokens);
    card.querySelector('.msg-count').textContent = formatNum(a.messages_count || 0);
    card.querySelector('.agent-id').textContent = a.agent_id ? a.agent_id.slice(0, 8) : '—';
    card.querySelector('.uptime').textContent = formatDuration(uptimeSec);
    card.querySelector('.spawn-time').textContent = a.spawn_time ? formatTime(a.spawn_time) : '—';
    card.querySelector('.last-active').textContent = a.last_active ? formatTime(a.last_active) : '—';
    card.querySelector('.task-status').textContent = taskStatus;
    card.querySelector('.task-desc').textContent = taskDesc;
    card.querySelector('.model-line').textContent = `Model: ${modelLabel}`;

    if (shouldPulse) card.classList.add('pulse');
    else card.classList.remove('pulse');
  }
}

function renderLegend() {
  const legend = document.getElementById('legend');
  if (legend.children.length) return;
  for (const [phase, color] of Object.entries(PHASE_COLORS)) {
    const item = document.createElement('div');
    item.className = 'legend-item';
    item.innerHTML = `<div class="legend-dot" style="background:${color};"></div> ${phase}`;
    legend.appendChild(item);
  }
}

function handleData(data) {
  data._last_update = new Date().toISOString();
  updateTop(data);
  renderAgents(data.agents || []);
  renderLegend();
}

function connect() {
  if (evtSource) { evtSource.close(); }
  evtSource = new EventSource('/api/events');
  evtSource.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      handleData(data);
      setConnected(true);
    } catch (err) {
      console.error('Parse error', err);
    }
  };
  evtSource.onerror = () => {
    setConnected(false);
    evtSource.close();
    if (reconnectTimer) clearTimeout(reconnectTimer);
    reconnectTimer = setTimeout(connect, 2000);
  };
  evtSource.onopen = () => setConnected(true);
}

// Particle network background
(function initParticles() {
  const canvas = document.getElementById('particles');
  const ctx = canvas.getContext('2d');
  let W, H, particles = [];
  function resize() {
    W = canvas.width = window.innerWidth;
    H = canvas.height = window.innerHeight;
  }
  window.addEventListener('resize', resize);
  resize();

  const count = Math.min(80, Math.floor(W * H / 15000));
  for (let i = 0; i < count; i++) {
    particles.push({
      x: Math.random() * W, y: Math.random() * H,
      vx: (Math.random() - 0.5) * 0.4,
      vy: (Math.random() - 0.5) * 0.4,
      r: Math.random() * 2 + 1,
    });
  }

  function draw() {
    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = 'rgba(0, 212, 255, 0.35)';
    ctx.strokeStyle = 'rgba(0, 212, 255, 0.06)';
    for (let i = 0; i < particles.length; i++) {
      const p = particles[i];
      p.x += p.vx; p.y += p.vy;
      if (p.x < 0) p.x = W; if (p.x > W) p.x = 0;
      if (p.y < 0) p.y = H; if (p.y > H) p.y = 0;
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fill();
      for (let j = i + 1; j < particles.length; j++) {
        const q = particles[j];
        const dx = p.x - q.x, dy = p.y - q.y;
        const d = Math.sqrt(dx*dx + dy*dy);
        if (d < 140) {
          ctx.lineWidth = 1 - d / 140;
          ctx.beginPath();
          ctx.moveTo(p.x, p.y);
          ctx.lineTo(q.x, q.y);
          ctx.stroke();
        }
      }
    }
    requestAnimationFrame(draw);
  }
  draw();
})();

connect();
</script>
</body>
</html>
"""

# ---------------------------------------------------------------------------
# SSE broadcaster
# ---------------------------------------------------------------------------

class SSEBroadcaster:
    """Manages SSE client queues."""

    def __init__(self) -> None:
        self._clients: list[queue.Queue[str]] = []
        self._lock = threading.Lock()

    def add_client(self) -> queue.Queue[str]:
        q: queue.Queue[str] = queue.Queue()
        with self._lock:
            self._clients.append(q)
        return q

    def remove_client(self, q: queue.Queue[str]) -> None:
        with self._lock:
            try:
                self._clients.remove(q)
            except ValueError:
                pass

    def broadcast(self, data: dict[str, Any]) -> None:
        payload = f"data: {json.dumps(data)}\n\n"
        with self._lock:
            dead: list[queue.Queue[str]] = []
            for q in self._clients:
                try:
                    q.put_nowait(payload)
                except queue.Full:
                    dead.append(q)
            for q in dead:
                try:
                    self._clients.remove(q)
                except ValueError:
                    pass


_broadcaster = SSEBroadcaster()
_server_instance: ThreadingHTTPServer | None = None
_server_thread: threading.Thread | None = None

# ---------------------------------------------------------------------------
# Request handler
# ---------------------------------------------------------------------------

class DashboardHandler(BaseHTTPRequestHandler):
    """Serve dashboard, API, and SSE."""

    state_path: Path = DEFAULT_STATE_PATH

    def log_message(self, fmt: str, *args: Any) -> None:
        # Suppress default request logging
        pass

    def _send_json(self, data: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _read_state(self) -> dict[str, Any]:
        path = self.state_path
        if path.exists():
            try:
                with open(path, "r") as f:
                    return json.load(f)  # type: ignore[no-any-return]
            except Exception:
                pass
        return {
            "swarm_id": "not-initialized",
            "topology": "hierarchical",
            "max_agents": 5,
            "agents": [],
            "main_context": {"used_tokens": 0, "max_tokens": 128000, "usage_percent": 0.0},
            "is_active": False,
            "overall_progress": 0.0,
            "active_agents": 0,
            "completed_tasks": 0,
            "total_tasks": 0,
            "total_iterations": 0,
            "last_verification": None,
        }

    def _check_state_freshness(self) -> dict[str, Any]:
        """Check if the state file is fresh and return verification info."""
        path = self.state_path
        if not path.exists():
            return {
                "is_state_fresh": False,
                "last_update_timestamp": None,
                "agent_count": 0,
                "iteration_count": 0,
                "state_exists": False,
            }
        try:
            mtime = path.stat().st_mtime
            is_fresh = (time.time() - mtime) < 5.0
            state = self._read_state()
            return {
                "is_state_fresh": is_fresh,
                "last_update_timestamp": datetime.fromtimestamp(mtime).isoformat(),
                "agent_count": len(state.get("agents", [])),
                "iteration_count": state.get("total_iterations", 0),
                "state_exists": True,
                "swarm_id": state.get("swarm_id", "not-initialized"),
                "is_active": state.get("is_active", False),
            }
        except Exception as e:
            return {
                "is_state_fresh": False,
                "last_update_timestamp": None,
                "agent_count": 0,
                "iteration_count": 0,
                "state_exists": True,
                "error": str(e),
            }

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/" or self.path == "/index.html":
            body = _DASHBOARD_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/api/status":
            self._send_json(self._read_state())
        elif self.path == "/api/verify":
            self._send_json(self._check_state_freshness())
        elif self.path == "/api/events":
            self._handle_sse()
        else:
            self.send_error(404)

    def _handle_sse(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        q = _broadcaster.add_client()
        try:
            # Send current state immediately
            initial = f"data: {json.dumps(self._read_state())}\n\n"
            self.wfile.write(initial.encode("utf-8"))
            self.wfile.flush()

            while True:
                try:
                    payload = q.get(timeout=1)
                except queue.Empty:
                    # Send keep-alive comment to detect disconnects
                    self.wfile.write(b": keep-alive\n\n")
                    self.wfile.flush()
                    continue
                self.wfile.write(payload.encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            _broadcaster.remove_client(q)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def start_dashboard(
    port: int = 0,
    state_path: Path | str | None = None,
    open_browser: bool = True,
) -> int:
    """Start the dashboard server. Returns the bound port number.

    Unified startup that respects existing dashboards (both persistent
    and in-process) and deduplicates browser tab opens.
    """
    global _server_instance, _server_thread

    # 1. Check if a persistent background dashboard is already running
    existing_persistent = find_running_dashboard(state_path)
    if existing_persistent is not None:
        if open_browser and _should_open_browser(state_path):
            webbrowser.open(f"http://127.0.0.1:{existing_persistent}")
            _mark_browser_opened(state_path)
        return existing_persistent

    # 2. Check if an in-process dashboard is already running
    if _server_instance is not None:
        actual_port = _server_instance.server_address[1]  # type: ignore[return-value]
        if open_browser and _should_open_browser(state_path):
            webbrowser.open(f"http://127.0.0.1:{actual_port}")
            _mark_browser_opened(state_path)
        return actual_port

    handler = type("Handler", (DashboardHandler,), {})
    if state_path:
        handler.state_path = Path(state_path)
    else:
        handler.state_path = DEFAULT_STATE_PATH

    _server_instance = ThreadingHTTPServer(("127.0.0.1", port), handler)
    actual_port = _server_instance.server_address[1]

    def serve() -> None:
        _server_instance.serve_forever()  # type: ignore[union-attr]

    _server_thread = threading.Thread(target=serve, daemon=True)
    _server_thread.start()

    # Start background broadcaster that pushes state changes
    def broadcaster_loop() -> None:
        last_data: str | None = None
        while _server_instance is not None:
            try:
                data = handler.state_path.read_text()
                if data != last_data:
                    last_data = data
                    try:
                        payload = json.loads(data)
                        _broadcaster.broadcast(payload)
                    except Exception:
                        pass
            except Exception:
                pass
            time.sleep(0.8)

    threading.Thread(target=broadcaster_loop, daemon=True).start()

    url = f"http://127.0.0.1:{actual_port}"
    if open_browser and _should_open_browser(state_path):
        # Small delay so the server is definitely listening
        time.sleep(0.15)
        webbrowser.open(url)
        _mark_browser_opened(state_path)

    return actual_port


def stop_dashboard() -> None:
    """Stop the in-process dashboard server if running."""
    global _server_instance, _server_thread
    if _server_instance is not None:
        _server_instance.shutdown()
        _server_instance = None
        _server_thread = None


def broadcast_now(state_path: Path | str | None = None) -> None:
    """Force an immediate SSE broadcast of the current state."""
    path = Path(state_path) if state_path else DEFAULT_STATE_PATH
    if not path.exists():
        return
    try:
        with open(path, "r") as f:
            data = json.load(f)
        _broadcaster.broadcast(data)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Browser deduplication
# ---------------------------------------------------------------------------

_BROWSER_OPEN_COOLDOWN_SECONDS = 30


def _browser_lock_path(state_path: Path | str | None = None) -> Path:
    """Path to a timestamp file tracking the last browser open."""
    if state_path:
        p = Path(state_path)
        return p.parent / "kimi-swarm-browser.lock"
    return Path.home() / ".kimi" / "kimi-swarm-browser.lock"


def _should_open_browser(state_path: Path | str | None = None, cooldown: int = _BROWSER_OPEN_COOLDOWN_SECONDS) -> bool:
    """Return True if enough time has passed since the last browser open."""
    lock = _browser_lock_path(state_path)
    if not lock.exists():
        return True
    try:
        with open(lock, "r") as f:
            last_open = float(f.read().strip())
        return (time.time() - last_open) > cooldown
    except Exception:
        return True


def _mark_browser_opened(state_path: Path | str | None = None) -> None:
    """Record the current timestamp as the last browser open time."""
    lock = _browser_lock_path(state_path)
    try:
        lock.parent.mkdir(parents=True, exist_ok=True)
        with open(lock, "w") as f:
            f.write(str(time.time()))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Persistent background process helpers
# ---------------------------------------------------------------------------

def _meta_path(state_path: Path | str | None = None) -> Path:
    """Path to the dashboard metadata file (port + pid)."""
    if state_path:
        p = Path(state_path)
        return p.parent / "kimi-swarm-dashboard.json"
    return DASHBOARD_META_PATH


def find_running_dashboard(state_path: Path | str | None = None) -> int | None:
    """Return port number if a dashboard is already running, else None."""
    meta = _meta_path(state_path)
    if not meta.exists():
        return None
    try:
        with open(meta, "r") as f:
            info = json.load(f)
        port = info.get("port")
        if port is None:
            return None
        # Verify it's actually responding
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/status",
            method="GET",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=2) as resp:
            if resp.status == 200:
                return port
    except Exception:
        pass
    # Stale meta file — remove it
    try:
        meta.unlink()
    except Exception:
        pass
    return None


def launch_persistent_dashboard(
    port: int = 0,
    state_path: Path | str | None = None,
    open_browser: bool = True,
) -> int:
    """Launch a persistent background dashboard process. Returns the port.

    Deduplicates against existing persistent dashboards and respects
    the browser-open cooldown so only one tab is opened per session.
    """
    existing = find_running_dashboard(state_path)
    if existing is not None:
        if open_browser and _should_open_browser(state_path):
            webbrowser.open(f"http://127.0.0.1:{existing}")
            _mark_browser_opened(state_path)
        return existing

    # Build the command to run a standalone blocking server
    script = Path(__file__).with_name("_dashboard_server.py")
    state_path_str = str(state_path) if state_path else "."
    cmd = [
        sys.executable,
        str(script),
        "--port",
        str(port),
        "--state-path",
        state_path_str,
    ]

    # Launch detached background process
    kwargs: dict[str, Any] = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "start_new_session": True,
    }

    proc = subprocess.Popen(cmd, **kwargs)

    # Wait a moment for the server to bind, then discover the port
    time.sleep(0.5)

    # The subprocess writes a meta file; read it back
    meta = _meta_path(state_path)
    actual_port = None
    for _ in range(20):
        if meta.exists():
            try:
                with open(meta, "r") as f:
                    info = json.load(f)
                actual_port = info.get("port")
                if actual_port:
                    break
            except Exception:
                pass
        time.sleep(0.1)

    if actual_port is None:
        # Fallback: try to detect from the process
        actual_port = port if port != 0 else 0

    if open_browser and actual_port and _should_open_browser(state_path):
        webbrowser.open(f"http://127.0.0.1:{actual_port}")
        _mark_browser_opened(state_path)

    return actual_port or 0


def stop_persistent_dashboard(state_path: Path | str | None = None) -> None:
    """Stop a persistent background dashboard process."""
    meta = _meta_path(state_path)
    if not meta.exists():
        return
    try:
        with open(meta, "r") as f:
            info = json.load(f)
        pid = info.get("pid")
        if pid:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
    except Exception:
        pass
    finally:
        try:
            meta.unlink()
        except Exception:
            pass


def stop_all_dashboards(state_path: Path | str | None = None) -> None:
    """Stop both in-process and persistent dashboard servers."""
    stop_dashboard()
    stop_persistent_dashboard(state_path=state_path)
    # Also clear browser lock so a fresh init can open a new tab
    try:
        lock = _browser_lock_path(state_path)
        if lock.exists():
            lock.unlink()
    except Exception:
        pass


def run_standalone(
    port: int = 0,
    state_path: Path | str | None = None,
) -> None:
    """Run a blocking standalone dashboard server (for background processes)."""
    actual_port = start_dashboard(port=port, state_path=state_path, open_browser=False)

    # Write metadata so the parent CLI can find us
    meta = _meta_path(state_path)
    with open(meta, "w") as f:
        json.dump({"port": actual_port, "pid": os.getpid()}, f)

    # Keep alive until SIGTERM / SIGINT
    def _on_signal(_signum: int, _frame: Any) -> None:
        stop_dashboard()
        try:
            meta.unlink()
        except Exception:
            pass
        sys.exit(0)

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    # Block forever
    while True:
        time.sleep(3600)
