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
const driftReport = ref(null)
const alertsSummary = ref(null)
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

function driftedFeatureCount() {
  return driftReport.value?.features?.filter((feature) => feature.drift_detected).length ?? 0
}

function hasInsufficientDriftData() {
  return driftReport.value?.features?.some((feature) => feature.insufficient_data) ?? true
}

function alertStatusLabel() {
  const status = alertsSummary.value?.status || 'ok'

  if (status === 'critical') {
    return 'Critical'
  }

  if (status === 'warning') {
    return 'Warning'
  }

  if (status === 'info') {
    return 'Info'
  }

  return 'OK'
}

function alertStatusClass() {
  const status = alertsSummary.value?.status || 'ok'

  return `alert-${status}`
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

  if (payload.drift_report) {
    driftReport.value = payload.drift_report
  }

  if (payload.alerts) {
    alertsSummary.value = payload.alerts
  }

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
      recentLogsResponse,
      driftReportResponse,
      alertsResponse
    ] = await Promise.all([
      fetchJson('/health'),
      fetchJson('/health/db'),
      fetchJson('/metrics/summary'),
      fetchJson('/metrics/predictions'),
      fetchJson('/metrics/timeseries?limit=50'),
      fetchJson('/inference-logs?limit=10'),
      fetchJson('/drift/ks?profile=all&limit=100&min_samples=20'),
      fetchJson('/alerts/current?limit=100')
    ])

    backendHealth.value = backendHealthResponse
    databaseHealth.value = databaseHealthResponse

    await applyDashboardSnapshot({
      summary: summaryResponse,
      predictions: predictionsResponse,
      timeseries: timeseriesResponse,
      recent_logs: recentLogsResponse,
      drift_report: driftReportResponse,
      alerts: alertsResponse
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

async function simulateBatch(profile, count) {
  try {
    isLoading.value = true
    errorMessage.value = ''

    const response = await fetch(`${apiBaseUrl}/simulate-batch?profile=${profile}&count=${count}`, {
      method: 'POST'
    })

    if (!response.ok) {
      throw new Error(`Batch simulation failed with status ${response.status}`)
    }

    await refreshDashboard()
  } catch (error) {
    errorMessage.value = `Batch simulation failed: ${error.message}`
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
          and statistical data drift using the Kolmogorov–Smirnov test.
        </p>
      </div>

      <div class="actions">
        <button :disabled="isLoading" @click="simulateInference('normal')">
          Simulate Normal
        </button>
        <button :disabled="isLoading" class="danger" @click="simulateInference('drift')">
          Simulate Drift
        </button>
        <button :disabled="isLoading" class="secondary" @click="simulateBatch('normal', 25)">
          Batch Normal ×25
        </button>
        <button :disabled="isLoading" class="danger-light" @click="simulateBatch('drift', 25)">
          Batch Drift ×25
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
        <span>Alerts</span>
        <strong :class="alertStatusClass()">
          {{ alertStatusLabel() }}
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


    <section class="panel alert-panel">
      <div class="panel-header">
        <div>
          <h2>Current Monitoring Alerts</h2>
          <p class="panel-subtitle">
            Alert rules evaluate recent latency, confidence, and KS drift detection results.
          </p>
        </div>

        <span class="alert-status" :class="alertStatusClass()">
          {{ alertStatusLabel() }}
        </span>
      </div>

      <section class="alert-summary-grid">
        <article class="mini-card">
          <span>Total Alerts</span>
          <strong>{{ alertsSummary?.alert_count ?? 0 }}</strong>
        </article>

        <article class="mini-card">
          <span>Critical</span>
          <strong>{{ alertsSummary?.critical_count ?? 0 }}</strong>
        </article>

        <article class="mini-card">
          <span>Warnings</span>
          <strong>{{ alertsSummary?.warning_count ?? 0 }}</strong>
        </article>

        <article class="mini-card">
          <span>Info</span>
          <strong>{{ alertsSummary?.info_count ?? 0 }}</strong>
        </article>
      </section>

      <div v-if="alertsSummary?.alerts?.length" class="alerts-list">
        <article
          v-for="alert in alertsSummary.alerts"
          :key="alert.name"
          class="alert-item"
          :class="`alert-item-${alert.severity}`"
        >
          <div>
            <strong>{{ alert.name }}</strong>
            <p>{{ alert.message }}</p>
          </div>

          <div class="alert-values">
            <span>Value: {{ formatNumber(alert.metric_value, 4) }}</span>
            <span>Threshold: {{ formatNumber(alert.threshold, 4) }}</span>
          </div>
        </article>
      </div>

      <p v-else class="success-message">
        No active alerts. Current monitoring signals are within configured thresholds.
      </p>

      <div class="thresholds">
        <span>
          p95 latency threshold:
          <strong>{{ formatNumber(alertsSummary?.thresholds?.latency_p95_threshold_ms) }} ms</strong>
        </span>
        <span>
          avg confidence threshold:
          <strong>{{ formatNumber(alertsSummary?.thresholds?.avg_confidence_threshold, 2) }}</strong>
        </span>
        <span>
          drift alpha:
          <strong>{{ formatNumber(alertsSummary?.thresholds?.drift_alpha, 2) }}</strong>
        </span>
      </div>
    </section>

    <section class="panel drift-panel">
      <div class="panel-header">
        <div>
          <h2>KS Data Drift Detection</h2>
          <p class="panel-subtitle">
            Comparing Iris training reference data against the latest production inference logs.
          </p>
        </div>

        <span
          class="drift-status"
          :class="driftReport?.drift_detected ? 'drift-alert' : 'drift-stable'"
        >
          {{ driftReport?.drift_detected ? 'Drift Detected' : 'No Drift Detected' }}
        </span>
      </div>

      <section class="drift-summary-grid">
        <article class="mini-card">
          <span>Profile</span>
          <strong>{{ driftReport?.profile || 'all' }}</strong>
        </article>

        <article class="mini-card">
          <span>Alpha</span>
          <strong>{{ driftReport?.alpha ?? 0.05 }}</strong>
        </article>

        <article class="mini-card">
          <span>Features Drifted</span>
          <strong>{{ driftedFeatureCount() }}</strong>
        </article>

        <article class="mini-card">
          <span>Min Samples</span>
          <strong>{{ driftReport?.min_samples ?? 20 }}</strong>
        </article>
      </section>

      <p v-if="hasInsufficientDriftData()" class="warning">
        Some features do not yet have enough production samples for the KS test.
        Generate more normal or drifted inference logs to complete the report.
      </p>

      <div class="table-wrapper">
        <table>
          <thead>
            <tr>
              <th>Feature</th>
              <th>Status</th>
              <th>KS Statistic</th>
              <th>p-value</th>
              <th>Reference Mean</th>
              <th>Production Mean</th>
              <th>Samples</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="feature in driftReport?.features || []" :key="feature.feature_name">
              <td>{{ feature.feature_name }}</td>
              <td>
                <span
                  class="drift-badge"
                  :class="feature.drift_detected ? 'drift-alert' : 'drift-stable'"
                >
                  {{ feature.insufficient_data ? 'waiting' : feature.drift_detected ? 'drift' : 'stable' }}
                </span>
              </td>
              <td>{{ formatNumber(feature.ks_statistic, 6) }}</td>
              <td>{{ formatNumber(feature.p_value, 6) }}</td>
              <td>{{ formatNumber(feature.reference_mean, 4) }}</td>
              <td>{{ formatNumber(feature.production_mean, 4) }}</td>
              <td>
                {{ feature.reference_sample_count }} /
                {{ feature.production_sample_count }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
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
