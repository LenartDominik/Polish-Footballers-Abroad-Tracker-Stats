"""Email notifications using Resend."""

from app.core.config import settings


def send_sync_failed_email(error: str, details: dict) -> None:
    """Send email when sync fails.

    Args:
        error: Error message
        details: Dict with started_at, players_updated, etc.
    """
    if not settings.resend_api_key:
        print("Resend API key not configured, skipping email")
        return

    if not settings.admin_email:
        print("Admin email not configured, skipping email")
        return

    try:
        import resend

        resend.api_key = settings.resend_api_key

        resend.Emails.send({
            "from": "Polish Tracker <noreply@polishfootballers.com>",
            "to": settings.admin_email,
            "subject": "Sync FAILED - Polish Footballers Tracker",
            "html": f"""
                <h2 style="color: red;">Sync failed!</h2>
                <p><strong>Error:</strong> {error}</p>
                <table style="border-collapse: collapse; width: 100%;">
                    <tr><td style="padding: 8px; border: 1px solid #ddd;">Started at:</td>
                        <td style="padding: 8px; border: 1px solid #ddd;">{details.get('started_at', 'N/A')}</td></tr>
                    <tr><td style="padding: 8px; border: 1px solid #ddd;">Players updated:</td>
                        <td style="padding: 8px; border: 1px solid #ddd;">{details.get('players_updated', 0)}</td></tr>
                    <tr><td style="padding: 8px; border: 1px solid #ddd;">API calls:</td>
                        <td style="padding: 8px; border: 1px solid #ddd;">{details.get('api_calls_used', 1)}</td></tr>
                </table>
            """
        })
        print(f"Failure email sent to {settings.admin_email}")
    except Exception as e:
        print(f"Failed to send email: {e}")


def send_sync_success_email(details: dict) -> None:
    """Send email when sync succeeds (optional)."""
    if not settings.resend_api_key:
        print("Resend API key not configured, skipping email")
        return

    if not settings.admin_email:
        print("Admin email not configured, skipping email")
        return

    try:
        import resend

        resend.api_key = settings.resend_api_key

        resend.Emails.send({
            "from": "Polish Tracker <noreply@polishfootballers.com>",
            "to": settings.admin_email,
            "subject": f"Sync completed - {details.get('players_updated', 0)} players updated",
            "html": f"""
                <h2 style="color: green;">Sync completed!</h2>
                <table style="border-collapse: collapse; width: 100%;">
                    <tr><td style="padding: 8px; border: 1px solid #ddd;">Players updated:</td>
                        <td style="padding: 8px; border: 1px solid #ddd;">{details.get('players_updated', 0)}</td></tr>
                    <tr><td style="padding: 8px; border: 1px solid #ddd;">API calls:</td>
                        <td style="padding: 8px; border: 1px solid #ddd;">{details.get('api_calls_used', 1)}</td></tr>
                    <tr><td style="padding: 8px; border: 1px solid #ddd;">Duration:</td>
                        <td style="padding: 8px; border: 1px solid #ddd;">{details.get('duration_seconds', 0)}s</td></tr>
                </table>
            """
        })
        print(f"Success email sent to {settings.admin_email}")
    except Exception as e:
        print(f"Failed to send email: {e}")
