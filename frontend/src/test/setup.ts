// Runs before every test file: after each test, unmount what was rendered and
// put back anything a test replaced (such as `fetch`).
import { afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
