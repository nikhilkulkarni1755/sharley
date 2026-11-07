"use client";

import { useEffect, useRef } from "react";

interface Props {
  onCapture: (png: File) => void;
  onClose: (reason?: string) => void;
}

const NO_CAMERA = "Camera unavailable or permission denied. Use Take a photo or choose a file instead.";

/** Live camera preview; the stream is always released on capture, close, error and unmount. */
export default function Webcam({ onCapture, onClose }: Props) {
  const video = useRef<HTMLVideoElement>(null);
  const stream = useRef<MediaStream | null>(null);

  const release = () => stream.current?.getTracks().forEach((t) => t.stop());

  useEffect(() => {
    let cancelled = false;
    Promise.resolve()
      .then(() => navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } }))
      .then((s) => {
        stream.current = s;
        if (cancelled) return release();
        video.current!.srcObject = s;
      })
      .catch(() => onClose(NO_CAMERA));
    return () => {
      cancelled = true;
      release();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- open the camera once per mount
  }, []);

  const capture = () => {
    const v = video.current!;
    const canvas = document.createElement("canvas");
    canvas.width = v.videoWidth;
    canvas.height = v.videoHeight;
    canvas.getContext("2d")!.drawImage(v, 0, 0);
    canvas.toBlob((blob) => {
      release();
      if (blob) onCapture(new File([blob], "webcam.png", { type: "image/png" }));
      else onClose("Could not capture the frame, try again.");
    }, "image/png");
  };

  return (
    <div className="webcam panel">
      <video ref={video} autoPlay playsInline muted aria-label="Webcam preview" />
      <div className="row">
        <button className="primary" onClick={capture}>Capture</button>
        <button onClick={() => onClose()}>Cancel</button>
      </div>
    </div>
  );
}
