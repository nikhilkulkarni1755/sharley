import type { Bank } from "./types";

export const projectFilename = (bank: Bank) => `sharley-project-${bank.spec_hash.slice(0, 8)}.zip`;

/** Triggers a browser download of `blob` through a temporary link. */
export function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
