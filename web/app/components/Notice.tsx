"use client";

interface NoticeProps {
  message: string;
  onDismiss: () => void;
}

// Aviso não bloqueante (falha de rede, API fora) exibido abaixo do header.
export function Notice({ message, onDismiss }: NoticeProps) {
  return (
    <div className="notice" role="status">
      <span>{message}</span>
      <button
        type="button"
        className="btn btn-ghost"
        onClick={onDismiss}
        aria-label="Fechar aviso"
      >
        ×
      </button>
    </div>
  );
}
