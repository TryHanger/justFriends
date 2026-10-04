# React + TypeScript + Vite

This template provides a minimal setup to get React working in Vite with HMR and some Oxlint rules.

## Running checks

Use Node.js 24.x, version 24.15 or newer (verified with 24.18). The test dependencies
require a newer Node.js runtime than Vite's minimum supported version.

```sh
npm ci
npm test
npm run lint
npm run build
```

The form regression tests render the real React components and replace only the
Axios HTTP transport. They cover validation errors, plain server messages,
unrecognized error payloads, and network failures without a running backend or
external API calls.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the Oxlint configuration

If you are developing a production application, we recommend enabling type-aware lint rules by installing `oxlint-tsgolint` and editing `.oxlintrc.json`:

```json
{
  "$schema": "./node_modules/oxlint/configuration_schema.json",
  "plugins": ["react", "typescript", "oxc"],
  "options": {
    "typeAware": true
  },
  "rules": {
    "react/rules-of-hooks": "error",
    "react/only-export-components": ["warn", { "allowConstantExport": true }]
  }
}
```

See the [Oxlint rules documentation](https://oxc.rs/docs/guide/usage/linter/rules) for the full list of rules and categories.

## Backend API address

The frontend defaults to `http://localhost:8000/api/v1`. To use another backend,
copy `.env.example` to `.env.local` and set `VITE_API_BASE_URL` to the **full API prefix**,
including `/api/v1`. For example, `https://api.example.org/api/v1`
uses a separate server, while `/api/v1` uses the frontend's origin. Requests and
JSON/CSV download links use the same prefix. Vite reads this setting at build
time, so restart the development server or rebuild after changing it. When the
backend is on another origin, its `CORS_ORIGINS` must allow the frontend origin.
