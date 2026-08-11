export function InitialLoadingScreen() {
  return (
    <div className="initial-loading" role="status" aria-label="Carregando agenda">
      <div className="loading-field" aria-hidden="true">
        <span className="loading-wave" />
        <span className="loading-wave loading-wave-two" />
        <span className="loading-wave loading-wave-three" />
      </div>
      <div className="loading-content">
        <span className="loading-brand">algarys</span>
        <span className="loading-rule" aria-hidden="true">
          <span />
        </span>
        <p>Preparando sua agenda</p>
      </div>
    </div>
  );
}
