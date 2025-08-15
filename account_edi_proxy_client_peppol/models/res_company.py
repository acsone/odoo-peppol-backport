# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    account_edi_proxy_client_peppol_ids = fields.One2many('account_edi_proxy_client_peppol.user', inverse_name='company_id')
