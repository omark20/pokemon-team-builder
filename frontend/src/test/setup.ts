// Runs before every test file: unmount rendered components after each test and
// provide the IntersectionObserver that jsdom lacks.
import { afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";
import { FakeIntersectionObserver } from "./observer";

vi.stubGlobal("IntersectionObserver", FakeIntersectionObserver);
afterEach(cleanup);
