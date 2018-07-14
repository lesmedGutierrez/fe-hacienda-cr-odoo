# -*- coding: utf-8 -*-

import json
import requests
import logging
import re
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools.safe_eval import safe_eval
import datetime
import pytz
import base64
import xml.etree.ElementTree as ET

_logger = logging.getLogger(__name__)


class IdentificationType(models.Model):
    _name = "identification.type"

    code = fields.Char(string="Código", required=False, )
    name = fields.Char(string="Nombre", required=False, )
    notes = fields.Text(string="Notas", required=False, )

class CompanyElectronic(models.Model):
    _name = 'res.company'
    _inherit = ['res.company','mail.thread','ir.needaction_mixin']

    commercial_name = fields.Char(string="Nombre comercial", required=False, )
    phone_code = fields.Char(string="Código de teléfono", required=False, size=3, default="506")
    fax_code = fields.Char(string="Código de Fax", required=False,)
    signature = fields.Binary(string="Llave Criptográfica", )
    identification_id = fields.Many2one(comodel_name="identification.type", string="Tipo de identificacion", required=False, )
    district_id = fields.Many2one(comodel_name="res.country.district", string="Distrito", required=False, )
    county_id = fields.Many2one(comodel_name="res.country.county", string="Cantón", required=False, )
    neighborhood_id = fields.Many2one(comodel_name="res.country.neighborhood", string="Barrios", required=False, )
    frm_ws_identificador = fields.Char(string="Usuario de Factura Electrónica", required=False,)
    frm_ws_password = fields.Char(string="Password de Factura Electrónica", required=False,)
    security_code = fields.Char(string="Código de seguridad para Factura Electrónica", size=8, required=False,)
    frm_ws_ambiente = fields.Selection(
        selection=[('disabled','Deshabilitado'),('stag', 'Pruebas'), ('prod', 'Producción'), ], string="Ambiente",
        required=True, default='disabled', help='Es el ambiente en al cual se le está actualizando el certificado. Para el ambiente de calidad (stag) c3RhZw==, '
                                                                                                                                                            'para el ambiente de producción (prod) '
                                                                                                                                           'cHJvZA==. Requerido.')
    frm_pin = fields.Char(string="Pin", required=False, help='Es el pin correspondiente al certificado. Requerido')
    frm_callback_url = fields.Char(string="Callback Url", required=False, default="https://url_callback/repuesta.php?", help='Es la URL en a la cual se reenviarán las respuestas de Hacienda.')

    activated = fields.Boolean(string="Activated", required=False, default=True)
    state = fields.Selection(
        [('active', 'Activo'),
         ('inactive','Inactivo')], string='Status', readonly=False, required=False, track_visibility='always',
        copy=False, default='active',)

    @api.onchange('email')
    def _onchange_email(self):
        pass


class PartnerElectronic(models.Model):
    _inherit = "res.partner"

    commercial_name = fields.Char(string="Nombre comercial", required=False, )
    phone_code = fields.Char(string="Código de teléfono", required=False, default="506")
    fax_code = fields.Char(string="Código de Fax", required=False,)
    state_id = fields.Many2one(comodel_name="res.country.state", string="Provincia", required=False, )
    district_id = fields.Many2one(comodel_name="res.country.district", string="Distrito", required=False, )
    county_id = fields.Many2one(comodel_name="res.country.county", string="Cantón", required=False, )
    neighborhood_id = fields.Many2one(comodel_name="res.country.neighborhood", string="Barrios", required=False, )
    identification_id = fields.Many2one(comodel_name="identification.type", string="Tipo de identificacion", required=False, )
    payment_methods_id = fields.Many2one(comodel_name="payment.methods", string="Métodos de Pago", required=False, )

    _sql_constraints = [
        ('vat_uniq', 'unique (vat)', "La cédula debe ser única"),
    ]

    @api.onchange('phone')
    def _onchange_phone(self):
        numbers = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9']
        if self.phone:
            for p in str(self.phone):
                if p not in numbers:
                    alert = {
                        'title': 'Atención',
                        'message': 'Favor no introducir letras, espacios ni guiones en los números telefónicos.'
                        }
                    return {'value': {'phone':''}, 'warning': alert}

    @api.onchange('mobile')
    def _onchange_mobile(self):
        numbers = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9']
        if self.mobile:
            for p in str(self.mobile):
                if p not in numbers:
                    alert = {
                        'title': 'Atención',
                        'message': 'Favor no introducir letras, espacios ni guiones en los números telefónicos.'
                    }
                    return {'value': {'mobile': ''},'warning': alert}

    @api.onchange('fax')
    def _onchange_mobile(self):
        numbers = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9']
        if self.fax:
            for p in str(self.fax):
                if p not in numbers:
                    alert = {
                        'title': 'Atención',
                        'message': 'Favor no introducir letras, espacios ni guiones en el fax.'
                    }
                    return {'value': {'fax': ''},'warning': alert}

    @api.onchange('email')
    def _onchange_email(self):
        if self.email:
            if not re.match('^[(a-z0-9\_\-\.)]+@[(a-z0-9\_\-\.)]+\.[(a-z)]{2,15}$', self.email.lower()):
                vals = {'email': False}
                alerta = {
                    'title': 'Atención',
                    'message': 'El correo electrónico no cumple con una estructura válida. '+str(self.email)
                    }
                return {'value': vals, 'warning': alerta}

    @api.onchange('vat')
    def _onchange_vat(self):
        if self.identification_id and self.identification_id.code == '01':
            if len(self.vat) != 9:
                raise UserError('La identificación tipo Cédula física debe de contener 9 dígitos, sin cero al inicio y sin guiones.')
        if self.identification_id and self.identification_id.code == '02':
            if len(self.vat) != 10:
                raise UserError('La identificación tipo Cédula jurídica debe contener 10 dígitos, sin cero al inicio y sin guiones.')
        if self.identification_id and self.identification_id.code == '03':
            if len(self.vat) < 11 or len(self.vat) > 12:
                raise UserError('La identificación tipo DIMEX debe contener 11 o 12 dígitos, sin ceros al inicio y sin guiones.')
        if self.identification_id and self.identification_id.code == '04':
            if len(self.vat) != 9:
                raise UserError('La identificación tipo NITE debe contener 10 dígitos, sin ceros al inicio y sin guiones.')
        if self.identification_id and self.identification_id.code == '05':
            if len(self.vat) < 10 or len(self.vat) > 20:
                raise UserError('La identificación tipo Extrangero debe ser de 10 dígitos.')


