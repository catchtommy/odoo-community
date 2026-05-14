{
    'name': 'Shiningace Website',
    'version': '19.0.1.0.2',
    'summary': 'Public-facing landing page for Shiningace tutoring platform',
    'category': 'Website',
    'author': 'Shiningace',
    'depends': ['website'],
    'data': [
        'views/landing_page.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'shiningace_website/static/src/css/landing.css',
            'shiningace_website/static/src/js/landing.js',
        ],
    },
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
