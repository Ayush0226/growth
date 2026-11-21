"""OAuth-only MCP adapters over the same workspace-checked HTTP handlers.

Disabled until Supabase OAuth Server, consent UI and client linking are verified.
Ordinary browser sessions cannot authenticate MCP clients.
"""
import asyncio
from datetime import datetime
from urllib.parse import urlparse
from uuid import UUID

import jwt
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations

from app.access import access_state
from app.config import Settings
from app.database import db
from app.gbp import service
from app.routes import google as api
from app.security import CurrentUser

SCOPES = ["openid", "email", "profile", "offline_access"]


class Verifier(TokenVerifier):
    async def verify_token(self, token):
        try:
            response = await asyncio.to_thread(db().auth.get_user, token)
            user = response.user
            if not user or not (await asyncio.to_thread(access_state, str(user.id)))[0]:
                return None
            # The identical token has just been validated by Supabase Auth.
            claims = jwt.decode(token, options={"verify_signature":False, "verify_exp":False, "verify_aud":False})
            client = claims.get("client_id")
            if not isinstance(client,str) or not client:
                return None
            return AccessToken(token=token,client_id=client,scopes=SCOPES,
                               expires_at=int(claims["exp"]),subject=str(user.id),claims={"email":user.email})
        except Exception:
            return None


async def identity():
    token = get_access_token()
    if not token or not token.subject or not (await asyncio.to_thread(access_state, token.subject))[0]:
        raise PermissionError("Authorized Growboard access is required")
    return CurrentUser(token.subject,(token.claims or {}).get("email"))


