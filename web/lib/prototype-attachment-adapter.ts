import {
  generateId,
  type AttachmentAdapter,
  type CompleteAttachment,
  type PendingAttachment,
} from "@assistant-ui/react";

const MAX_FILE_SIZE = 25 * 1024 * 1024;

export class PrototypeAttachmentAdapter implements AttachmentAdapter {
  accept = "image/*,video/*,application/pdf";

  async add({ file }: { file: File }): Promise<PendingAttachment> {
    if (file.size > MAX_FILE_SIZE) throw new Error("Files must be 25 MB or smaller.");
    return {
      id: generateId(),
      type: file.type.startsWith("image/") ? "image" : "file",
      name: file.name,
      contentType: file.type,
      file,
      status: { type: "requires-action", reason: "composer-send" },
    };
  }

  async send(attachment: PendingAttachment): Promise<CompleteAttachment> {
    const body = new FormData();
    body.append("file", attachment.file);
    const response = await fetch("/api/uploads", { method: "POST", body });
    if (!response.ok) throw new Error(await response.text());
    const { url } = (await response.json()) as { url: string };
    return {
      ...attachment,
      status: { type: "complete" },
      content: attachment.contentType?.startsWith("image/")
        ? [{ type: "image", image: url }]
        : [{ type: "file", data: url, sourceType: "url", filename: attachment.name, mimeType: attachment.contentType || "application/octet-stream" }],
    };
  }

  async remove() {}
}
