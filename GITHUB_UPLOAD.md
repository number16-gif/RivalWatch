# GitHub and local development

This project is published at **https://github.com/number16-gif/RivalWatch**.

## Download and run

Use **Code → Download ZIP** on GitHub, extract it, then follow [README.md](README.md). On Windows 11, run `install.bat`, then `start_web.bat` and `start_worker.bat` in separate windows.

## Contribute changes via Git

```bash
git clone https://github.com/number16-gif/RivalWatch.git
cd RivalWatch
git checkout -b feature/my-improvement
# edit files and run tests
git add .
git commit -m "Explain the change"
git push -u origin feature/my-improvement
```

You can then open a pull request in GitHub.

## Before each push

- Confirm that no secrets or tokens are in the commit.
- Exclude `.env`, `.flask_secret`, `*.db`, `*.log`, `.venv/`, and local `demo.html`.
- Run `python -m unittest discover -s tests -v`.
- Check the **Actions** tab for the result.
- Keep changes small and README instructions accurate.

This is a local educational project, **not** a production-hosted SaaS. For public deployment it would need isolation, network-level SSRF protection, more testing, and a hardened server.
