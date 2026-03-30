import smtplib
import logging
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone
from backend.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

def send_security_alert(username: str, email: str, ip_address: str, user_agent: str, method: str, success: bool = True, failure_reason: str = None, alert_type: str = "login"):
    """
    Sends a specialized security alert email to the user.
    Types: registration, biometric_face, biometric_voice, biometric_dual, secure_password, failure, 2fa_totp
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    
    # Default variables
    status_color = "#00d2ff" if success else "#ff4b2b"
    icon = "🔐" if success else "⚠️"
    title = "Successful Login" if success else "Failed Login Attempt"
    description = "A new successful login was detected for your account." if success else "A failed login attempt was detected for your account."
    
    # Specialized Logic for "Perfect" Experience
    if alert_type == "registration":
        title = "Identity Vault Created"
        description = "Welcome to FaceAuth. Your zero-trust biometric profile is now active and guarded."
        icon = "✨"
    elif alert_type == "biometric_face":
        title = "Face Identity Verified"
        description = "Access granted via Neural Face Recognition. Your unique facial architecture was matched successfully."
        icon = "👤"
    elif alert_type == "biometric_voice":
        title = "Voice Identity Verified"
        description = "Access granted via Voice Biometrics. Your vocal frequency and syntax were matched successfully."
        icon = "🎙️"
    elif alert_type == "biometric_dual":
        title = "Multi-Modal Fusion Clearance"
        description = "Elite Security Clearance: Your identity was cross-verified using both Face and Voice modalities."
        icon = "🛡️"
    elif alert_type == "secure_password":
        title = "Secure Credentials Access"
        description = "Login successful via primary encrypted credentials. Our system continues to monitor your activity."
        icon = "🔑"
    elif alert_type == "2fa_totp":
        title = "2FA Security Check"
        description = "A high-security 2FA verification was successfully processed for this session."
        icon = "🔢"

    if not success and failure_reason:
        description = f"Security Violation: {failure_reason}. If this wasn't you, our neural enclave suggests immediate action."
        title = "Security Alert: Unauthorized Access Attempt"
        icon = "🛑"

    # Enhanced HTML Template
    html_content = f"""
    <html>
    <body style="font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #050510; color: #ffffff; padding: 40px; margin: 0;">
        <div style="max-width: 600px; margin: 0 auto; background: linear-gradient(145deg, rgba(255,255,255,0.05) 0%, rgba(255,255,255,0.01) 100%); border: 1px solid rgba(255,255,255,0.1); border-radius: 24px; padding: 40px; backdrop-filter: blur(20px); box-shadow: 0 20px 40px rgba(0,0,0,0.6);">
            <div style="text-align: center; margin-bottom: 32px;">
                <div style="font-size: 56px; margin-bottom: 20px;">{icon}</div>
                <h1 style="color: {status_color}; margin: 0; font-size: 26px; text-transform: uppercase; letter-spacing: 3px; font-weight: 800;">{title}</h1>
                <p style="color: #6d6d7a; margin-top: 10px; font-size: 13px; text-transform: uppercase; letter-spacing: 1px;">Universal Identity Protection</p>
            </div>
            
            <p style="font-size: 16px; color: #a0a0ab; line-height: 1.7; text-align: center;">Hello <strong>{username}</strong>,</p>
            <p style="font-size: 17px; color: #ffffff; line-height: 1.7; text-align: center; font-weight: 300;">{description}</p>
            
            <div style="background: rgba(0,0,0,0.5); border-radius: 20px; padding: 28px; margin: 32px 0; border: 1px solid rgba(255,255,255,0.05); box-shadow: inset 0 0 20px rgba(0,210,255,0.05);">
                <table style="width: 100%; color: #ffffff; font-size: 14px; border-collapse: collapse;">
                    <tr>
                        <td style="color: #6d6d7a; padding: 10px 0; border-bottom: 1px solid rgba(255,255,255,0.05);">Auth Protocol:</td>
                        <td style="padding: 10px 0; border-bottom: 1px solid rgba(255,255,255,0.05); text-align: right; text-transform: uppercase; font-weight: bold; color: {status_color};">{method}</td>
                    </tr>
                    <tr>
                        <td style="color: #6d6d7a; padding: 10px 0; border-bottom: 1px solid rgba(255,255,255,0.05);">Network Node (IP):</td>
                        <td style="padding: 10px 0; border-bottom: 1px solid rgba(255,255,255,0.05); text-align: right;">{ip_address}</td>
                    </tr>
                    <tr>
                        <td style="color: #6d6d7a; padding: 10px 0;">Security Timestamp:</td>
                        <td style="padding: 10px 0; text-align: right;">{now}</td>
                    </tr>
                </table>
            </div>
            
            <div style="text-align: center; margin-top: 40px; padding-top: 30px; border-top: 1px solid rgba(255,255,255,0.05);">
                <p style="font-size: 12px; color: #5d5d6a; line-height: 1.6;">
                    Verified against your AES-256-GCM encrypted neural enclave. This identity session is secured with unique hardware-level tokens.
                </p>
                <div style="margin-top: 28px;">
                    <a href="#" style="background: linear-gradient(90deg, {status_color} 0%, #0072ff 100%); color: #ffffff; text-decoration: none; padding: 14px 40px; border-radius: 14px; font-weight: bold; font-size: 15px; display: inline-block; box-shadow: 0 10px 20px rgba(0,210,255,0.2);">Secure Vault Dashboard</a>
                </div>
                <p style="font-size: 11px; color: #404050; margin-top: 45px; letter-spacing: 0.5px;">&copy; 2026 FaceAuth Biometric Alliance. Elite Identity Standards.</p>
            </div>
        </div>
    </body>
    </html>
    """

    if settings.email_backend == "console":
        logger.info(f"\n{'#'*30} {title.upper()} {'#'*30}")
        logger.info(f"TO: {email} | METHOD: {method}")
        logger.info(f"DESC: {description}")
        logger.info(f"{'#'*70}\n")
        return

    # SMTP Production Logic
    if not settings.smtp_user or not settings.smtp_password:
        return

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"FaceAuth [URGENT]: {title}"
        msg["From"] = settings.smtp_from or settings.smtp_user
        msg["To"] = email
        msg.attach(MIMEText(html_content, "html"))

        context = ssl.create_default_context()
        if int(settings.smtp_port) == 465:
            with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, context=context) as server:
                server.login(settings.smtp_user, settings.smtp_password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
                server.starttls(context=context)
                server.login(settings.smtp_user, settings.smtp_password)
                server.send_message(msg)
            
        logger.info(f"✅ Secure {alert_type} email dispatch successful -> {email}")
    except Exception as e:
        logger.error(f"❌ Security Dispatch Failed: {e}")
