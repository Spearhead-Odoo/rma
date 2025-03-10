# Copyright 2020 Tecnativa - Ernesto Tejeda
# Copyright 2022-2025 Tecnativa - Víctor Martínez
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, exceptions, http
from odoo.exceptions import AccessError, MissingError
from odoo.http import request
from odoo.tools import consteq

from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.addons.portal.controllers.portal import pager as portal_pager


class PortalRma(CustomerPortal):
    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if "rma_count" in counters:
            rma_model = request.env["rma"]
            rma_count = (
                rma_model.search_count([]) if rma_model.has_access("read") else 0
            )
            values["rma_count"] = rma_count
        return values

    def _rma_get_page_view_values(self, rma, access_token, **kwargs):
        values = {
            "page_name": "RMA",
            "rma": rma,
        }
        return self._get_page_view_values(
            rma, access_token, values, "my_rmas_history", False, **kwargs
        )

    def _get_filter_domain(self, kw):
        return []

    @http.route(
        ["/my/rmas", "/my/rmas/page/<int:page>"], type="http", auth="user", website=True
    )
    def portal_my_rmas(self, page=1, date_begin=None, date_end=None, sortby=None, **kw):
        values = self._prepare_portal_layout_values()
        rma_obj = request.env["rma"]
        # Avoid error if the user does not have access.
        if not rma_obj.has_access("read"):
            return request.redirect("/my")
        domain = self._get_filter_domain(kw)
        searchbar_sortings = {
            "date": {"label": _("Date"), "order": "date desc"},
            "name": {"label": _("Name"), "order": "name desc"},
            "state": {"label": _("Status"), "order": "state"},
        }
        # default sort by order
        if not sortby:
            sortby = "date"
        order = searchbar_sortings[sortby]["order"]
        if date_begin and date_end:
            domain += [
                ("create_date", ">", date_begin),
                ("create_date", "<=", date_end),
            ]
        # count for pager
        rma_count = rma_obj.search_count(domain)
        # pager
        pager = portal_pager(
            url="/my/rmas",
            url_args={
                "date_begin": date_begin,
                "date_end": date_end,
                "sortby": sortby,
            },
            total=rma_count,
            page=page,
            step=self._items_per_page,
        )
        # content according to pager and archive selected
        rmas = rma_obj.search(
            domain, order=order, limit=self._items_per_page, offset=pager["offset"]
        )
        request.session["my_rmas_history"] = rmas.ids[:100]
        values.update(
            {
                "date": date_begin,
                "rmas": rmas,
                "page_name": "RMA",
                "pager": pager,
                "default_url": "/my/rmas",
                "searchbar_sortings": searchbar_sortings,
                "sortby": sortby,
            }
        )
        return request.render("rma.portal_my_rmas", values)

    @http.route(["/my/rmas/<int:rma_id>"], type="http", auth="public", website=True)
    def portal_my_rma_detail(
        self, rma_id, access_token=None, report_type=None, download=False, **kw
    ):
        try:
            rma_sudo = self._document_check_access("rma", rma_id, access_token)
        except (AccessError, MissingError):
            return request.redirect("/my")
        if report_type in ("html", "pdf", "text"):
            return self._show_report(
                model=rma_sudo,
                report_type=report_type,
                report_ref="rma.report_rma_action",
                download=download,
            )

        values = self._rma_get_page_view_values(rma_sudo, access_token, **kw)
        return request.render("rma.portal_rma_page", values)

    @http.route(
        ["/my/rma/picking/pdf/<int:rma_id>/<int:picking_id>"],
        type="http",
        auth="public",
        website=True,
    )
    def portal_my_rma_picking_report(self, rma_id, picking_id, access_token=None, **kw):
        try:
            picking_sudo = self._picking_check_access(
                rma_id, picking_id, access_token=access_token
            )
        except exceptions.AccessError:
            return request.redirect("/my")
        report_sudo = request.env.ref("stock.action_report_delivery").sudo()
        pdf = report_sudo._render_qweb_pdf(report_sudo, res_ids=picking_sudo.ids)[0]
        pdfhttpheaders = [
            ("Content-Type", "application/pdf"),
            ("Content-Length", len(pdf)),
        ]
        return request.make_response(pdf, headers=pdfhttpheaders)

    def _picking_check_access(self, rma_id, picking_id, access_token=None):
        rma = request.env["rma"].browse([rma_id])
        picking = request.env["stock.picking"].browse([picking_id])
        picking_sudo = picking.sudo()
        try:
            picking.check_access("read")
        except exceptions.AccessError:
            if not access_token or not consteq(rma.access_token, access_token):
                raise
        return picking_sudo
