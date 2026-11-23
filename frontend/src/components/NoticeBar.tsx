// The result of the last thing the visitor did, kept in view at the bottom of
// the window, since the grid's Add buttons may be far below the team.
//
// Screen readers announce a change inside a live region that is already on the
// page, so the two regions (polite for news, assertive for errors) are always
// mounted; each notice gets a fresh node, so a repeated message is announced too.
import { useRef } from "react";
import type { Notice } from "../teamsState";

// A number that changes whenever a new notice object arrives.
function useNoticeNumber(notice: Notice | null): number {
  const last = useRef<{ notice: Notice | null; number: number }>({ notice: null, number: 0 });
  if (last.current.notice !== notice) last.current = { notice, number: last.current.number + 1 };
  return last.current.number;
}

export function NoticeBar({ notice, onClose }: { notice: Notice | null; onClose: () => void }) {
  const number = useNoticeNumber(notice);
  const announce = (kind: Notice["kind"]) =>
    notice?.kind === kind && <span key={number}>{notice.text}</span>;
  return (
    <>
      <div className="visually-hidden notice-live" aria-live="polite">
        {announce("info")}
      </div>
      <div className="visually-hidden notice-live" aria-live="assertive">
        {announce("error")}
      </div>
      {notice && (
        <div className={`notice-bar notice-${notice.kind}`}>
          <span>{notice.text}</span>
          <button type="button" className="notice-close" aria-label="Close message" onClick={onClose}>
            ×
          </button>
        </div>
      )}
    </>
  );
}