class CodeTypeProduct(models.Model):
    _name = "code.type.product"

    code = fields.Char(string="Código", required=False, )
    name = fields.Char(string="Nombre", required=False, )


class ProductElectronic(models.Model):
    _inherit = "product.template"

    @api.model
    def _default_code_type_id(self):
        code_type_id = self.env['code.type.product'].search([('code','=','04')], limit=1)
        return code_type_id or False

    commercial_measurement = fields.Char(string="Unidad de Medida Comercial", required=False, )
    code_type_id = fields.Many2one(comodel_name="code.type.product", string="Tipo de código", required=False, default=_default_code_type_id)


class InvoiceTaxElectronic(models.Model):
    _inherit = "account.tax"

    tax_code = fields.Char(string="Código de impuesto", required=False, )


# class Exoneration(models.Model):
# 	_name = "exoneration"
#
# 	code = fields.Char(string="Código", required=False, )
# 	type = fields.Char(string="Tipo", required=False, )
# 	exoneration_number = fields.Char(string="Número de exoneración", required=False, )
# 	name_institution = fields.Char(string="Nombre de institución", required=False, )
# 	date = fields.Date(string="Fecha", required=False, )
# 	percentage_exoneration = fields.Float(string="Porcentaje de exoneración", required=False, )


class PaymentMethods(models.Model):
    _name = "payment.methods"

    active = fields.Boolean(string="Activo", required=False, default=True)
    sequence = fields.Char(string="Secuencia", required=False, )
    name = fields.Char(string="Nombre", required=False, )
    notes = fields.Text(string="Notas", required=False, )


class SaleConditions(models.Model):
    _name = "sale.conditions"

    active = fields.Boolean(string="Activo", required=False, default=True)
    sequence = fields.Char(string="Secuencia", required=False, )
    name = fields.Char(string="Nombre", required=False, )
    notes = fields.Text(string="Notas", required=False, )

class AccountPaymentTerm(models.Model):
    _inherit = "account.payment.term"
    sale_conditions_id = fields.Many2one(comodel_name="sale.conditions", string="Condiciones de venta" )


class ReferenceDocument(models.Model):
    _name = "reference.document"

    active = fields.Boolean(string="Activo", required=False, default=True)
    code = fields.Char(string="Código", required=False, )
    name = fields.Char(string="Nombre", required=False, )


class ReferenceCode(models.Model):
    _name = "reference.code"

    active = fields.Boolean(string="Activo", required=False, default=True)
    code = fields.Char(string="Código", required=False, )
    name = fields.Char(string="Nombre", required=False, )


class Resolution(models.Model):
    _name = "resolution"

    active = fields.Boolean(string="Activo", required=False, default=True)
    name = fields.Char(string="Nombre", required=False, )
    date_resolution = fields.Date(string="Fecha de resolución", required=False, )


class ProductUom(models.Model):
    _inherit = "product.uom"
    code = fields.Char(string="Código", required=False, )


class AccountJournal(models.Model):
    _inherit = "account.journal"
    nd = fields.Boolean(string="Nota de Débito", required=False, )


