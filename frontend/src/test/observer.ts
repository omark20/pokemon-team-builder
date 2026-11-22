// jsdom has no IntersectionObserver. This stand-in records every live observer
// so a test can say "the watched element scrolled into view".
type Callback = (entries: { isIntersecting: boolean }[]) => void;

const live = new Set<FakeIntersectionObserver>();

export class FakeIntersectionObserver {
  private readonly callback: Callback;

  constructor(callback: Callback) {
    this.callback = callback;
    live.add(this);
  }

  observe(): void {}

  disconnect(): void {
    live.delete(this);
  }

  trigger(): void {
    this.callback([{ isIntersecting: true }]);
  }
}

export function scrollSentinelIntoView(): void {
  for (const observer of [...live]) observer.trigger();
}
