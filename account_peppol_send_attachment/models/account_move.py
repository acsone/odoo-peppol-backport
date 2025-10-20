# Copyright 2025 ACSONE SA/NV
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    peppol_attachment_ids = fields.Many2many(
        comodel_name="ir.attachment",
        string="Peppol Attachments",
        copy=False,
    )
