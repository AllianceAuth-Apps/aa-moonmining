from django.utils.html import format_html


def bootstrap5_label_html(text: str, label: str = "default") -> str:
    """Return HTML for a Bootstrap 5 label."""
    return format_html('<span class="badge text-bg-{}">{}</span>', label, text)
