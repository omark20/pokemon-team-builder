// What every dialog on the page shares: a dimmed backdrop, a title, Escape to
// close, and Tab kept inside while it is open. Used by the account dialog and
// the delete-account dialog.
import type { KeyboardEvent, ReactNode } from "react";

// Tab from the last control goes to the first, and Shift+Tab from the first
// to the last, so focus never leaves the dialog.
function keepFocusInside(event: KeyboardEvent<HTMLElement>) {
  const controls = [...event.currentTarget.querySelectorAll<HTMLElement>("input, button:not(:disabled)")];
  const [first, last] = [controls[0], controls[controls.length - 1]];
  const leaving = event.shiftKey ? document.activeElement === first : document.activeElement === last;
  if (!leaving) return;
  event.preventDefault();
  (event.shiftKey ? last : first)?.focus();
}

interface FrameProps {
  title: string;
  onClose: () => void;
  children: ReactNode;
}

export function DialogFrame({ title, onClose, children }: FrameProps) {
  function onKeyDown(event: KeyboardEvent<HTMLElement>) {
    if (event.key === "Escape") onClose();
    if (event.key === "Tab") keepFocusInside(event);
  }
  return (
    <div className="dialog-backdrop">
      <div className="dialog" role="dialog" aria-modal="true" aria-labelledby="dialog-title" onKeyDown={onKeyDown}>
        <h2 id="dialog-title">{title}</h2>
        {children}
      </div>
    </div>
  );
}
