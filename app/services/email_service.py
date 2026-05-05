import os
import logging

# Setup logging to simulate email sending
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def send_otp_email(email: str, otp: str):
    """
    Simulates sending an OTP email. 
    In production, replace this with SMTP, SendGrid, or AWS SES.
    """
    subject = "HeartSync Security: Your Verification Code"
    body = f"""
    Hello,

    Your clinical portal verification code is: {otp}
    This code will expire in 10 minutes.

    If you did not request this, please secure your account immediately.

    Regards,
    HeartSync Security Team
    """
    
    # FOR DEMONSTRATION: We log it to the console.
    # In a real app, you'd use a mailer library here.
    logger.info(f"--- SIMULATED EMAIL TO {email} ---")
    logger.info(f"Subject: {subject}")
    logger.info(f"Body: {body}")
    logger.info("----------------------------------")
    
    return True
