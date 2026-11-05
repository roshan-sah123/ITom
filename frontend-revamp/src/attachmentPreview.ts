export function attachmentViewUrl(path: string, name: string) {
  return `/?${new URLSearchParams({ attachment: path, name })}`;
}

export function previewEndpoint(path: string) {
  if (!/^\/api\/v1\/(?:knowledge\/content\/[1-9]\d*\/file|vendors\/submissions\/[1-9]\d*\/sop)$/.test(path))
    throw new Error("Preview unavailable: invalid attachment address.");
  return `${path}?preview=true`;
}

export function previewText(bytes: Uint8Array) {
  const encoding = bytes[0] === 255 && bytes[1] === 254 ? "utf-16le"
    : bytes[0] === 254 && bytes[1] === 255 ? "utf-16be" : "utf-8";
  return new TextDecoder(encoding).decode(bytes);
}
