
## Backend storage integration

This backend runtime extends the standalone tooling with S3 synchronization.
`/workspace/inputs/` is read-only and receives session uploads automatically.
Keep edits, downloaded assets and working files outside that directory.

Save the editable native master with `render.save_scene()`. To update the
frontend's scene, also export a self-contained GLB to `/workspace/scene.glb`.
The supervisor publishes that GLB to the session's storage and restores it in
replacement sandboxes. Native `.blend` files and render PNGs stay local under
the existing storage contract. Executor reconnect preserves the live Blender
process and its files.
