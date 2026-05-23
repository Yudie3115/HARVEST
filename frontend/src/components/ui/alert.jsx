import { cn } from '../../lib/utils'

const variants = {
  default: 'border-admin-border bg-admin-surface text-admin-text',
  success: 'border-green-500/30 bg-green-500/5 text-green-100',
  warning: 'border-yellow-500/30 bg-yellow-500/5 text-yellow-100',
  error: 'border-red-500/30 bg-red-500/5 text-red-100',
  info: 'border-blue-500/30 bg-blue-500/5 text-blue-100',
}

export function Alert({ className, variant = 'default', children, ...props }) {
  return (
    <div
      className={cn(
        'rounded-lg border px-4 py-3 text-sm',
        variants[variant],
        className,
      )}
      {...props}
    >
      {children}
    </div>
  )
}

export function AlertTitle({ className, children, ...props }) {
  return (
    <div className={cn('font-semibold mb-1', className)} {...props}>
      {children}
    </div>
  )
}

export function AlertDescription({ className, children, ...props }) {
  return (
    <div className={cn('text-sm opacity-90', className)} {...props}>
      {children}
    </div>
  )
}
