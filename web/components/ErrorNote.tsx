export default function ErrorNote({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="note bad">
      <span>{message}</span>
      {onRetry && <button onClick={onRetry}>Retry</button>}
    </div>
  );
}
