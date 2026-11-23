"""The test copy (staging.pac-va.com, PAC_STAGING=1) never sends anything out, says on every page that it's the test
site, keeps out of search engines, and its data copy holds no secrets. The live site (no PAC_STAGING) is unchanged.
Run from the PAC folder: python tests/test_staging_mode.py"""
import json, os, shutil, sqlite3, subprocess, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if len(sys.argv) == 1:
    rc = 0
    for mode in ("live", "staging"):
        with tempfile.TemporaryDirectory(prefix=f"pac-{mode}-") as temp:
            data = Path(temp) / "data"; data.mkdir()
            shutil.copy2(ROOT / "data" / "runways.json", data / "runways.json")
            env = dict(os.environ, PAC_DATA_DIR=str(data))
            env.pop("PAC_STAGING", None)
            if mode == "staging":
                env["PAC_STAGING"] = "1"
            rc |= subprocess.run([sys.executable, __file__, mode], cwd=ROOT, env=env).returncode
    sys.exit(rc)
MODE = sys.argv[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))

failures = []
def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + f"[{MODE}] {name}" + ("" if cond else f" · {detail}"))
    if not cond: failures.append(name)

import urllib.request  # noqa: E402
sent = []
def no_network(*a, **k):
    sent.append(a[0] if a else k)
    raise OSError("network is off in this test")
urllib.request.urlopen = no_network
import smtplib  # noqa: E402
smtplib.SMTP = smtplib.SMTP_SSL = lambda *a, **k: sent.append(("smtp", a)) or (_ for _ in ()).throw(OSError("no smtp"))

import app as A, site_mode, discord_post, mailer, hoppie, sayintentions  # noqa: E402
DATA = Path(os.environ["PAC_DATA_DIR"])
(DATA / "hoppie_logon").write_text("SECRETLOGON")
client = A.app.test_client()

if MODE == "staging":
    check("staging is detected", site_mode.staging() and A.STAGING)
    hook = "https://discord.com/api/webhooks/123456789012345678/abcdefghijklmnopqrstuvwxyz"
    ok, err = discord_post.post(hook, {"content": "hello"}, wait=True)
    check("Discord posts are refused", ok is False and "test site" in (err or ""), (ok, err))
    discord_post.post(hook, {"content": "hello"})            # the background form must not start a send either
    st = {"smtp_host": "smtp.example.com", "smtp_port": 587, "smtp_user": "u", "smtp_pass": "p", "mail_from": "ops@pac-va.com"}
    ok, err = mailer.send(st, "pilot@example.com", "Hi", "text", wait=True)
    check("emails are refused", ok is False and "test site" in (err or ""), (ok, err))
    check("there is no Hoppie logon, so nothing polls PAC's real inbox", hoppie.logon(DATA) == "")
    check("Hoppie telexes are refused", "test site" in (hoppie.send("SECRETLOGON", "PAC123", "hi") or ""))
    ok, err = sayintentions._post("k", "va", {"x": 1})
    check("SayIntentions updates are refused", ok is False and "test site" in (err or ""))
    check("nothing reached the network", not sent, sent)
    check("the browser is told it's the test site", A.public_settings().get("staging") is True)
    robots = client.get("/robots.txt").get_data(as_text=True)
    check("robots.txt shuts search engines out", "Disallow: /\n" in robots and "Sitemap" not in robots, robots)
    page = client.get("/")
    html = page.get_data(as_text=True)
    check("pages carry the TEST SITE strip", "pac-test-banner" in html and "TEST SITE" in html)
    check("and [TEST] in the tab title", "<title>[TEST] " in html)
    check("and a noindex header", page.headers.get("X-Robots-Tag", "").startswith("noindex"))
    check("the strip is added once", html.count('id="pac-test-banner"') == 1)
    check("API answers are left alone", "pac-test-banner" not in client.get("/api/bootstrap").get_data(as_text=True))
