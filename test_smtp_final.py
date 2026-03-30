import smtplib
import ssl
import os
from dotenv import load_dotenv

# Load .env variables
load_dotenv()

def test_smtp_connection():
    print("🚀 --- FaceAuth SMTP Diagnostic Tool ---")
    
    host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    port = int(os.getenv("SMTP_PORT", 587))
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASSWORD")
    sender = os.getenv("SMTP_FROM", user)

    print(f"📡 Connecting to: {host}:{port}")
    print(f"📧 Authenticating as: {user}")
    
    if not password:
        print("❌ ERROR: SMTP_PASSWORD is empty in .env!")
        return

    try:
        context = ssl.create_default_context()
        
        # Test Port 465 (Direct SSL) vs 587 (STARTTLS)
        if port == 465:
            print("🔒 Using SSL (Port 465)...")
            server = smtplib.SMTP_SSL(host, port, context=context, timeout=10)
        else:
            print("🔓 Using STARTTLS (Port 587)...")
            server = smtplib.SMTP(host, port, timeout=10)
            server.set_debuglevel(1) # Show every step of the conversation
            server.starttls(context=context)
            
        print("🔑 Attempting Login...")
        server.login(user, password)
        print("✅ SUCCESS: Login verified!")
        
        # Try sending a test message
        print(f"📤 Sending test email to {user}...")
        message = f"Subject: FaceAuth SMTP Test\n\nSMTP Connection is PERFECT. Everything is READY."
        server.sendmail(sender, [user], message)
        print("✅ SUCCESS: Test email dispatched!")
        
        server.quit()
        print("\n🎉 DIAGNOSTIC COMPLETE: Your email system is working perfectly.")
        
    except smtplib.SMTPAuthenticationError:
        print("\n❌ AUTHENTICATION FAILED: Incorrect email or App Password.")
        print("👉 Note: If you have 2FA on Gmail, you MUST use an 'App Password' from: https://myaccount.google.com/apppasswords")
    except Exception as e:
        print(f"\n❌ CONNECTION ERROR: {type(e).__name__} - {e}")
        print("👉 Suggestion: Check if your ISP or Firewall is blocking port 587.")

if __name__ == "__main__":
    test_smtp_connection()
