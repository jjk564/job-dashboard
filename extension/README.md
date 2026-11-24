# JobPulse Native Chrome Extension (Zero-CAPTCHA Friction)

When an ATS application page uses Cloudflare Turnstile, reCAPTCHA, or hCaptcha, automated browser engines like Playwright can cause CAPTCHA widgets to loop even when you click them manually.

Loading this lightweight local extension in your **regular Chrome or Edge browser** gives you:
- **100% native browser CAPTCHA verification** (zero Playwright, zero CDP automation flags)
- **Automatic form filling** powered by your local JobPulse backend (`http://127.0.0.1:8000`)
- **Automatic Resume & Cover Letter PDF attachment**
- **Instant Bot Trap Warning Banners** right above the form
- **1-click Speed-Run queue progression** (`✓ Mark Applied & Next`)

## 30-Second Setup (One-Time)
1. Open Chrome and navigate to `chrome://extensions` (or `edge://extensions` in Edge).
2. Enable **Developer mode** (toggle in the top-right corner).
3. Click **Load unpacked** and select this `extension` folder:
   `Job Dashboard/extension`
4. Keep JobPulse running (`start.bat`), and click **Regular Chrome** / **Speed-Run (Chrome)** in JobPulse!
