export function EventsFeed({ events }: { events: any[] }) {
  return (
    <div style={{ border: "1px solid #ddd", padding: 12, borderRadius: 10 }}>
      <div style={{ fontWeight: 700, marginBottom: 8 }}>Live events</div>
      <div style={{ maxHeight: 420, overflow: "auto" }}>
        {events.map((e, idx) => (
          <div key={idx} style={{ padding: "8px 0", borderBottom: "1px solid #eee" }}>
            <div style={{ fontSize: 12, opacity: 0.7 }}>{new Date((e.ts ?? Date.now()) * 1000).toLocaleString()}</div>
            <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>{JSON.stringify(e, null, 2)}</pre>
          </div>
        ))}
      </div>
    </div>
  );
}