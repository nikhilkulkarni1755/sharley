const LINES = ["M0,20 L100,35", "M0,50 L100,45", "M0,80 L100,60", "M15,0 L35,100", "M60,0 L85,100"];

export default function TraceImage({ src }: { src: string }) {
  return (
    <div className="trace-wrap" role="status" aria-label="Reading the image">
      {/* eslint-disable-next-line @next/next/no-img-element -- local data URI preview */}
      <img src={src} alt="Uploaded spec screenshot" />
      <svg data-testid="trace" className="trace" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
        {LINES.map((d, i) => (
          <path key={d} d={d} pathLength={1} style={{ animationDelay: `${i * 0.35}s` }} />
        ))}
      </svg>
    </div>
  );
}
