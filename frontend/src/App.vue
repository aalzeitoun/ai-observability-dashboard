<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import Chart from 'chart.js/auto'

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
const wsBaseUrl = import.meta.env.VITE_WS_BASE_URL || apiBaseUrl.replace(/^http/, 'ws')

const backendHealth = ref(null)
const databaseHealth = ref(null)
const summary = ref(null)
const predictions = ref([])
const timeseries = ref([])
const recentLogs = ref([])
const errorMessage = ref('')
const isLoading = ref(false)
const websocketStatus = ref('connecting')

const latencyChartCanvas = ref(null)
const confidenceChartCanvas = ref(null)
const predictionChartCanvas = ref(null)

let latencyChart = null
let confidenceChart = null
let predictionChart = null
let dashboardSocket = null
let reconnectTimer = null
let shouldReconnect = true

function formatNumber(value, digits = 2) {
  if (value === null || value === undefined) {
    return 'N/A'
  }

  return Number(value).toFixed(digits)
}

function formatDate(value) {
  if (!value) {
    return 'N/A'
  }

  return new Date(value).toLocaleString()
}

function destroyCharts() {
  if (latencyChart) {
    latencyChart.destroy()
    latencyChart = null
  }

  if (confidenceChart) {
    confidenceChart.destroy()
    confidenceChart = null
  }

  if (predictionChart) {
    predictionChart.destroy()
    predictionChart = null
  }
}

async function fetchJson(path) {
  const response = await fetch(`${apiBaseUrl}${path}`)

  if (!response.ok) {
    throw new Error(`${path} failed with status ${response.status}`)
  }

  return response.json()
}

async function applyDashboardSnapshot(payload) {
  summary.value = payload.summary
  predictions.value = payload.predictions
  timeseries.value = payload.timeseries
  recentLogs.value = payload.recent_logs

  await nextTick()
  renderCharts()
}

async function refreshDashboard() {
  try {
    isLoading.value = true
    errorMessage.value = ''

    const [
      backendHealthResponse,
      databaseHealthResponse,
      summaryResponse,
      predictionsResponse,
      timeseriesResponse,
      recentLogsResponse
    ] = await Promise.all([
      fetchJson('/health'),
      fetchJson('/health/db'),
      fetchJson('/metrics/summary'),
      fetchJson('/metrics/predictions'),
      fetchJson('/metrics/timeseries?limit=50'),
      fetchJson('/inference-logs?limit=10')
    ])

    backendHealth.value = backendHealthResponse
    databaseHealth.value = databaseHealthResponse

    await applyDashboardSnapshot({
      summary: summaryResponse,
      predictions: predictionsResponse,
      timeseries: timeseriesResponse,
      recent_logs: recentLogsResponse
    })
  } catch (error) {
    errorMessage.value = `Dashboard refresh failed: ${error.message}`
  } finally {
    isLoading.value = false
  }
}

