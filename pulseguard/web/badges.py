"""Dynamic SVG badge generator for GitHub READMEs and dashboards."""

from typing import Optional


def generate_status_badge(
    label: str = "Status",
    status_text: str = "OPERATIONAL",
    is_up: bool = True,
    uptime_pct: Optional[float] = None,
) -> str:
    """Generates a crisp, monochromatic SVG status badge compatible with GitHub markdown."""
    if uptime_pct is not None:
        status_text = f"{uptime_pct:.2f}%"
        color_bg = "#22c55e" if uptime_pct >= 99.0 else ("#f59e0b" if uptime_pct >= 95.0 else "#ef4444")
    else:
        color_bg = "#22c55e" if is_up else "#ef4444"

    # Approximate text width calculation
    label_width = max(35, len(label) * 7 + 10)
    value_width = max(40, len(status_text) * 7 + 14)
    total_width = label_width + value_width

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{total_width}" height="20" role="img" aria-label="{label}: {status_text}">
  <title>{label}: {status_text}</title>
  <linearGradient id="s" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <clipPath id="r">
    <rect width="{total_width}" height="20" rx="3" fill="#fff"/>
  </clipPath>
  <g clip-path="url(#r)">
    <rect width="{label_width}" height="20" fill="#1e293b"/>
    <rect x="{label_width}" width="{value_width}" height="20" fill="{color_bg}"/>
    <rect width="{total_width}" height="20" fill="url(#s)"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" text-rendering="geometricPrecision" font-size="110">
    <text aria-hidden="true" x="{label_width * 5}" y="150" fill="#010101" fill-opacity=".3" transform="scale(.1)">{label}</text>
    <text x="{label_width * 5}" y="140" transform="scale(.1)" fill="#fff">{label}</text>
    <text aria-hidden="true" x="{(label_width + value_width / 2) * 10}" y="150" fill="#010101" fill-opacity=".3" transform="scale(.1)">{status_text}</text>
    <text x="{(label_width + value_width / 2) * 10}" y="140" transform="scale(.1)" fill="#fff">{status_text}</text>
  </g>
</svg>"""
    return svg
