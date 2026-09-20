import { useRef, useState } from 'react';
export function useUploadZone(onUpload: (files: File[]) => void, disabled: boolean) {
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const onDrop = (e: React.DragEvent) => { e.preventDefault(); setDragging(false); if (!disabled) onUpload(Array.from(e.dataTransfer.files)); };
  return { input, dragging, setDragging, onDrop };
}
