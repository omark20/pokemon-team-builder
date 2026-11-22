// Lint rules, including the size and nesting limits the project holds itself
// to: 40 lines of code per function (60 for a React component, whose body is
// mostly markup), 3 levels of nesting, complexity 10, 300 lines per file and
// 200 per component file. Test files have no file limit.
import js from "@eslint/js";
import tseslint from "typescript-eslint";
import { defineConfig } from "eslint/config";

export default defineConfig(
  { ignores: ["dist", "node_modules"] },
  js.configs.recommended,
  tseslint.configs.recommended,
  {
    rules: {
      "max-lines-per-function": ["error", { max: 40, skipBlankLines: true, skipComments: true }],
      "max-depth": ["error", 3],
      complexity: ["error", 10],
      "max-lines": ["error", 300],
    },
  },
  {
    files: ["src/components/**"],
    rules: {
      "max-lines-per-function": ["error", { max: 60, skipBlankLines: true, skipComments: true }],
      "max-lines": ["error", 200],
    },
  },
  {
    files: ["**/*.test.ts", "**/*.test.tsx"],
    rules: { "max-lines": "off" },
  },
);
