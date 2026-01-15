export function MetricsTable({ metrics }: { metrics: any }) {
  return (
    <div style={{ border: "1px solid #ddd", padding: 12, borderRadius: 10 }}>
      <div style={{ fontWeight: 700, marginBottom: 8 }}>Metrics</div>
      <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>{JSON.stringify(metrics, null, 2)}</pre>
    </div>
  );
}