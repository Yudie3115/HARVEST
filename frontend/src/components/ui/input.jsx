import { cn } from '../../lib/utils'

export function Input({ className, ...props }) {
  return (
    <input
      className={cn(
        'w-full rounded-md border border-admin-border bg-admin-bg px-3 py-2',
        'text-sm text-admin-text placeholder:text-admin-muted',
        'focus:outline-none focus:ring-1 focus:ring-admin-accent focus:border-admin-accent',
        'transition-colors',
        className,
      )}
      {...props}
    />
  )
}

export function Textarea({ className, ...props }) {
  return (
    <textarea
      className={cn(
        'w-full rounded-md border border-admin-border bg-admin-bg px-3 py-2',
        'text-sm text-admin-text placeholder:text-admin-muted resize-none',
        'focus:outline-none focus:ring-1 focus:ring-admin-accent focus:border-admin-accent',
        'transition-colors',
        className,
      )}
      {...props}
    />
  )
}
