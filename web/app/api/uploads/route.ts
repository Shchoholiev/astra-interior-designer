import { randomUUID } from "node:crypto";
import { mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { NextResponse } from "next/server";

const MAX_FILE_SIZE = 25 * 1024 * 1024;
export const runtime = "nodejs";

export async function POST(request: Request) {
  const data = await request.formData();
  const file = data.get("file");
  if (!(file instanceof File)) return new NextResponse("A file is required.", { status: 400 });
  if (file.size > MAX_FILE_SIZE) return new NextResponse("Files must be 25 MB or smaller.", { status: 413 });

  const id = randomUUID();
  const directory = path.join(tmpdir(), "astra-interior-designer", "uploads");
  await mkdir(directory, { recursive: true });
  await Promise.all([
    writeFile(path.join(directory, `${id}.bin`), Buffer.from(await file.arrayBuffer())),
    writeFile(path.join(directory, `${id}.json`), JSON.stringify({ name: file.name, type: file.type })),
  ]);

  return NextResponse.json({ id, url: `/api/uploads/${id}` });
}
