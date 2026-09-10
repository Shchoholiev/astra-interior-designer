import {
  generateId,
  type AttachmentAdapter,
  type CompleteAttachment,
  type PendingAttachment,
} from "@assistant-ui/react";

import type { AstraApi } from "@/lib/astra-api";

const MAX_FILE_SIZE = 25 * 1024 * 1024;

export class AstraAttachmentAdapter implements AttachmentAdapter {
  accept = "image/*,video/*,application/pdf";
  private objectKeys = new Map<string, string>();

  constructor(private api: AstraApi) {}

  keysFor(ids: string[]) {
    return ids.map((id) => this.objectKeys.get(id)).filter((key): key is string => Boolean(key));
  }

  async add({ file }: { file: File }): Promise<PendingAttachment> {
    if (file.size > MAX_FILE_SIZE) throw new Error("Files must be 25 MB or smaller.");
    return {
      id: generateId(),
      type: file.type.startsWith("image/") ? "image" : "file",
      name: file.name,
      contentType: file.type || "application/octet-stream",
      file,
      status: { type: "requires-action", reason: "composer-send" },
    };
  }

  async send(attachment: PendingAttachment): Promise<CompleteAttachment> {
    const contentType = attachment.contentType || "application/octet-stream";
    const upload = await this.api.createUpload(attachment.name, contentType);
    const response = await fetch(upload.upload_url, {
      method: "PUT",
      headers: upload.headers,
      body: attachment.file,
    });
    if (!response.ok) throw new Error(`Upload failed (${response.status}).`);
    this.objectKeys.set(attachment.id, upload.object_key);
    const previewUrl = URL.createObjectURL(attachment.file);
    return {
      ...attachment,
      status: { type: "complete" },
      content: attachment.type === "image"
        ? [{ type: "image", image: previewUrl, filename: attachment.name }]
        : [{ type: "file", data: previewUrl, sourceType: "url", filename: attachment.name, mimeType: contentType }],
    };
  }

  async remove(attachment: CompleteAttachment) {
    this.objectKeys.delete(attachment.id);
    for (const part of attachment.content) {
      const url = part.type === "image" ? part.image : part.type === "file" ? part.data : null;
      if (url?.startsWith("blob:")) URL.revokeObjectURL(url);
    }
  }
}
