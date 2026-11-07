export type ParsedFiles = { files: Record<string, string> } | { error: string };

/** Validates the JSON editor content: an object mapping relative paths to file contents. */
export function parseFiles(text: string): ParsedFiles {
  let value: unknown;
  try {
    value = JSON.parse(text);
  } catch {
    return { error: "Files must be valid JSON." };
  }
  if (typeof value !== "object" || value === null || Array.isArray(value) || Object.keys(value).length === 0) {
    return { error: 'Files must be a non-empty object like {"app.py": "..."}.' };
  }
  if (!Object.values(value).every((v) => typeof v === "string")) {
    return { error: "Every file's content must be a string." };
  }
  return { files: value as Record<string, string> };
}

export const MAX_IMAGE_BYTES = 8_000_000;
const IMAGE_TYPES = ["image/png", "image/jpeg"];

export type DroppedKind = "image" | "text" | "unsupported" | "too-large";

export function classifyFile(file: { name: string; type: string; size: number }): DroppedKind {
  if (IMAGE_TYPES.includes(file.type)) return file.size > MAX_IMAGE_BYTES ? "too-large" : "image";
  if (file.type.startsWith("text/") || /\.(txt|md|markdown)$/i.test(file.name)) return "text";
  return "unsupported";
}

/** Base64 payload of a data URI, without the "data:...;base64," prefix the API rejects. */
export const stripDataUri = (dataUri: string): string => dataUri.slice(dataUri.indexOf(",") + 1);

export function readDataUri(file: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}
