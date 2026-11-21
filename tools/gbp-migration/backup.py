"""Read-only snapshot, encrypted by Windows DPAPI for the current Windows user.

Scope: public application tables, Auth admin records and storage bucket metadata.
This is not a physical database backup or a backup of storage object bytes.
No credentials are printed. Restore must be deliberate; never replay pending jobs.
"""
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import zlib

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]
TABLES = """workspaces workspace_members social_connections social_accounts social_permissions
media_assets content_drafts content_draft_media content_targets publishing_jobs usage_counters
deletion_requests audit_events oauth_states automation_rules automation_events automation_contacts
automation_deliveries scheduler_leases scheduler_configuration business_chatbots chatbot_contacts
chatbot_runs pilot_access_grants pilot_access_attempts whatsapp_connections whatsapp_messages
whatsapp_events whatsapp_contacts whatsapp_rules whatsapp_templates whatsapp_campaigns
whatsapp_signup_sessions whatsapp_ai_runs""".split()


class Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def protect(data, decrypt=False):
    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    result = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    if decrypt:
        ok = crypt.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(result))
    else:
        ok = crypt.CryptProtectData(ctypes.byref(source), "Growboard pre-Google snapshot", None, None, None, 1, ctypes.byref(result))
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(result.pbData)


def main():
    values = {}
    for name in [".env", ".env.local"]:
        path = ROOT/"business-growth-platform-backend"/name
        if path.exists():
            values.update(dotenv_values(path))
    url = str(values.get("SUPABASE_URL", "")).rstrip("/")
    if url != "https://vcbpmtfarhhdjrnuwlts.supabase.co":
        raise RuntimeError("Expected Growboard project configuration is unavailable; no backup attempted")
    key = values.get("SUPABASE_SERVICE_ROLE_KEY")
    if not key:
        raise RuntimeError("Service configuration is unavailable")
    snapshot = {"project": "vcbpmtfarhhdjrnuwlts", "created_at": datetime.now(timezone.utc).isoformat(),
                "scope": "public tables, auth admin records, storage bucket metadata; excludes object bytes", "tables": {}}
    with httpx.Client(timeout=30, headers={"apikey":key,"Authorization":"Bearer "+key}) as http:
        for table in TABLES:
            rows=[]
            for offset in range(0,100000,1000):
                response=http.get(f"{url}/rest/v1/{table}",params={"select":"*","limit":1000,"offset":offset})
                response.raise_for_status()
                batch=response.json();rows.extend(batch)
                if len(batch)<1000:
                    break
            else:
                raise RuntimeError("Snapshot row cap exceeded; no complete snapshot produced")
            snapshot["tables"][table]=rows
        users=[]
        for page in range(1,101):
            response=http.get(url+"/auth/v1/admin/users",params={"page":page,"per_page":100})
            response.raise_for_status();batch=response.json().get("users",[]);users.extend(batch)
            if len(batch)<100:break
        snapshot["auth_users"]=users
        response=http.get(url+"/storage/v1/bucket");response.raise_for_status()
        snapshot["storage_buckets"]=response.json()
    raw=zlib.compress(json.dumps(snapshot,separators=(",", ":")).encode(),9)
    encrypted=protect(raw)
    assert hashlib.sha256(protect(encrypted,True)).digest()==hashlib.sha256(raw).digest()
    out=ROOT/"output"/"gbp-migration";out.mkdir(parents=True,exist_ok=True)
    target=out/(datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")+"-growboard.dpapi")
    target.write_bytes(encrypted)
    report={"file":str(target),"tables":len(TABLES),"rows":sum(len(v) for v in snapshot["tables"].values()),
            "auth_records":len(users),"storage_object_bytes_backed_up":False,"encrypted_roundtrip_verified":True}
    (out/"latest-snapshot.json").write_text(json.dumps(report,indent=2))
    print(json.dumps(report))


if __name__=="__main__":main()
