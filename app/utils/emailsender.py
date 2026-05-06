import os
import requests
from dotenv import load_dotenv

load_dotenv()

def send_otp_email(receiver_email: str, otp: str):
    resend_api_key = os.getenv("RESEND_API_KEY")
    
    # Fallback to mock if no API key is provided
    if not resend_api_key:
        print(f"Mock sending OTP {otp} to {receiver_email}")
        return True

    # Note: On a free Resend tier without a verified domain, 
    # you MUST use 'onboarding@resend.dev' as the from email.
    sender_email = os.getenv("EMAIL_SENDER", "onboarding@resend.dev")

    html = f"""\
    <!DOCTYPE html>
    <html>
      <head>
        <meta charset="utf-8">
      </head>
      <body style="margin: 0; padding: 0; background-color: #F8FAFC; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
        <table width="100%" border="0" cellspacing="0" cellpadding="0" style="padding: 40px 20px;">
          <tr>
            <td align="center">
              <table width="100%" max-width="500px" border="0" cellspacing="0" cellpadding="0" style="background-color: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 16px; overflow: hidden; max-width: 500px; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.05);">
                <tr>
                  <td style="padding: 40px 40px 20px 40px; text-align: center;">
                    <div style="width: 40px; height: 40px; border: 1px solid #E5E7EB; border-radius: 10px; margin: 0 auto 24px auto; line-height: 40px; text-align: center; color: #111111; font-weight: bold; background-color: #FFFFFF;">
                      +
                    </div>
                    <h2 style="margin: 0 0 8px 0; color: #111111; font-size: 24px; font-weight: 700; letter-spacing: -0.5px;">Secure Verification</h2>
                    <p style="margin: 0; color: #6B7280; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 2px;">Clinical Access Portal</p>
                  </td>
                </tr>
                <tr>
                  <td style="padding: 20px 40px;">
                    <p style="margin: 0 0 24px 0; color: #374151; font-size: 15px; line-height: 24px; text-align: center;">
                      You are attempting to access a secure clinical environment. Please use the verification code below to authenticate your identity.
                    </p>
                    <div style="background-color: #F9FAFB; border: 1px solid #E5E7EB; border-radius: 12px; padding: 24px; text-align: center; margin-bottom: 24px;">
                      <div style="font-family: monospace; font-size: 32px; font-weight: 700; color: #111111; letter-spacing: 8px;">
                        {otp}
                      </div>
                    </div>
                    <p style="margin: 0; color: #6B7280; font-size: 13px; text-align: center;">
                      This code is valid for <strong>5 minutes</strong>. If you did not request this, please ignore this email.
                    </p>
                  </td>
                </tr>
                <tr>
                  <td style="padding: 30px 40px; background-color: #F9FAFB; border-top: 1px solid #E5E7EB; text-align: center;">
                    <p style="margin: 0; color: #9CA3AF; font-size: 11px;">
                      &copy; 2026 Arrhythmia Detection System. All rights reserved.
                    </p>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
        </table>
      </body>
    </html>
    """
    
    headers = {
        "Authorization": f"Bearer {resend_api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "from": sender_email,
        "to": [receiver_email],
        "subject": "Your Verification Code",
        "html": html
    }

    try:
        response = requests.post("https://api.resend.com/emails", json=payload, headers=headers)
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        print(f"Error sending email via Resend: {e}")
        print(f"Response: {e.response.text if hasattr(e, 'response') and e.response else 'No response body'}")
        return False