def create_server(settings: Settings):
    resource = str(settings.google_mcp_resource_url).rstrip("/")
    server = MCPServer(name="growboard-google",title="Growboard Google Business Profile",version="1.0.0",
        instructions="Resolve locations before location-scoped actions. Show exact content, targets and publication time before a public write. Never return provider tokens or ask for passwords.",
        token_verifier=Verifier(),auth=AuthSettings(issuer_url=str(settings.supabase_url).rstrip("/")+"/auth/v1",
            resource_server_url=resource,required_scopes=SCOPES,validate_token_resource=False))
    read = ToolAnnotations(read_only_hint=True,destructive_hint=False,open_world_hint=False)
    write = ToolAnnotations(read_only_hint=False,destructive_hint=False,open_world_hint=True)

    @server.tool(name="list_locations",annotations=read)
    async def list_locations():
        return await api.locations(await identity(),settings)

    @server.tool(name="list_business_accounts",annotations=read)
    async def list_business_accounts():
        result=await api.locations(await identity(),settings);accounts={}
        for loc in result["locations"]:
            accounts.setdefault(loc["account_name"],{"account_id":loc["account_name"],"name":loc.get("account_display_name"),"location_count":0})["location_count"]+=1
        return {"accounts":list(accounts.values())}

    @server.tool(name="get_account_overview",annotations=read)
    async def get_account_overview():
        user=await identity()
        return {"connection":await api.status(user,settings),"locations":await api.locations(user,settings)}

    @server.tool(name="list_reviews",annotations=read)
    async def list_reviews(location_id: str, page_token: str=""):
        return await api.reviews(api.ReviewsInput(location_id=location_id,page_token=page_token),await identity(),settings)

    @server.tool(name="draft_review_reply",annotations=read)
    async def draft_review_reply(review_id: str, tone: str="friendly professional", language: str="English"):
        return await api.draft_reply(api.DraftReplyInput(review_name=review_id,tone=tone,language=language),await identity(),settings)

    @server.tool(name="publish_review_reply",description="Publish the exact reply to the selected review after the user authorizes its content and target.",annotations=write)
    async def publish_review_reply(review_id: str,reply_text: str):
        return await api.reply(api.ReplyInput(review_id=review_id,reply_text=reply_text),await identity(),settings)

    @server.tool(name="list_review_automation_rules",annotations=read)
    async def list_review_automation_rules():
        return await api.rules(await identity(),settings)

    @server.tool(name="configure_review_automation_rule",description="Configure future review replies. Enabling requires the owner's authorization and confirmation that other products will not reply automatically.",annotations=write)
    async def configure_review_automation_rule(location_id:str,enabled:bool=False,mode:str="draft",min_rating:int=4,max_rating:int=5,
                                              tone:str="friendly professional",language:str="English",daily_limit:int=20,
                                              exclusive_delivery_confirmed:bool=False):
        data=api.RuleInput(location_id=location_id,enabled=enabled,mode=mode,min_rating=min_rating,max_rating=max_rating,
                           tone=tone,language=language,daily_limit=daily_limit,exclusive_delivery_confirmed=exclusive_delivery_confirmed)
        return await api.save_rule(data,await identity(),settings)

    @server.tool(name="list_review_reply_jobs",annotations=read)
    async def list_review_reply_jobs():
        return await api.review_jobs(await identity(),settings)

    @server.tool(name="approve_review_reply_job",description="Approve and publish the selected draft after showing its exact text and target to the user.",annotations=write)
    async def approve_review_reply_job(job_id:UUID):
        return await api.approve(job_id,await identity(),settings)

    @server.tool(name="cancel_review_reply_job",annotations=write)
    async def cancel_review_reply_job(job_id:UUID):
        return await api.cancel_reply(job_id,await identity(),settings)

    @server.tool(name="list_scheduled_posts",annotations=read)
    async def list_scheduled_posts():
        return await api.posts(await identity(),settings)

    @server.tool(name="schedule_post",description="Schedule exact post text for the selected location and timezone-aware time after the user authorizes it.",annotations=write)
    async def schedule_post(location_id:str,caption:str,publish_at:datetime,request_id:UUID):
        return await api.create_post(api.PostInput(location_id=location_id,summary=caption,scheduled_for=publish_at,request_id=request_id),await identity(),settings)

    @server.tool(name="cancel_scheduled_post",annotations=write)
    async def cancel_scheduled_post(post_id:UUID):
        return await api.cancel_post(post_id,await identity(),settings)

    @server.tool(name="list_content_campaigns",annotations=read)
    async def list_content_campaigns():
        return await api.campaigns(await identity(),settings)

    @server.tool(name="create_content_campaign",annotations=write)
    async def create_content_campaign(title:str,summary:str,location_ids:list[str],timezone:str="Asia/Kolkata"):
        return await api.create_campaign(api.CampaignInput(title=title,summary=summary,location_ids=location_ids,timezone=timezone),await identity(),settings)

    @server.tool(name="schedule_content_campaign",description="Schedule the selected campaign after user authorization of its targets, text and time.",annotations=write)
    async def schedule_content_campaign(campaign_id:UUID,publish_at:datetime):
        return await api.schedule_campaign(campaign_id,api.CampaignSchedule(publish_at=publish_at),await identity(),settings)

    @server.tool(name="cancel_content_campaign",annotations=write)
    async def cancel_content_campaign(campaign_id:UUID):
        return await api.cancel_campaign(campaign_id,await identity(),settings)

    @server.tool(name="list_media_assets",annotations=read)
    async def list_media_assets():
        return await api.media(await identity(),settings)

    @server.tool(name="generate_local_rank_report",annotations=write)
    async def generate_local_rank_report(location_id:str,keyword:str,request_id:UUID):
        return await api.rank(api.RankInput(location_id=location_id,keyword=keyword,request_id=request_id),await identity(),settings)

    security=TransportSecuritySettings(enable_dns_rebinding_protection=True,
        allowed_hosts=[urlparse(resource).netloc,"localhost:*","127.0.0.1:*","testserver"],
        allowed_origins=settings.cors_origins())
    return server,server.streamable_http_app(transport_security=security)