function renderCharts() {
  if (!latencyChartCanvas.value || !confidenceChartCanvas.value || !predictionChartCanvas.value) {
    return
  }

  destroyCharts()

  const labels = timeseries.value.map((point) =>
    new Date(point.created_at).toLocaleTimeString()
  )

  latencyChart = new Chart(latencyChartCanvas.value, {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: 'Latency ms',
          data: timeseries.value.map((point) => point.latency_ms),
          tension: 0.25
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false
    }
  })

  confidenceChart = new Chart(confidenceChartCanvas.value, {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: 'Confidence',
          data: timeseries.value.map((point) => point.confidence),
          tension: 0.25
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: {
          min: 0,
          max: 1
        }
      }
    }
  })

  predictionChart = new Chart(predictionChartCanvas.value, {
    type: 'bar',
    data: {
      labels: predictions.value.map((item) => `Class ${item.prediction}`),
      datasets: [
        {
          label: 'Prediction count',
          data: predictions.value.map((item) => item.count)
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false
    }
  })
}

function connectWebSocket() {
  if (dashboardSocket) {
    dashboardSocket.close()
  }

  websocketStatus.value = 'connecting'
  dashboardSocket = new WebSocket(`${wsBaseUrl}/ws/dashboard`)

  dashboardSocket.onopen = () => {
    websocketStatus.value = 'connected'
  }

  dashboardSocket.onmessage = async (event) => {
    const payload = JSON.parse(event.data)

    if (payload.type === 'dashboard_snapshot') {
      await applyDashboardSnapshot(payload)
    }
  }

  dashboardSocket.onerror = () => {
    websocketStatus.value = 'error'
  }

  dashboardSocket.onclose = () => {
    websocketStatus.value = 'disconnected'

    if (shouldReconnect) {
      reconnectTimer = window.setTimeout(connectWebSocket, 3000)
    }
  }
}

async function simulateInference(profile) {
  try {
    isLoading.value = true
    errorMessage.value = ''

    const response = await fetch(`${apiBaseUrl}/simulate-inference?profile=${profile}`, {
      method: 'POST'
    })

    if (!response.ok) {
      throw new Error(`Simulation failed with status ${response.status}`)
    }

    await refreshDashboard()
  } catch (error) {
    errorMessage.value = `Simulation failed: ${error.message}`
  } finally {
    isLoading.value = false
  }
}

onMounted(async () => {
  await refreshDashboard()
  connectWebSocket()
})

onBeforeUnmount(() => {
  shouldReconnect = false

  if (reconnectTimer) {
    window.clearTimeout(reconnectTimer)
  }

  if (dashboardSocket) {
    dashboardSocket.close()
  }

  destroyCharts()
})
</script>

<template>
  <main class="page">
    <section class="hero">
      <div>
        <p class="eyebrow">MLOps Monitoring</p>
        <h1>AI Observability Dashboard</h1>
        <p class="subtitle">
          Monitor inference latency, confidence scores, prediction distribution,
          and simulated production drift.
        </p>
      </div>

      <div class="actions">
        <button :disabled="isLoading" @click="simulateInference('normal')">
          Simulate Normal
        </button>
        <button :disabled="isLoading" class="danger" @click="simulateInference('drift')">
          Simulate Drift
        </button>
        <button :disabled="isLoading" class="secondary" @click="refreshDashboard">
          Refresh
        </button>
      </div>
    </section>

    <section v-if="errorMessage" class="error">
      {{ errorMessage }}
    </section>

    <section class="status-row">
      <article class="status-card">
        <span>Backend</span>
        <strong :class="backendHealth?.status === 'ok' ? 'ok' : 'muted'">
          {{ backendHealth?.status || 'checking' }}
        </strong>
      </article>

      <article class="status-card">
        <span>PostgreSQL</span>
        <strong :class="databaseHealth?.status === 'ok' ? 'ok' : 'muted'">
          {{ databaseHealth?.status || 'checking' }}
        </strong>
      </article>

      <article class="status-card">
        <span>WebSocket</span>
        <strong :class="websocketStatus === 'connected' ? 'ok' : 'muted'">
          {{ websocketStatus }}
        </strong>
      </article>

      <article class="status-card">
        <span>Latest Log</span>
        <strong>{{ formatDate(summary?.latest_log_at) }}</strong>
      </article>
    </section>

    <section class="metrics-grid">
      <article class="metric-card">
        <span>Total Logs</span>
        <strong>{{ summary?.total_logs ?? 0 }}</strong>
      </article>

      <article class="metric-card">
        <span>Avg Latency</span>
        <strong>{{ formatNumber(summary?.avg_latency_ms) }} ms</strong>
      </article>

      <article class="metric-card">
        <span>P95 Latency</span>
        <strong>{{ formatNumber(summary?.p95_latency_ms) }} ms</strong>
      </article>

      <article class="metric-card">
        <span>Avg Confidence</span>
        <strong>{{ formatNumber(summary?.avg_confidence, 4) }}</strong>
      </article>

      <article class="metric-card">
        <span>Low Confidence</span>
        <strong>{{ summary?.low_confidence_count ?? 0 }}</strong>
      </article>

      <article class="metric-card">
        <span>Max Latency</span>
        <strong>{{ formatNumber(summary?.max_latency_ms) }} ms</strong>
      </article>
    </section>

    <section class="charts-grid">
      <article class="panel">
        <h2>Latency Over Time</h2>
        <div class="chart-container">
          <canvas ref="latencyChartCanvas"></canvas>
        </div>
      </article>

      <article class="panel">
        <h2>Confidence Over Time</h2>
        <div class="chart-container">
          <canvas ref="confidenceChartCanvas"></canvas>
        </div>
      </article>

      <article class="panel full-width">
        <h2>Prediction Distribution</h2>
        <div class="chart-container">
          <canvas ref="predictionChartCanvas"></canvas>
        </div>
      </article>
    </section>

    <section class="panel">
      <h2>Recent Inference Logs</h2>

      <div class="table-wrapper">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Profile</th>
              <th>Model</th>
              <th>Prediction</th>
              <th>Confidence</th>
              <th>Latency</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="log in recentLogs" :key="log.id">
              <td>{{ log.id }}</td>
              <td>
                <span class="profile-badge" :class="`profile-${log.profile}`">
                  {{ log.profile }}
                </span>
              </td>
              <td>{{ log.model_name }}</td>
              <td>{{ log.prediction }}</td>
              <td>{{ formatNumber(log.confidence, 4) }}</td>
              <td>{{ formatNumber(log.latency_ms) }} ms</td>
              <td>{{ formatDate(log.created_at) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </main>
</template>
