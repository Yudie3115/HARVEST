import { cn } from '../../lib/utils'

export function Select({ className, children, ...props }) {
  return (
    <select
      className={cn(
        'w-full rounded-md border border-admin-border bg-admin-bg px-3 py-2',
        'text-sm text-admin-text',
        'focus:outline-none focus:ring-1 focus:ring-admin-accent focus:border-admin-accent',
        'appearance-none cursor-pointer transition-colors',
        'bg-[url("data:image/svg+xml,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' width=\'10\' height=\'6\'%3E%3Cpath d=\'M0 0l5 6 5-6z\' fill=\'%2371717a\'/%3E%3C/svg%3E")]',
        'bg-no-repeat bg-[right_10px_center] pr-8',
        className,
      )}
      {...props}
    >
      {children}
    </select>
  )
}
