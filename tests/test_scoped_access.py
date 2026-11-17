"""Scoped staff access (company.SCOPE): the path->capability mapping, default-deny for everything
unmapped, and may_path for a scoped role-holder vs a plain pilot. This is the security core of the
roles access engine: a scoped role must reach ONLY its own section and never the sensitive feeds."""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import company

con = sqlite3.connect(":memory:")
con.execute("CREATE TABLE pilots (id TEXT PRIMARY KEY, name TEXT, staff INT)")
for pid, name, staff in [("PAC0001", "Joseph", 1), ("PAC0014", "Alan", 0), ("PAC0002", "Jose", 0), ("PAC0003", "Mara", 0), ("PAC0004", "Devi", 0)]:
    con.execute("INSERT INTO pilots VALUES (?,?,?)", (pid, name, staff))
company.migrate(con)                       # seeds the owner's ceo role
company.assign(con, "PAC0014", "livery_mgr", "")   # Alan: Livery Manager, not a full admin
company.assign(con, "PAC0003", "creative", "")     # Mara: Creative / Media Director, not a full admin
company.assign(con, "PAC0004", "commercial", "")   # Devi: Commercial Director, not a full admin
con.commit()

fails = []
def check(name, ok, got=None):
    print(("PASS" if ok else "FAIL") + ": " + name + ("" if ok else f"  [{got!r}]"))
    if not ok:
        fails.append(name)

# --- path -> capability ------------------------------------------------------
check("liveries path is scoped", company.capability_for("/api/staff/liveries") == "liveries")
check("liveries sub-path is scoped", company.capability_for("/api/staff/liveries/ab12cd") == "liveries")
check("no false prefix match (liveriesX)", company.capability_for("/api/staff/liveriesX") is None,
      company.capability_for("/api/staff/liveriesX"))

# default-deny: every sensitive endpoint must be unmapped (full-admin only)
SENSITIVE = ["/api/staff/overview", "/api/staff/roster", "/api/staff/roster/PAC0002",
             "/api/staff/wallet/PAC0002", "/api/staff/pilots/PAC0002", "/api/staff/ceo",
             "/api/staff/ceo/letter", "/api/staff/backup/download", "/api/staff/backups",
             "/api/staff/mail", "/api/staff/discord", "/api/staff/hoppie", "/api/staff/roles",
             "/api/staff/site", "/api/staff/market", "/api/staff/statements"]
for p in SENSITIVE:
    check("default-deny (unmapped): " + p, company.capability_for(p) is None, company.capability_for(p))

# a non-staff path is never a capability path
check("non-staff path -> None", company.capability_for("/api/pilot/me") is None)

# --- caps_of -----------------------------------------------------------------
check("Alan's caps = [liveries]", company.caps_of(con, "PAC0014") == ["liveries"], company.caps_of(con, "PAC0014"))
check("plain pilot has no caps", company.caps_of(con, "PAC0002") == [], company.caps_of(con, "PAC0002"))
check("owner/ceo has no scoped caps (full admin instead)", company.caps_of(con, "PAC0001") == [],
      company.caps_of(con, "PAC0001"))

# --- may_path: the gate's decision for a non-admin -------------------------
check("Alan MAY /api/staff/liveries", company.may_path(con, "PAC0014", "/api/staff/liveries") is True)
check("Alan MAY /api/staff/liveries/<id>", company.may_path(con, "PAC0014", "/api/staff/liveries/x9") is True)
check("Alan may NOT /api/staff/overview", company.may_path(con, "PAC0014", "/api/staff/overview") is False)
check("Alan may NOT /api/staff/roster", company.may_path(con, "PAC0014", "/api/staff/roster") is False)
check("Alan may NOT /api/staff/wallet/<pid>", company.may_path(con, "PAC0014", "/api/staff/wallet/PAC0002") is False)
check("Alan may NOT /api/staff/pilots/<pid>", company.may_path(con, "PAC0014", "/api/staff/pilots/PAC0002") is False)
check("Alan may NOT /api/staff/roles", company.may_path(con, "PAC0014", "/api/staff/roles") is False)
check("plain pilot may NOT /api/staff/liveries", company.may_path(con, "PAC0002", "/api/staff/liveries") is False)

# --- Creative / Media: a second scoped role, kept separate from Livery -------
check("partner-photos path is scoped to creative", company.capability_for("/api/staff/partner-photos") == "creative")
check("partner-photos sub-path (browse) scoped", company.capability_for("/api/staff/partner-photos/FX/B77F/browse") == "creative")
check("news path is scoped to creative", company.capability_for("/api/staff/news") == "creative")
check("news sub-path (delete one) scoped", company.capability_for("/api/staff/news/42") == "creative")
check("Mara's caps = [creative]", company.caps_of(con, "PAC0003") == ["creative"], company.caps_of(con, "PAC0003"))
check("Mara MAY /api/staff/partner-photos", company.may_path(con, "PAC0003", "/api/staff/partner-photos") is True)
check("Mara MAY partner-photos sub-path", company.may_path(con, "PAC0003", "/api/staff/partner-photos/FX/B77F") is True)
check("Mara MAY /api/staff/news (announcements/NOTAMs)", company.may_path(con, "PAC0003", "/api/staff/news") is True)
check("Mara MAY /api/staff/news/<id>", company.may_path(con, "PAC0003", "/api/staff/news/7") is True)
check("Alan (livery) may NOT /api/staff/news", company.may_path(con, "PAC0014", "/api/staff/news") is False)
check("Mara may NOT /api/staff/liveries (other role's section)", company.may_path(con, "PAC0003", "/api/staff/liveries") is False)
check("Mara may NOT /api/staff/overview", company.may_path(con, "PAC0003", "/api/staff/overview") is False)
check("Alan (livery) may NOT /api/staff/partner-photos", company.may_path(con, "PAC0014", "/api/staff/partner-photos") is False)

# --- Commercial: complaints (with shipper standing) --------------------------
check("complaints path is scoped to commercial", company.capability_for("/api/staff/complaints") == "commercial")
check("complaints answer sub-path scoped", company.capability_for("/api/staff/complaints/12") == "commercial")
check("Devi's caps = [commercial]", company.caps_of(con, "PAC0004") == ["commercial"], company.caps_of(con, "PAC0004"))
check("Devi MAY /api/staff/complaints", company.may_path(con, "PAC0004", "/api/staff/complaints") is True)
check("Devi MAY /api/staff/complaints/<id>", company.may_path(con, "PAC0004", "/api/staff/complaints/9") is True)
check("Devi may NOT /api/staff/market (fleet money, unmapped)", company.may_path(con, "PAC0004", "/api/staff/market") is False)
check("Devi may NOT /api/staff/overview", company.may_path(con, "PAC0004", "/api/staff/overview") is False)
check("Mara (creative) may NOT /api/staff/complaints", company.may_path(con, "PAC0003", "/api/staff/complaints") is False)

print("\n" + ("ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}"))
sys.exit(1 if fails else 0)
