# -*- coding: utf-8 -*-
import json
import logging
import ssl
import urllib.request
import urllib.error

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

HF_ENDPOINT_PARAM  = "ai_chatbot.hf_endpoint_url"
HF_ENDPOINT_DEFAULT = "https://catchtommy-shiningace-ai-chat-backend.hf.space/webhook"
REQUEST_TIMEOUT    = 60


class AIChatbotController(http.Controller):

    @http.route(
        "/ai_chatbot/chat",
        type="jsonrpc",
        auth="public",
        methods=["POST"],
        csrf=False,
        website=True,
    )
    def chat(self, message="", history=None, session_id=None, **kwargs):
        if not message or not message.strip():
            return {"error": "Empty message."}

        ICP = request.env["ir.config_parameter"].sudo()
        endpoint_url = ICP.get_param(HF_ENDPOINT_PARAM, default=HF_ENDPOINT_DEFAULT).rstrip("/")

        payload = json.dumps({
            "message": message.strip(),
            "history": history or [],
            "session_id": session_id or request.session.sid or "default",
        }).encode("utf-8")

        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE

        headers = {
            "Content-Type": "application/json",
            "Accept":       "application/json",
            "User-Agent":   "Odoo-AI-Chatbot/1.0",
        }

        try:
            req = urllib.request.Request(
                endpoint_url,
                data=payload,
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT, context=ssl_ctx) as resp:
                raw  = resp.read().decode("utf-8")
                data = json.loads(raw)

        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8")[:400]
            except Exception:
                pass
            _logger.error("ai_chatbot: HTTP %s — %s — %s", exc.code, exc.reason, body)
            return {"error": f"AI service returned an error ({exc.code}). Please try again."}

        except urllib.error.URLError as exc:
            _logger.error("ai_chatbot: Cannot reach HF API — %s", exc.reason)
            return {"error": "Cannot reach the AI service. Please try again later."}

        except json.JSONDecodeError:
            _logger.error("ai_chatbot: Invalid JSON from HF API — %s", raw[:200])
            return {"error": "Received an unexpected response from the AI service."}

        ai_response = (
            data.get("reply")
            or data.get("response")
            or data.get("answer")
            or data.get("output")
            or data.get("text")
            or data.get("message")
            or ""
        )
        if not ai_response:
            _logger.warning("ai_chatbot: Unexpected response shape — %s", data)
            return {"error": "The AI returned an empty response. Please rephrase and try again."}

        return {"response": ai_response}
