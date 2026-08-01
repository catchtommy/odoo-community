# -*- coding: utf-8 -*-
{
    'name': 'Education AI',
    'version': '19.0.1.0.0',
    'category': 'Education',
    'summary': 'AI lesson planning, quiz generation, RAG integration (future phase)',
    'description': """
Education AI (future phase — not yet implemented)
====================================================
Will provide AI lesson planning, homework/quiz/revision-notes/flashcard
generation, a tutor/student AI assistant, and RAG/embeddings integration.
Schema-only groundwork already exists: every model inheriting
education.abstract.mixin (education_core, education_curriculum,
education_content, education_course) already carries keywords/
ai_description/embedding_synced fields, so this module can bolt on without
any schema changes to earlier modules. Must remain optional/removable
without affecting the rest of the suite — no other module may depend on it.
    """,
    'author': 'ShiningAce',
    'website': 'https://www.shiningace.com',
    'license': 'LGPL-3',
    'depends': ['education_progress', 'education_course'],
    'data': [],
    'installable': False,
    'application': False,
}
