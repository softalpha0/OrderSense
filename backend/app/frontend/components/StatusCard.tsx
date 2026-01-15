export function StatusCard({ running }: { running: boolean }) {
  return (
    <div style={{ border: "1px solid #ddd", padding: 12, borderRadius: 10 }}>
      <div style={{ fontWeight: 700 }}>Status</div>
      <div>{running ? "RUNNING" : "STOPPED"}</div>
    </div>
  );
}