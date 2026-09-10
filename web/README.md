# Astra Interior Designer UI

Next.js and TypeScript prototype for the post-GLB experience: a reusable chat panel beside an interactive Three.js room viewer.

## Run locally

```bash
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173).

The UI starts in self-contained demo mode. To connect it to FastAPI, copy
`.env.example` to `.env.local`, set the server-only API URL and token, and set
`NEXT_PUBLIC_ASTRA_BACKEND_ENABLED=true`. The browser talks through the Next.js
proxy, so `ASTRA_API_KEY` is never included in client JavaScript.

## Included

- `@assistant-ui/react` for chat messages, composer, attachments, and cancellation
- React Three Fiber, Drei, and Three.js for GLB rendering, orbit controls, and first-person walking
- A blank viewer until the selected session has a generated GLB
- A demo adapter plus a FastAPI adapter for native Agents API SSE events
- Presigned S3 uploads capped at 25 MB when connected; temporary local uploads in demo mode
- Backend-listed session switching, explicit turn cancellation, Blender tool-status labels, and generated GLB refresh

The API client is in `lib/astra-api.ts`, presigned uploads are implemented in
`lib/astra-attachment-adapter.ts`, and the authenticated streaming proxy is in
`app/api/astra/[...path]/route.ts`.

## Checks

```bash
npm run lint
npm run build
```
