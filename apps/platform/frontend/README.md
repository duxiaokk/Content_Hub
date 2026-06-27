# Frontend Build Baseline

## Baseline

- Node.js: `20.18.0` or newer in the Node 20 LTS line
- npm: `10.x` or `11.x`
- Install command: `npm ci`
- Build command: `npm run build`

The frontend lockfile is committed. Use `npm ci` for reproducible installs. Do not use `npm install` as the default team workflow unless you are intentionally updating dependencies.

## Standard build flow

```bash
cd apps/platform/frontend
npm ci
npm run build
```

The production bundle is written to `apps/platform/frontend/dist`.

## Windows

```powershell
cd D:\Python\content_hub\apps\platform\frontend
node -v
npm -v
npm ci
npm run build
```

Expected baseline:

- `node -v` starts with `v20.`
- `npm -v` starts with `10.` or `11.`

## Linux

```bash
cd /path/to/content_hub/apps/platform/frontend
node -v
npm -v
npm ci
npm run build
```

If `nvm` is available:

```bash
nvm use
npm ci
npm run build
```

## Common failures

- Old Node runtime:
  Vite 6 and the current TypeScript toolchain should be validated against Node 20 LTS first.
- Dirty `node_modules`:
  If the lockfile and installed modules drift, remove `node_modules` and rerun `npm ci`.
- Lockfile mismatch:
  If `package.json` changes without a matching `package-lock.json` update, `npm ci` will fail by design.
- Shell path differences on Windows:
  Run the commands from PowerShell or a shell with Node/npm on `PATH`.

## Notes

- The dev server still uses the proxy in `vite.config.ts` and expects the backend on `http://localhost:8000`.
- This document defines the team baseline for local reproduction; CI should use the same Node major version.

## CI smoke

- GitHub Actions runs the frontend smoke build in `.github/workflows/frontend-build-smoke.yml`.
- The CI baseline matches local reproduction:
  - Node.js `20.18.0`
  - `npm ci`
  - `npm run build`
- The workflow prints `node -v` and `npm -v` before install so environment drift is visible in logs.
