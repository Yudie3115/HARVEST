import { cn } from '../../lib/utils'

const variants = {
  default: 'bg-admin-accent text-black hover:bg-green-400 font-medium',
  outline: 'border border-admin-border text-admin-muted hover:bg-admin-hover hover:text-admin-text',
  ghost: 'text-admin-muted hover:bg-admin-hover hover:text-admin-text',
  destructive: 'bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20',
}

const sizes = {
  sm: 'h-7 px-3 text-xs',
  default: 'h-9 px-4 text-sm',
  lg: 'h-10 px-6 text-sm',
}

export function Button({
  className,
  variant = 'default',
  size = 'default',
  disabled,
  children,
  ...props
}) {
  return (
    <button
      className={cn(
        'inline-flex items-center justify-center gap-2 rounded-md transition-colors',
        'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-admin-accent',
        'disabled:pointer-events-none disabled:opacity-40',
        variants[variant],
        sizes[size],
        className,
      )}
      disabled={disabled}
      {...props}
    >
      {children}
    </button>
  )
}
