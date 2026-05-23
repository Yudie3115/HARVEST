import { cn } from '../../lib/utils'

const variants = {
  default: 'bg-zinc-800 text-zinc-300 border-zinc-700',
  success: 'bg-green-500/10 text-green-400 border-green-500/20',
  warning: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20',
  error: 'bg-red-500/10 text-red-400 border-red-500/20',
  info: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
}

const statusMap = {
  processed: 'success',
  processing: 'info',
  queued: 'info',
  discovered: 'default',
  failed: 'error',
  skipped: 'warning',
}

export function Badge({ className, variant, status, children, ...props }) {
  const v = variant || statusMap[status] || 'default'
  return (
    <span
      className={cn(
        'inline-flex items-center rounded border px-1.5 py-0.5 text-[11px] font-medium',
        variants[v],
        className,
      )}
      {...props}
    >
      {children}
    </span>
  )
}