class AccountInvoiceRefund(models.TransientModel):
    _inherit = "account.invoice.refund"

    @api.model
    def _get_invoice_id(self):
        context = dict(self._context or {})
        active_id = context.get('active_id', False)
        if active_id:
            return active_id
        return ''

    reference_code_id = fields.Many2one(comodel_name="reference.code", string="Código de referencia", required=True, )
    invoice_id = fields.Many2one(comodel_name="account.invoice", string="Documento de referencia", default=_get_invoice_id, required=False, )

    @api.multi
    def compute_refund(self, mode='refund'):
        if self.env.user.company_id.frm_ws_ambiente == 'disabled':
            result = super(AccountInvoiceRefund, self).compute_refund()
            return result
        else:
            inv_obj = self.env['account.invoice']
            inv_tax_obj = self.env['account.invoice.tax']
            inv_line_obj = self.env['account.invoice.line']
            context = dict(self._context or {})
            xml_id = False

            for form in self:
                created_inv = []
                date = False
                description = False
                for inv in inv_obj.browse(context.get('active_ids')):
                    if inv.state in ['draft', 'proforma2', 'cancel']:
                        raise UserError(_('Cannot refund draft/proforma/cancelled invoice.'))
                    if inv.reconciled and mode in ('cancel', 'modify'):
                        raise UserError(_('Cannot refund invoice which is already reconciled, invoice should be unreconciled first. You can only refund this invoice.'))

                    date = form.date or False
                    description = form.description or inv.name
                    refund = inv.refund(form.date_invoice, date, description, inv.journal_id.id, form.invoice_id.id, form.reference_code_id.id)

                    created_inv.append(refund.id)
                    if mode in ('cancel', 'modify'):
                        movelines = inv.move_id.line_ids
                        to_reconcile_ids = {}
                        to_reconcile_lines = self.env['account.move.line']
                        for line in movelines:
                            if line.account_id.id == inv.account_id.id:
                                to_reconcile_lines += line
                                to_reconcile_ids.setdefault(line.account_id.id, []).append(line.id)
                            if line.reconciled:
                                line.remove_move_reconcile()
                        refund.action_invoice_open()
                        for tmpline in refund.move_id.line_ids:
                            if tmpline.account_id.id == inv.account_id.id:
                                to_reconcile_lines += tmpline
                        to_reconcile_lines.filtered(lambda l: l.reconciled == False).reconcile()
                        if mode == 'modify':
                            invoice = inv.read(inv_obj._get_refund_modify_read_fields())
                            invoice = invoice[0]
                            del invoice['id']
                            invoice_lines = inv_line_obj.browse(invoice['invoice_line_ids'])
                            invoice_lines = inv_obj.with_context(mode='modify')._refund_cleanup_lines(invoice_lines)
                            tax_lines = inv_tax_obj.browse(invoice['tax_line_ids'])
                            tax_lines = inv_obj._refund_cleanup_lines(tax_lines)
                            invoice.update({
                                'type': inv.type,
                                'date_invoice': form.date_invoice,
                                'state': 'draft',
                                'number': False,
                                'invoice_line_ids': invoice_lines,
                                'tax_line_ids': tax_lines,
                                'date': date,
                                'origin': inv.origin,
                                'fiscal_position_id': inv.fiscal_position_id.id,
                                'invoice_id': inv.id,#agregado
                                'reference_code_id': form.reference_code_id.id,#agregado
                            })
                            for field in inv_obj._get_refund_common_fields():
                                if inv_obj._fields[field].type == 'many2one':
                                    invoice[field] = invoice[field] and invoice[field][0]
                                else:
                                    invoice[field] = invoice[field] or False
                            inv_refund = inv_obj.create(invoice)
                            if inv_refund.payment_term_id.id:
                                inv_refund._onchange_payment_term_date_invoice()
                            created_inv.append(inv_refund.id)
                    xml_id = (inv.type in ['out_refund', 'out_invoice']) and 'action_invoice_tree1' or \
                             (inv.type in ['in_refund', 'in_invoice']) and 'action_invoice_tree2'
                    # Put the reason in the chatter
                    subject = _("Invoice refund")
                    body = description
                    refund.message_post(body=body, subject=subject)
            if xml_id:
                result = self.env.ref('account.%s' % (xml_id)).read()[0]
                invoice_domain = safe_eval(result['domain'])
                invoice_domain.append(('id', 'in', created_inv))
                result['domain'] = invoice_domain
                return result
            return True


class InvoiceLineElectronic(models.Model):
    _inherit = "account.invoice.line"

    total_amount = fields.Float(string="Monto total", required=False, )
    total_discount = fields.Float(string="Total descuento", required=False, )
    discount_note = fields.Char(string="Nota de descuento", required=False, )
    total_tax = fields.Float(string="Total impuesto", required=False, )
    #exoneration_total = fields.Float(string="Exoneración total", required=False, )
    #total_line_exoneration = fields.Float(string="Exoneración total de la línea", required=False, )
    #exoneration_id = fields.Many2one(comodel_name="exoneration", string="Exoneración", required=False, )

