# SPDX-FileCopyrightText: 2025 Coop IT Easy SC
#
# SPDX-License-Identifier: AGPL-3.0-or-later

from odoo import _, api, models
from odoo.exceptions import UserError


class AccountInvoice(models.Model):
    _inherit = "account.invoice"

    @api.multi
    def action_invoice_open(self):
        for invoice in self:
            if (
                invoice.company_id.account_peppol_proxy_state != "active"
                or not invoice.is_sale_document()
                # this is a dirty hack to avoid blocking invoicing from the
                # pos. in case of an invalid invoice, it will have to be
                # corrected manually later.
                or "pos_picking_id" in invoice._context
            ):
                # don't check invoices for companies that are not ready to
                # send through peppol or invoices that are not outbound or are
                # created from the point of sale.
                continue
            partner = self.partner_id.commercial_partner_id
            if not partner.account_peppol_is_endpoint_valid:
                # don't check invoices that won't be send through peppol
                continue
            # check that sender and receiver have an email address (peppol
            # requirement)
            company_partner = invoice.company_id.partner_id
            if not company_partner.email:
                raise UserError(
                    _('Missing email address for partner "%s".') % company_partner.name
                )
            if not partner.email:
                raise UserError(
                    _('Missing email address for partner "%s".') % partner.name
                )
            # require a payment mode, because without one, base_ubl_payment
            # issues a warning and uses payment mode 31, while for a wire
            # transfer, payment mode 30 should be used.
            if not self.payment_mode_id:
                raise UserError(_("A payment mode is required."))
            for line in invoice.invoice_line_ids:
                # check existence of a product on each line (or base_ubl will
                # ignore it)
                if not line.product_id:
                    raise UserError(
                        _(
                            'Missing product on line "%s". Having a product '
                            "on invoice lines is necessary to correctly send "
                            "the invoice through Peppol."
                        )
                        % line.name
                    )
                # check existence of one tax on each line (peppol requirement)
                taxes = line.invoice_line_tax_ids
                if not taxes:
                    raise UserError(_('Missing taxes on line "%s".') % line.name)
                if len(taxes) != 1:
                    raise UserError(
                        _('There must be only one tax on line "%s".') % line.name
                    )
                tax = taxes[0]
                # check unece tax type and category (would cause an error
                # during ubl generation)
                if not tax.unece_type_id:
                    raise UserError(_('Missing UNECE Tax Type on tax "%s".') % tax.name)
                if not tax.unece_categ_id:
                    raise UserError(
                        _('Missing UNECE Tax Category on tax "%s".') % tax.name
                    )
        return super().action_invoice_open()

    @api.onchange("partner_id", "company_id")
    def _onchange_partner_id(self):
        # the account_payment_partner module removes the payment mode if no
        # partner is set or if no company is set or if the partner has no
        # default payment mode. this prevents to use a user-defined default
        # payment mode. what we want:
        # * on a new invoice form, the user-defined default payment mode is
        #   set if it exists.
        # * when selecting a partner that has no default payment mode:
        #   ideally, the user-defined default should be set, but that is
        #   difficult to do, so fall back to no change to the payment mode.
        # * when selecting a partner that has a default payment mode: select
        #   it (default behavior of account_payment_partner).
        # * when removing the partner: ideally, the user-defined default
        #   should be set, but that is difficult to do, so fall back to no
        #   change to the payment mode.
        payment_mode = self.payment_mode_id
        res = super()._onchange_partner_id()
        if self.type != "out_invoice":
            # don't change behavior on other invoice types.
            return res
        if not self.payment_mode_id:
            self.payment_mode_id = payment_mode
        return res
