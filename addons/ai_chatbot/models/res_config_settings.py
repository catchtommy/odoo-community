# -*- coding: utf-8 -*-
"""
Extends res.config.settings to expose AI Chatbot configuration in the
Settings UI (Technical → AI Chatbot section).
"""
from odoo import api, fields, models

HF_ENDPOINT_PARAM = "ai_chatbot.hf_endpoint_url"
ENABLED_PARAM = "ai_chatbot.enabled"
TITLE_PARAM = "ai_chatbot.title"
PLACEHOLDER_PARAM = "ai_chatbot.placeholder"


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    # ── Toggle ────────────────────────────────────────────────────────────────
    ai_chatbot_enabled = fields.Boolean(
        string="Enable AI Chatbot",
        help="Show the floating AI assistant on all website and portal pages.",
        config_parameter=ENABLED_PARAM,
    )

    # ── API Endpoint ──────────────────────────────────────────────────────────
    ai_chatbot_hf_endpoint = fields.Char(
        string="Hugging Face Endpoint URL",
        help="Full URL to your LangChain API endpoint, e.g. https://your-space.hf.space/webhook",
        config_parameter=HF_ENDPOINT_PARAM,
    )

    # ── UI Customisation ──────────────────────────────────────────────────────
    ai_chatbot_title = fields.Char(
        string="Chat Window Title",
        help="Title shown at the top of the chat window.",
        config_parameter=TITLE_PARAM,
        default="AI Assistant",
    )

    ai_chatbot_placeholder = fields.Char(
        string="Input Placeholder",
        help="Placeholder text shown in the message input box.",
        config_parameter=PLACEHOLDER_PARAM,
        default="Type your question…",
    )
