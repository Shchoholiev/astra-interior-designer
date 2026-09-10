import { readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { NextResponse } from "next/server";

export const runtime = "nodejs";

export async function GET(_: Request, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  if (!/^[0-9a-f-]{36}$/.test(id)) return new NextResponse("Not found", { status: 404 });
  const directory = path.join(tmpdir(), "astra-interior-designer", "uploads");
  try {
    const [bytes, metadata] = await Promise.all([
      readFile(path.join(directory, `${id}.bin`)),
      readFile(path.join(directory, `${id}.json`), "utf8"),
    ]);
    const { type } = JSON.parse(metadata) as { type: string };
    return new NextResponse(bytes, { headers: { "Content-Type": type || "application/octet-stream", "Cache-Control": "private, max-age=3600" } });
  } catch {
    return new NextResponse("Not found", { status: 404 });
  }
}
