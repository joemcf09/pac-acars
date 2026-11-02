# Putting PAC online at pac-va.com

About an hour, start to finish. You'll need the domain (bought) and a card for the server (around $5 a month).
Everything below is copy-and-paste; where you see `pac-va.com`, it's already your domain.

---

## 1. Rent a server

Any small Linux server will do. PAC is light: 1 shared CPU and 1 GB of memory is plenty for a virtual airline.

| Host | Plan | About |
|---|---|---|
| **Hetzner** | CX22 | €4/month, excellent value, German or US locations |
| **DigitalOcean** | Basic droplet | $6/month, very easy, lots of guides |
| **Vultr** | Regular | $5/month, many locations |

When creating it:
* **Image:** Ubuntu 24.04 LTS
* **Location:** near you and your pilots (for you, a US east-coast location)
* **Authentication:** SSH key if you have one, otherwise a password is fine to start
* Note the server's **IP address**, for example `203.0.113.45`

---

## 2. Point the domain at it

In Cloudflare, open **pac-va.com → DNS → Add record**, twice:

| Type | Name | Content | Proxy |
|---|---|---|---|
| A | `@` | your server's IP | **DNS only** (grey cloud) |
| A | `www` | your server's IP | **DNS only** (grey cloud) |

Grey cloud matters at first: Caddy needs to reach your server directly to get its certificate. You can switch the
orange cloud on later if you want Cloudflare's protection.

Check it worked (wait a minute or two):

```bash
ping pac-va.com
```

---

## 3. Set the server up

Connect to it:

```bash
ssh root@pac-va.com
```

Then, as a block:

```bash
# keep the system current and install what PAC needs
apt update && apt -y upgrade
apt -y install python3-venv python3-pip git unzip sqlite3 rsync ufw

# a user for PAC, so it never runs as root
adduser --disabled-password --gecos "" pac

# only let in SSH and the web
ufw allow OpenSSH && ufw allow 80 && ufw allow 443 && ufw --force enable

# Caddy: the web server that gets and renews the HTTPS certificate automatically
apt -y install debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
apt update && apt -y install caddy
```

---

## 4. Install PAC

On **your PC**, send PAC up to the server (from the folder containing `pac-acars.zip`):

```bash
scp pac-acars.zip root@pac-va.com:/home/pac/
```

Back on the **server**:

```bash
cd /home/pac
unzip -q pac-acars.zip && rm pac-acars.zip
chown -R pac:pac /home/pac

# install PAC's Python packages into its own folder
sudo -u pac bash -c 'cd /home/pac/pac-acars && python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt'
```

### Bring your airline with you (optional but recommended)

If you've been flying on your PC, take your logbook with you. On your PC: **Staff › Site and rules › Download a
full backup**, then:

```bash
scp pac-backup-*.zip root@pac-va.com:/home/pac/
```

Start PAC (next step), open the site, sign in as founder, then **Staff › Site and rules › Restore from a backup**.

---

## 5. Start PAC as a service

```bash
cp /home/pac/pac-acars/deploy/pac.service /etc/systemd/system/pac.service
systemctl daemon-reload
systemctl enable --now pac
systemctl status pac --no-pager      # should say "active (running)"
```

PAC now starts at boot and restarts by itself if it ever stops.

---

## 6. Turn on HTTPS

```bash
cp /home/pac/pac-acars/deploy/Caddyfile /etc/caddy/Caddyfile
systemctl reload caddy
```

Caddy fetches a certificate from Let's Encrypt within a few seconds and renews it forever, free.

**Open https://pac-va.com in your browser.** You should see PAC with a padlock.

---

## 7. Finish the setup inside PAC

Sign in as founder, then:

1. **Staff › Site and rules › Letters and links**
   * **Website address pilots use:** `https://pac-va.com`
     *This is important: sign-in links in welcome letters use it. Until you set it, they'll say `localhost`.*
   * **Discord invite:** your invite link
2. **Staff › Site and rules › Email** — your PAC mailbox and app password (see below for a better option now that
   you have a domain)
3. **Staff › Site and rules** — switch **Reuse pilot IDs** off before real pilots join

### PAC ACARS for your pilots

Each pilot's app needs to point at the server. In PAC ACARS: **Settings › PAC website** → `https://pac-va.com`,
then sign in. Their own API key is created automatically.

