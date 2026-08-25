import { Component, type ErrorInfo, type ReactNode } from 'react';

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  message: string;
}

export default class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { hasError: false, message: '' };

  static getDerivedStateFromError(error: unknown): ErrorBoundaryState {
    return { hasError: true, message: error instanceof Error ? error.message : 'Error inesperado' };
  }

  componentDidCatch(error: unknown, info: ErrorInfo) {
    console.error('ErrorBoundary capturó un error:', error, info);
  }

  handleReload = () => {
    this.setState({ hasError: false, message: '' });
  };

  render() {
    if (!this.state.hasError) return this.props.children;

    return (
      <div className="flex min-h-screen items-center justify-center bg-yeikar-tertiary p-6">
        <div className="w-full max-w-md rounded-2xl border border-yeikar-secondary-light/10 bg-white p-8 text-center shadow-card">
          <div className="mx-auto mb-5 flex h-12 w-12 items-center justify-center rounded-xl bg-yeikar-primary font-headline text-2xl font-black text-yeikar-neutral shadow-gold">
            Y
          </div>
          <h1 className="font-headline text-xl font-black tracking-tight text-yeikar-neutral">
            Algo salió mal
          </h1>
          <p className="mt-2 text-sm leading-relaxed text-yeikar-neutral/55">
            Ocurrió un error inesperado en la aplicación. Tu información está a salvo.
          </p>
          {this.state.message && (
            <p className="mt-2 font-mono text-xs text-yeikar-neutral/40">{this.state.message}</p>
          )}
          <button
            type="button"
            onClick={this.handleReload}
            className="mt-6 inline-flex items-center gap-2 rounded-xl bg-yeikar-primary px-5 py-2.5 font-headline text-sm font-bold text-yeikar-neutral shadow-gold transition-colors hover:bg-yeikar-primary-light"
          >
            Volver a intentar
          </button>
        </div>
      </div>
    );
  }
}
