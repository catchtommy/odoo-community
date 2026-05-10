# -*- coding: utf-8 -*-
{
    "name": "AI Chatbot (LangChain + Groq)",
    "version": "19.0.1.0.0",
    "summary": "Floating AI chat assistant powered by LangChain on Hugging Face + Groq Llama3",
    "category": "Website",
    "author": "Shiningace",
    "license": "LGPL-3",
    "depends": [
        "base",
        "web",
        "website",
        "portal",
        "base_setup",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_config_parameter.xml",
        "views/res_config_settings_views.xml",
        "views/website_templates.xml",
    ],
    "assets": {
        # Load on the public website / portal frontend
        "web.assets_frontend": [
            "ai_chatbot/static/src/css/ai_chatbot.css",
            "ai_chatbot/static/src/js/ai_chatbot.js",
        ],
    },
    "installable": True,
    "auto_install": False,
    "application": False,
}
