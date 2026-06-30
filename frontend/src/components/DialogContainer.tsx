import { useState, useEffect } from 'react';

type DialogType = 'alert' | 'confirm';

interface DialogOptions {
  message: string;
  type: DialogType;
  title?: string;
  confirmText?: string;
  cancelText?: string;
  resolve: (value: any) => void;
}

class DialogService {
  private listener: ((options: DialogOptions | null) => void) | null = null;

  subscribe(listener: (options: DialogOptions | null) => void) {
    this.listener = listener;
    return () => {
      this.listener = null;
    };
  }

  alert(message: string, options: Omit<DialogOptions, 'message' | 'type' | 'resolve'> = {}): Promise<void> {
    return new Promise((resolve) => {
      if (this.listener) {
        this.listener({ message, type: 'alert', ...options, resolve });
      } else {
        window.alert(message);
        resolve();
      }
    });
  }

  confirm(message: string, options: Omit<DialogOptions, 'message' | 'type' | 'resolve'> = {}): Promise<boolean> {
    return new Promise((resolve) => {
      if (this.listener) {
        this.listener({ message, type: 'confirm', ...options, resolve });
      } else {
        resolve(window.confirm(message));
      }
    });
  }
}

export const dialog = new DialogService();

export default function DialogContainer() {
  const [options, setOptions] = useState<DialogOptions | null>(null);

  useEffect(() => {
    return dialog.subscribe(setOptions);
  }, []);

  if (!options) return null;

  const handleConfirm = () => {
    options.resolve(options.type === 'confirm' ? true : undefined);
    setOptions(null);
  };

  const handleCancel = () => {
    if (options.type === 'confirm') {
      options.resolve(false);
    } else {
      options.resolve(undefined);
    }
    setOptions(null);
  };

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-fade-in">
      <div 
        className="bg-[var(--color-bg-elevated)] border border-white/10 rounded-2xl p-6 max-w-sm w-full shadow-2xl animate-slide-up"
        role="dialog"
        aria-modal="true"
      >
        <h3 className="text-lg font-semibold text-white mb-2">
          {options.title || (options.type === 'confirm' ? 'Confirm' : 'Alert')}
        </h3>
        <p className="text-[var(--color-text-secondary)] text-sm mb-6 leading-relaxed whitespace-pre-wrap">
          {options.message}
        </p>
        <div className="flex justify-end gap-3">
          {options.type === 'confirm' && (
            <button
              onClick={handleCancel}
              className="px-4 py-2 rounded-lg text-sm font-medium text-white hover:bg-white/10 transition-colors"
            >
              {options.cancelText || 'Cancel'}
            </button>
          )}
          <button
            onClick={handleConfirm}
            className="px-4 py-2 rounded-lg text-sm font-medium bg-[var(--color-primary)] hover:brightness-110 text-white transition-all shadow-lg shadow-indigo-500/20"
          >
            {options.confirmText || 'OK'}
          </button>
        </div>
      </div>
    </div>
  );
}