---

## 8. Nightly backups

```bash
cp /home/pac/pac-acars/deploy/backup.sh /etc/cron.daily/pac-backup
chmod +x /etc/cron.daily/pac-backup
/etc/cron.daily/pac-backup          # run it once now to check
```

That keeps 30 days of backups on the server. **A server can die, so keep a copy somewhere else too:**

```bash
apt -y install rclone
rclone config          # add your Google Drive, Dropbox or Backblaze; call the remote "pacbackup"
nano /etc/cron.daily/pac-backup     # uncomment the rclone line at the bottom
```

---

## 9. Email from your own domain (recommended)

Now that you own pac-va.com, letters can come from `ops@pac-va.com` instead of a Gmail address, which stops them
landing in junk folders. Use a sending service with a free tier:

* **Resend** (3,000 a month free), **Brevo** (300 a day), or **Mailgun**

Sign up, add `pac-va.com`, and they'll give you two or three **DNS records** (SPF, DKIM, DMARC) to add in
Cloudflare, exactly as you added the A records. Then in PAC's **Email** settings use the SMTP details they show,
with `ops@pac-va.com` as the address. Letters will then be properly authenticated and land in the inbox.

**DigitalOcean blocks ports 465 and 587** on new accounts, so on the server use Resend's spare port: server
`smtp.resend.com`, port **2465**, security **SSL**, sign-in name `resend`, and your Resend API key as the password.
**Check the connection** finds a working port by itself and offers to switch to it. Receiving mail at `ops@pac-va.com`
works through Cloudflare's free **Email Routing**, which forwards it to the PAC Gmail inbox.

---

## 10. The PAC Discord bot

PAC Operations is PAC's own Discord bot. It runs on the same server as its own service.

1. **Create the bot** at discord.com/developers/applications: New Application (`PAC Operations`, PAC logo), then
   **Bot › Reset Token** (copy it; it's a password) and switch on **Server Members Intent**.
2. **Invite it**: OAuth2 › URL Generator, tick **bot** and **applications.commands**, and the permissions **Manage
   Roles**, **Send Messages**, **Embed Links** and **View Channels**. Open the link and add it to the PAC server. In
   Server Settings › Roles, drag the bot's role above the PAC rank roles.
3. **Install the service** (once), from PowerShell on your PC:

   ```
   ssh root@pac-va.com "cp /home/pac/pac-acars/deploy/pac-discord.service /etc/systemd/system/ && systemctl daemon-reload && systemctl enable --now pac-discord"
   ```

4. **Switch it on** in **Staff › Site and rules › Discord bot**: paste the token, check the channel and role names,
   tick **Run the PAC Discord bot** and save. Within a minute the section shows 🟢 Online.

Pilots link their account in **Settings › Link my Discord account**, which gives them a code for `/link` in Discord.
`update.sh` restarts the bot with each update. Its log: `journalctl -u pac-discord -n 50`.

## Everyday commands

```bash
systemctl status pac          # is PAC running?
journalctl -u pac -n 100      # the last 100 lines of PAC's log
systemctl restart pac         # restart it
/etc/cron.daily/pac-backup    # back up right now
```

**Updating PAC** when I send you a new zip:

```bash
scp pac-acars.zip pac@pac-va.com:~/            # from your PC
ssh pac@pac-va.com '~/pac-acars/deploy/update.sh ~/pac-acars.zip'
```

That backs up first, replaces the program files only (your data is untouched), installs anything new and restarts.

---

## If something goes wrong

| What you see | What to do |
|---|---|
| "This site can't be reached" | `systemctl status pac` and `systemctl status caddy` on the server |
| Certificate warning | Check the DNS records are grey-cloud, then `journalctl -u caddy -n 50` |
| PAC won't start after an update | `journalctl -u pac -n 50` shows the error; restore with the backup it took |
| Sign-in links say localhost | Set the website address in Staff › Site and rules › Letters and links |
| Pilots can't connect the ACARS app | They need `https://pac-va.com` in the app's Settings, and to sign in again |

---

## What this costs

| | |
|---|---|
| Domain | about $10 a year |
| Server | $5 to $6 a month |
| HTTPS certificate | free, forever |
| Email sending | free at the volumes a VA needs |
