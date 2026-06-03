export default function ToastContainer({ toasts }) {
  if (toasts.length === 0) return null

  return (
    <div className="toasts">
      {toasts.map(t => (
        <div key={t.id} className={`toast ${t.type}`}>
          {t.msg}
        </div>
      ))}
    </div>
  )
}
