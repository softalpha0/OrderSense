"use client";

import { useEffect, useMemo, useState } from "react";
import { getStatus, getMetrics, startBot, stopBot, wsUrl } from "../lib/api";
import { StatusCard } from "../components/StatusCard";
import { MetricsTable } from "../components/MetricsTable";
import { EventsFeed } from "../components/EventsFeed";

export default function Page() {
  const [running, setRunning] = useState(false);
  const [metrics, setMetrics] = useState<any>({});
  const [events, setEvents] = useState<any[]>([]);
  const ws = useMemo(() => wsUrl(), []);

  useEffect(() => {
    (async () => {
      const s = await getStatus();
      setRunning(!!s.running);
      setMetrics(await getMetrics());
    })();
  }, []);

  useEffect(() => {
    const sock = new WebSocket(ws);
    sock.onmessage = (msg) => {
      const data = JSON.parse(msg.data);
      setMetrics(data.metrics);
      setEvents(data.events);
    };
    return () => sock.close();
  }, [ws]);

  return (
    <main style={{ display: "grid", gap: 12, maxWidth: 1100, margin: "0 auto" }}>
      <h1 style={{ margin: "12px 0" }}>OrderSense</h1>

      <div style={{ display: "flex", gap: 12 }}>
        <StatusCard running={running} />
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <button onClick={async () => { await startBot(); setRunning(true); }}>
            Start
          </button>
          <button onClick={async () => { await stopBot(); setRunning(false); }}>
            Stop
          </button>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        <MetricsTable metrics={metrics} />
        <EventsFeed events={events} />
      </div>
    </main>
  );
}