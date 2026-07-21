// Shared link-safety helper. Used by markdownComponents.jsx's `a` override
// (rendering Markdown-produced links for both the chat UI and the Documents
// library) and by the library's DocumentDetailPage (rendering the "View
// original source" link built from a document's source_url). Only http(s)
// links are allowed through as real clickable anchors — anything else
// (javascript:, data:, mailto:, relative paths, malformed strings, etc.)
// must be rendered as inert plain text by the caller.
export function isSafeUrl(href) {
  if (typeof href !== 'string') return false
  return /^https?:\/\//i.test(href)
}
