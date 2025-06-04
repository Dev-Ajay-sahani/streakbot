import os
from supabase import create_client, Client
import postgrest  # import for exception handling

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ---------- USER STREAKS ----------
def get_streak(user_id: str) -> int:
    try:
        # Avoid using .single() to prevent the multiple/no rows error
        res = supabase.table("streaks").select("streak").eq("user_id", user_id).execute()
        if res.data and len(res.data) > 0:
            return res.data[0]["streak"]
        else:
            return 0
    except postgrest.exceptions.APIError:
        return 0

def increment_streak(user_id: str):
    current = get_streak(user_id)
    if current == 0:
        supabase.table("streaks").upsert({"user_id": user_id, "streak": 1}).execute()
    else:
        supabase.table("streaks").update({"streak": current + 1}).eq("user_id", user_id).execute()

def reset_streak(user_id: str):
    exists = get_streak(user_id)
    if exists:
        supabase.table("streaks").update({"streak": 0}).eq("user_id", user_id).execute()
    else:
        supabase.table("streaks").insert({"user_id": user_id, "streak": 0}).execute()

# ---------- SERVER CONFIG (channel & role) ----------
def set_config(channel_id: int, role_id: int):
    supabase.table("config").upsert({
        "id": 1,  # assuming one config per server
        "channel_id": channel_id,
        "role_id": role_id
    }).execute()

def get_config():
    res = supabase.table("config").select("*").eq("id", 1).single().execute()
    return res.data if res.data else None
