export default function AnalyzeButton({ loading, disabled, onClick }) {
  return (
    <button className="btn" onClick={onClick} disabled={disabled || loading}>
      {loading ? (
        <>
          <Spinner />
          Analysing…
        </>
      ) : (
        <>
          Run analysis
          <ArrowIcon />
        </>
      )}
    </button>
  )
}

function Spinner() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true"
      style={{ animation: 'spin 0.8s linear infinite' }}>
      <circle cx="7" cy="7" r="5.5" stroke="currentColor" strokeWidth="2" opacity="0.25" />
      <path d="M12.5 7A5.5 5.5 0 0 0 7 1.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  )
}

function ArrowIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 15 15" fill="none" aria-hidden="true">
      <path d="M3 7.5h8M7.5 4l3.5 3.5-3.5 3.5" stroke="currentColor" strokeWidth="1.8"
        strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}
