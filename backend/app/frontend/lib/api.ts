const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

export async function getStatus() {
  return fetch(`${BACKEND}/api/status`).then(r => r.json());
}
export async function getMetrics() {
  return fetch(`${BACKEND}/api/metrics`).then(r => r.json());
}
export async function getEvents() {
  return fetch(`${BACKEND}/api/events`).then(r => r.json());
}
export async function startBot() {
  return fetch(`${BACKEND}/api/start`, { method: "POST" }).then(r => r.json());
}
export async function stopBot() {
  return fetch(`${BACKEND}/api/stop`, { method: "POST" }).then(r => r.json());
}
export function wsUrl() {
  return BACKEND.replace("http", "ws") + "/ws";
}