else:
    check("the live site is not staging", not site_mode.staging() and not A.STAGING)
    check("the live site keeps its Hoppie logon", hoppie.logon(DATA) == "SECRETLOGON")
    check("the browser isn't told it's a test site", A.public_settings().get("staging") is False)
    check("robots.txt lets search engines in", "Allow: /" in client.get("/robots.txt").get_data(as_text=True))
    page = client.get("/")
    check("no TEST strip on the live site", "pac-test-banner" not in page.get_data(as_text=True) and "X-Robots-Tag" not in page.headers)
    ok, err = discord_post.post("https://discord.com/api/webhooks/123456789012345678/abcdefghijklmnopqrstuvwxyz", {"content": "x"}, wait=True)
    check("the live site still tries to post to Discord", ok is False and "test site" not in (err or "") and sent, (ok, err))

    # ------------------------------------------------ the data copy (run once, in the live pass)
    sys.path.insert(0, str(ROOT / "deploy"))
    import scrub_staging_data  # noqa: E402
    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        (d / "settings.json").write_text(json.dumps({"discord_webhook": "https://x", "smtp_pass": "pw", "si_va_key": "k", "si_enabled": True,
                                                     "discord_bot_token": "tok", "va_name": "Pagani Air Cargo"}))
        for f in ("bot_secret", "hoppie_logon", "secret_key"):
            (d / f).write_text("s")
        scrub_staging_data.scrub(d)
        st = json.loads((d / "settings.json").read_text())
        check("the copy keeps no webhook, password, key or token", not any(st.get(k) for k in ("discord_webhook", "smtp_pass", "si_va_key", "discord_bot_token")), st)
        check("the copy keeps ordinary settings", st.get("va_name") == "Pagani Air Cargo" and st.get("si_enabled") is False)
        check("the copy keeps no secret files", not any((d / f).exists() for f in ("bot_secret", "hoppie_logon", "secret_key")))

    if shutil.which("rsync") and os.name != "nt":
        with tempfile.TemporaryDirectory() as t:
            live, stage = Path(t) / "live", Path(t) / "pac-staging" / "data"
            live.mkdir()
            con = sqlite3.connect(live / "logbook.db"); con.execute("CREATE TABLE f (x)"); con.execute("INSERT INTO f VALUES (42)"); con.commit(); con.close()
            (live / "settings.json").write_text(json.dumps({"discord_webhook": "https://x"}))
            (live / "hoppie_logon").write_text("LOGON"); (live / "profile.json").write_text("{}")
            env = dict(os.environ, PAC_LIVE_DATA=str(live), PAC_STAGING_DATA=str(stage), PAC_STAGING_RESTART="0")
            p = subprocess.run(["bash", str(ROOT / "deploy" / "refresh_staging_data.sh")], env=env, capture_output=True, text=True)
            check("the refresh script runs", p.returncode == 0, p.stdout + p.stderr)
            rows = sqlite3.connect(stage / "logbook.db").execute("SELECT x FROM f").fetchall() if (stage / "logbook.db").exists() else []
            check("it copies the logbook", rows == [(42,)], rows)
            check("and the other files, without secrets", (stage / "profile.json").exists() and not (stage / "hoppie_logon").exists()
                  and not json.loads((stage / "settings.json").read_text()).get("discord_webhook"))
            bad = subprocess.run(["bash", str(ROOT / "deploy" / "refresh_staging_data.sh")], capture_output=True, text=True,
                                 env=dict(env, PAC_STAGING_DATA=str(live)))
            check("it refuses to write anywhere but a test-copy folder", bad.returncode != 0 and "Refusing" in bad.stdout)

    # ------------------------------------------------ deploy commands
    import deploy  # noqa: E402
    first, later = deploy.remote_staging_script(True), deploy.remote_staging_script(False)
    check("the first staging deploy runs the setup from the upload", "setup_staging.sh /home/pac/pac-staging.zip" in first)
    check("later staging deploys run the test copy's own updater", "/home/pac/pac-staging/current/deploy/update_staging.sh" in later)
    check("no staging command touches the live folder", "/home/pac/pac-acars/" not in first + later and "pac-discord" not in first + later)
    env_file = (ROOT / "deploy" / "staging.env").read_text()
    check("the staging updater points at the test copy's folder, port and service",
          "PAC_DEPLOY_ROOT=/home/pac/pac-staging" in env_file and ":5055/up" in env_file and "restart pac-staging" in env_file
          and 'PAC_SVC_DISCORD_RESTART=""' in env_file)
    svc = (ROOT / "deploy" / "pac-staging.service").read_text()
    check("the test copy's service sends nothing out and writes only its own data",
          "PAC_STAGING=1" in svc and "PAC_PORT=5055" in svc and "ReadWritePaths=/home/pac/pac-staging/shared/data" in svc)

print(f"\nSTAGING MODE TESTS ({MODE}) PASSED" if not failures else f"\n{len(failures)} FAILED: {failures}")
sys.exit(1 if failures else 0)
