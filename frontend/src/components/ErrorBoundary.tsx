// Catches an error thrown while the page draws, which would otherwise unmount
// everything and leave a blank page, and shows a way back instead. The visitor's
// teams are stored on the server, so reloading loses nothing. The error goes to
// the browser's console and nowhere else. React offers this only to classes.
import { Component, type ErrorInfo, type ReactNode } from "react";

export const PAGE_FAILED = "Something went wrong on this page. Your teams are saved.";

interface BoundaryState {
  failed: boolean;
}

export class ErrorBoundary extends Component<{ children: ReactNode }, BoundaryState> {
  state: BoundaryState = { failed: false };

  static getDerivedStateFromError(): BoundaryState {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("The page failed to render:", error, info.componentStack);
  }

  render(): ReactNode {
    if (!this.state.failed) return this.props.children;
    return (
      <main className="page">
        <h1>Pokémon Team Builder</h1>
        <section className="face-off">
          <div className="face-off-message" role="alert">
            <p>{PAGE_FAILED}</p>
            <button type="button" className="primary" onClick={() => window.location.reload()}>
              Reload the page
            </button>
          </div>
        </section>
      </main>
    );
  }
}
