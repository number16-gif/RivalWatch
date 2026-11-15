# Security notes

RivalWatch is an educational application intended to run **locally only**.

- Never expose the Flask development server to the internet.
- Do not commit `.env`, `.flask_secret`, local databases, or logs.
- The project's URL validation and `robots.txt` handling are best-effort safeguards, not a substitute for egress isolation, SSRF/DNS rebinding protection, rate limiting, and security review.
- Only monitor publicly accessible pages where automated access is permitted.
- No authentication bypass, CAPTCHA bypass, or website-protection evasion is part of this project.

If you find an issue, avoid sharing secrets or personal data in public bug reports.
