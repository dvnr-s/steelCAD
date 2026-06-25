import { Component } from 'react'

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  componentDidCatch(error, info) {
    console.error('[ErrorBoundary]', error, info.componentStack)
  }

  render() {
    if (!this.state.hasError) return this.props.children

    return (
      <div
        style={{
          minHeight: '100vh', display: 'flex', alignItems: 'center',
          justifyContent: 'center', padding: 32, background: 'var(--c-bg)',
        }}
      >
        <div
          className="card"
          style={{ maxWidth: 480, width: '100%', padding: 32, textAlign: 'center' }}
        >
          <div style={{ fontSize: 40, marginBottom: 16 }}>⚠</div>
          <h2 style={{ marginBottom: 8 }}>Something went wrong</h2>
          <p style={{ color: 'var(--c-text-muted)', marginBottom: 24 }}>
            An unexpected error occurred. Please reload the page. If the problem
            persists, contact your system administrator.
          </p>
          {this.state.error && (
            <pre style={{
              background: 'var(--c-surface-2)', border: '1px solid var(--c-border)',
              borderRadius: 'var(--radius)', padding: 12, textAlign: 'left',
              fontSize: '0.75rem', overflowX: 'auto', marginBottom: 24,
              color: 'var(--c-error)',
            }}>
              {this.state.error.message}
            </pre>
          )}
          <button
            className="btn btn-primary"
            onClick={() => window.location.reload()}
          >
            Reload Page
          </button>
        </div>
      </div>
    )
  }
}
