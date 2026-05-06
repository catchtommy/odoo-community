from odoo import http
from odoo.http import request


class ShiningaceWebsite(http.Controller):

    @http.route('/', auth='public', website=True, type='http', csrf=False)
    def landing_page(self, **kw):
        return request.render('shiningace_website.landing_page', {})

    @http.route('/book-demo', auth='public', website=True, type='http', csrf=False)
    def book_demo(self, **kw):
        return request.render('shiningace_website.landing_page', {})
