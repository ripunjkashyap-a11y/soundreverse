export default function MusicianNotes({ musician }) {
  if (!musician) return null

  const {
    tuning_targets = [],
    tuning_tip,
    tonal_tags = [],
    tonal_character,
  } = musician

  const hasTonal = tonal_tags.length > 0 || tonal_character
  const hasTuning = tuning_targets.length > 0
  if (!hasTonal && !hasTuning) return null

  const CHIPS = ['chip-blue', 'chip-amber', 'chip-green', 'chip-magenta']

  return (
    <section className="card col-7">
      <div className="card-head">
        <p className="label">For musicians</p>
      </div>

      {hasTonal && (
        <div style={{ marginBottom: hasTuning ? 20 : 0 }}>
          {tonal_tags.length > 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 12 }}>
              {tonal_tags.map((tag, i) => (
                <span key={tag} className={`chip ${CHIPS[i % CHIPS.length]}`}>{tag}</span>
              ))}
            </div>
          )}
          {tonal_character && (
            <p style={{ margin: 0, fontSize: 13.5, color: 'var(--text-2)', lineHeight: 1.65 }}>
              {tonal_character}
            </p>
          )}
        </div>
      )}

      {hasTuning && (
        <>
          <p className="label" style={{ marginBottom: 10 }}>Tuning targets</p>
          <table className="dtable">
            <thead>
              <tr>
                <th>Element</th>
                <th className="right">Frequency</th>
                <th className="right">Note</th>
              </tr>
            </thead>
            <tbody>
              {tuning_targets.map(t => (
                <tr key={t.element}>
                  <td>{t.element}</td>
                  <td className="right mono" style={{ color: 'var(--text-1)' }}>
                    {t.hz}<span style={{ color: 'var(--text-4)', marginLeft: 3 }}>Hz</span>
                  </td>
                  <td className="right">
                    <span className="chip chip-blue mono">{t.note}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {tuning_tip && (
            <p style={{ margin: '14px 0 0', fontSize: 12.5, color: 'var(--text-3)', lineHeight: 1.6 }}>
              {tuning_tip}
            </p>
          )}
        </>
      )}
    </section>
  )
}
