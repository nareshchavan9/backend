def send_otp_email(receiver_email: str, otp: str):
    """
    Mock email sender to avoid external API dependencies.
    The OTP is simply printed to the server logs.
    """
    print(f"=========================================")
    print(f"MOCK EMAIL DISPATCH")
    print(f"To: {receiver_email}")
    print(f"Subject: Your Verification Code")
    print(f"Code: {otp}")
    print(f"=========================================")
    return True
