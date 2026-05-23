import { cn } from '../../lib/utils'

export function Progress({ value = 0, className, ...props }) {
  return (
    <div
      className={cn('h-1.5 w-full overflow-hidden rounded-full bg-zinc-800', className)}
      {...props}
    >
      <div
        className="h-full rounded-full bg-admin-accent transition-all duration-300"
        style={{ width: `${Math.min(100, Math.max(0, value * 100))}%` }}
      />
    </div>
  )
}
