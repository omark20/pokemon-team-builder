// Runs before every test file: after each test, unmount what was rendered and
// put back anything a test replaced (such as `fetch`); and provide the
// IntersectionObserver that jsdom lacks.
import { afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";
import { FakeIntersectionObserver } from "./observer";

vi.stubGlobal("IntersectionObserver", FakeIntersectionObserver);
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
