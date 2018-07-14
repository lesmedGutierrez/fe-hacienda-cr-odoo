# -*- coding: utf-8 -*-

import json
import requests
import logging
import re
from odoo import models, fields, api, _
from odoo.exceptions import UserError
# from odoo.tools.safe_eval import safe_eval
import datetime
import pytz
import base64
import xml.etree.ElementTree as ET

_logger = logging.getLogger(__name__)


class AccountInvoiceElectronic(models.Model):
    _inherit = "account.invoice"

    number_electronic = fields.Char(
        string="Número electrónico", required=False, copy=False, index=True)
    date_issuance = fields.Char(
        string="Fecha de emisión", required=False, copy=False)
    state_send_invoice = fields.Selection(
        [('aceptado', 'Aceptado'), ('rechazado', 'Rechazado'),],
        'Estado FE Proveedor')
    state_tributacion = fields.Selection(
        [('aceptado', 'Aceptado'), ('rechazado', 'Rechazado'),
         ('no_encontrado', 'No encontrado')], 'Estado FE', copy=False)
    state_invoice_partner = fields.Selection(
        [('1', 'Aceptado'), ('3', 'Rechazado'), ('2', 'Aceptacion parcial')],
        'Respuesta del Cliente')
    reference_code_id = fields.Many2one(
        comodel_name="reference.code", string="Código de referencia",
        required=False, )
    payment_methods_id = fields.Many2one(
        comodel_name="payment.methods", string="Métodos de Pago",
        required=False, )
    invoice_id = fields.Many2one(
        comodel_name="account.invoice", string="Documento de referencia",
        required=False, copy=False)
    xml_respuesta_tributacion = fields.Binary(
        string="Respuesta Tributación XML", required=False, copy=False,
        attachment=True)
    fname_xml_respuesta_tributacion = fields.Char(
        string="Nombre de archivo XML Respuesta Tributación", required=False,
        copy=False)
    xml_comprobante = fields.Binary(
        string="Comprobante XML", required=False, copy=False, attachment=True)
    fname_xml_comprobante = fields.Char(
        string="Nombre de archivo Comprobante XML", required=False, copy=False,
        attachment=True)
    xml_supplier_approval = fields.Binary(
        string="XML Proveedor", required=False, copy=False, attachment=True)
    fname_xml_supplier_approval = fields.Char(
        string="Nombre de archivo Comprobante XML proveedor", required=False,
        copy=False, attachment=True)
    amount_tax_electronic_invoice = fields.Monetary(
        string='Total de impuestos FE', readonly=True,)
    amount_total_electronic_invoice = fields.Monetary(
        string='Total FE', readonly=True,)

    _sql_constraints = [
        ('number_electronic_uniq', 'unique (number_electronic)',
         "La clave de comprobante debe ser única"),
    ]

    @api.onchange('xml_supplier_approval')
    def _onchange_xml_supplier_approval(self):
        if self.xml_supplier_approval:
            root = ET.fromstring(re.sub(' xmlns="[^"]+"', '', base64.b64decode(self.xml_supplier_approval), count=1))#quita el namespace de los elementos
            if not root.findall('Clave'):
                return {'value': {'xml_supplier_approval': False},'warning': {'title': 'Atención','message': 'El archivo xml no contiene el nodo Clave. Por favor cargue un archivo con el formato correcto.'}}
            if not root.findall('FechaEmision'):
                return {'value': {'xml_supplier_approval': False},'warning': {'title': 'Atención','message': 'El archivo xml no contiene el nodo FechaEmision. Por favor cargue un archivo con el formato correcto.'}}
            if not root.findall('Emisor'):
                return {'value': {'xml_supplier_approval': False},'warning': {'title': 'Atención','message': 'El archivo xml no contiene el nodo Emisor. Por favor cargue un archivo con el formato correcto.'}}
            if not root.findall('Emisor')[0].findall('Identificacion'):
                return {'value': {'xml_supplier_approval': False},'warning': {'title': 'Atención','message': 'El archivo xml no contiene el nodo Identificacion. Por favor cargue un archivo con el formato correcto.'}}
            if not root.findall('Emisor')[0].findall('Identificacion')[0].findall('Tipo'):
                return {'value': {'xml_supplier_approval': False},'warning': {'title': 'Atención','message': 'El archivo xml no contiene el nodo Tipo. Por favor cargue un archivo con el formato correcto.'}}
            if not root.findall('Emisor')[0].findall('Identificacion')[0].findall('Numero'):
                return {'value': {'xml_supplier_approval': False},'warning': {'title': 'Atención','message': 'El archivo xml no contiene el nodo Numero. Por favor cargue un archivo con el formato correcto.'}}
            if not (root.findall('ResumenFactura') and root.findall('ResumenFactura')[0].findall('TotalImpuesto')):
                return {'value': {'xml_supplier_approval': False},'warning': {'title': 'Atención','message': 'No se puede localizar el nodo TotalImpuesto. Por favor cargue un archivo con el formato correcto.'}}
            if not (root.findall('ResumenFactura') and root.findall('ResumenFactura')[0].findall('TotalComprobante')):
                return {'value': {'xml_supplier_approval': False},'warning': {'title': 'Atención','message': 'No se puede localizar el nodo TotalComprobante. Por favor cargue un archivo con el formato correcto.'}}
            #self.fname_xml_supplier_approval = 'comrpobante_proveedor.xml'

    @api.multi
    def charge_xml_data(self):
        if self.xml_supplier_approval:
            root = ET.fromstring(re.sub(' xmlns="[^"]+"', '', base64.b64decode(self.xml_supplier_approval), count=1))#quita el namespace de los elementos
            self.number_electronic = root.findall('Clave')[0].text
            self.date_issuance = root.findall('FechaEmision')[0].text
            partner = self.env['res.partner'].search([('vat', '=', root.findall('Emisor')[0].find('Identificacion')[1].text)])
            if partner:
                self.partner_id = partner.id
            else:
                raise UserError('El proveedor con identificación '+root.findall('Emisor')[0].find('Identificacion')[1].text+' no existe. Por favor creelo primero en el sistema.')
            self.amount_tax_electronic_invoice = root.findall('ResumenFactura')[0].findall('TotalImpuesto')[0].text
            self.amount_total_electronic_invoice = root.findall('ResumenFactura')[0].findall('TotalComprobante')[0].text

    @api.multi
    def send_xml(self):
        for inv in self:
            if inv.xml_supplier_approval:
                root = ET.fromstring(re.sub(' xmlns="[^"]+"', '', base64.b64decode(inv.xml_supplier_approval), count=1))
                if not inv.state_invoice_partner:
                    raise UserError('Aviso!.\nDebe primero seleccionar el tipo de respuesta para el archivo cargado.')
                if float(root.findall('ResumenFactura')[0].findall('TotalComprobante')[0].text) == inv.amount_total:
                    if inv.company_id.frm_ws_ambiente != 'disabled' and inv.state_invoice_partner:
                        if inv.state_invoice_partner == '1':
                            detalle_mensaje = 'Aceptado'
                            tipo = 05
                        if inv.state_invoice_partner == '2':
                            detalle_mensaje = 'Aceptado parcial'
                            tipo = 06
                        if inv.state_invoice_partner == '3':
                            detalle_mensaje = 'Rechazado'
                            tipo = 07
                        payload = {
                            'clave': {
                                'tipo': tipo,
                                'sucursal': '1',#sucursal,#TODO
                                'terminal': '1',#terminal,
                                'numero_documento': root.findall('Clave')[0].text,
                                'numero_cedula_emisor': root.findall('Emisor')[0].find('Identificacion')[1].text,
                                'fecha_emision_doc': root.findall('FechaEmision')[0].text,
                                'mensaje': inv.state_invoice_partner,
                                'detalle_mensaje': detalle_mensaje,
                                'monto_total_impuesto': root.findall('ResumenFactura')[0].findall('TotalImpuesto')[0].text,
                                'total_factura': root.findall('ResumenFactura')[0].findall('TotalComprobante')[0].text,
                                'numero_cedula_receptor': inv.company_id.vat,
                                'num_consecutivo_receptor': inv.number[:20],
                                'emisor': {
                                    'identificacion': {
                                        'tipo': root.findall('Emisor')[0].findall('Identificacion')[0].findall('Tipo')[0].text,
                                        'numero': root.findall('Emisor')[0].findall('Identificacion')[0].findall('Numero')[0].text,
                                    },
                                },
                            },
                        }
                        headers = {
                            #'content-type': 'application/json',
                            #'authorization': "Bearer " + token['access_token'],
                        }
                        if inv.company_id.frm_ws_ambiente == 'stag':
                            requests_url = 'https://url_to_stag/accept_msg'
                        else:
                            requests_url = 'https://url_to_prod/accept_msg'
                        response_document = requests.post(requests_url,
                                                          headers=headers,
                                                          data=json.dumps(payload))
                        response_content = json.loads(response_document._content)

                        _logger.error('MAB - JSON DATA:%s', payload)
                        _logger.error('MAB - response:%s', response_content)

                        if response_content.get('code'):
                            if response_content.get('code') == 'XX':  #aprovado
                                inv.fname_xml_respuesta_tributacion = 'Respuesta_aprobacion' + inv.number + '.xml'
                                inv.xml_respuesta_tributacion = response_content.get('data')
                                inv.state_send_invoice = 'aceptado'
                            else:
                                raise UserError('Error con el comprobante: \n' + str(response_document._content))
                        if response_document.status_code == 'YY': #error
                            if response_document._content and response_document._content.split(',')[1][5:] == 'false':
                                raise UserError('Error con el comprobante: \n' + str(response_document._content))
                        else:
                            raise UserError('Error con el comprobante: \n'+str(response_document._content))
                else:
                    raise UserError('Error!.\nEl monto total de la factura no coincide con el monto total del archivo XML')


    @api.multi
    @api.returns('self')
    def refund(self, date_invoice=None, date=None, description=None, journal_id=None, invoice_id=None, reference_code_id=None):
        if self.env.user.company_id.frm_ws_ambiente == 'disabled':
            new_invoices = super(AccountInvoiceElectronic, self).refund()
            return new_invoices
        else:
            new_invoices = self.browse()
            for invoice in self:
                # create the new invoice
                values = self._prepare_refund(invoice, date_invoice=date_invoice, date=date,
                                              description=description, journal_id=journal_id)
                values.update({'invoice_id': invoice_id,
                               'reference_code_id': reference_code_id})
                refund_invoice = self.create(values)
                invoice_type = {
                    'out_invoice': ('customer invoices refund'),
                    'in_invoice': ('vendor bill refund')
                }
                message = _("This %s has been created from: <a href=# data-oe-model=account.invoice data-oe-id=%d>%s</a>") % (invoice_type[invoice.type], invoice.id, invoice.number)
                refund_invoice.message_post(body=message)
                new_invoices += refund_invoice
            return new_invoices

    @api.onchange('partner_id', 'company_id')
    def _onchange_partner_id(self):
        super(AccountInvoiceElectronic, self)._onchange_partner_id()
        self.payment_methods_id = self.partner_id.payment_methods_id

    @api.model
    def _consultahacienda(self):#cron
        invoices = self.env['account.invoice'].search([('type', 'in', ('out_invoice','out_refund')),('state', 'in', ('open', 'paid')),('number_electronic', '!=', False),('state_tributacion','=',False)])
        for i in invoices:
            if i.number_electronic and len(i.number_electronic) == 50:
                if i.company_id.frm_ws_ambiente == 'stag':
                    requests_url = 'https://url_to_stag/consultahacienda'
                else:
                    requests_url = 'https://url_to_prod/consultahacienda'
                payload = {
                    'clave': i.number_electronic,
                }
                headers = {
                    # 'content-type': 'application/json',
                    # 'authorization': "Bearer " + token['access_token'],
                }
                response_document = requests.post(requests_url,
                                                  headers=headers,
                                                  data=json.dumps(payload))
                response_content = json.loads(response_document._content)
                if response_content.get('code') == 33:
                    i.state_tributacion = 'no_encontrado'
                if response_content.get('hacienda_result'):
                    if response_content.get('hacienda_result').get('ind-estado'):
                        i.state_tributacion = response_content.get('hacienda_result').get('ind-estado')
                        i.fname_xml_respuesta_tributacion = 'respuesta_tributacion_' + i.number + '.xml'
                        i.xml_respuesta_tributacion = response_content.get('hacienda_result').get('respuesta-xml')

    @api.multi
    def action_invoice_open(self):
        super(AccountInvoiceElectronic, self).action_invoice_open()
        _logger.error('MAB - entrando action_invoice_open')
        for inv in self:
            if inv.company_id.frm_ws_ambiente != 'disabled':
                TipoDocumento = ''
                FacturaReferencia = ''
                now_utc = datetime.datetime.now(pytz.timezone('UTC'))
                now_cr = now_utc.astimezone(pytz.timezone('America/Costa_Rica'))
                date_cr = now_cr.strftime("%Y-%m-%dT%H:%M:%S-06:00")
                tipo_documento_referencia = ''
                numero_documento_referencia = ''
                fecha_emision_referencia = ''
                codigo_referencia = ''
                razon_referencia = ''
                medio_pago = inv.payment_methods_id.sequence or '01'
                if inv.type == 'out_invoice':#FC Y ND
                    if inv.invoice_id and inv.journal_id and inv.journal_id.nd:
                        TipoDocumento = '02'
                        tipo_documento_referencia = inv.invoice_id.number_electronic[29:31]#50625011800011436041700100001 01 0000000154112345678
                        numero_documento_referencia = inv.invoice_id.number_electronic
                        fecha_emision_referencia = inv.invoice_id.date_issuance
                        codigo_referencia = inv.reference_code_id.code
                        razon_referencia = inv.reference_code_id.name
                        medio_pago = ''
                    else:
                        TipoDocumento = '01'
                if inv.type == 'out_refund':#NC
                    if inv.invoice_id.journal_id.nd:
                        tipo_documento_referencia = '02'
                    else:
                        tipo_documento_referencia = '01'
                    TipoDocumento = '03'
                    numero_documento_referencia = inv.invoice_id.number_electronic
                    fecha_emision_referencia = inv.invoice_id.date_issuance
                    codigo_referencia = inv.reference_code_id.code
                    razon_referencia = inv.reference_code_id.name
                    if inv.origin and inv.origin.isdigit():
                        FacturaReferencia = (inv.origin)
                    else:
                        FacturaReferencia = 0
                if inv.payment_term_id:
                    if inv.payment_term_id.sale_conditions_id:
                        sale_conditions = inv.payment_term_id.sale_conditions_id.sequence or '01'
                    else:
                        raise UserError('No se pudo Crear la factura electrónica: \n Debe configurar condiciones de pago para %s',
                                        inv.payment_term_id.name)
                else:
                    sale_conditions = '01'

                if inv.number.isdigit() and TipoDocumento:
                    currency_rate = 1 / inv.currency_id.rate
                    lines = []
                    base_total = 0.0
                    numero = 0
                    if inv.partner_id.identification_id.code == '05':
                        receptor_identificacion = {
                            'tipo': False,
                            'numero': False,
                        }
                        receptor_identificacion_extranjero = inv.partner_id.vat
                    else:
                        receptor_identificacion = {
                            'tipo': inv.partner_id.identification_id.code,
                            'numero': inv.partner_id.vat,
                        }
                        receptor_identificacion_extranjero =''

                    totalserviciogravado = 0.0
                    totalservicioexento = 0.0
                    totalmercaderiagravado = 0.0
                    totalmercaderiaexento = 0.0
                    for inv_line in inv.invoice_line_ids:
                        impuestos_acumulados = 0.0
                        numero +=1
                        base_total += inv_line.price_unit * inv_line.quantity
                        impuestos = []
                        for i in inv_line.invoice_line_tax_ids:
                            if i.tax_code <> '00':
                                impuestos.append({
                                    'codigo': i.tax_code,
                                    'tarifa': i.amount,
                                    'monto': round(i.amount / 100 * inv_line.price_subtotal, 2),
                                })
                                impuestos_acumulados += round(i.amount / 100 * inv_line.price_subtotal, 2)
                        if inv_line.product_id:
                            if inv_line.product_id.type == 'service':
                                if impuestos_acumulados:
                                    totalserviciogravado += inv_line.quantity * inv_line.price_unit
                                else:
                                    totalservicioexento += inv_line.quantity * inv_line.price_unit
                            else:
                                if impuestos_acumulados:
                                    totalmercaderiagravado += inv_line.quantity * inv_line.price_unit
                                else:
                                    totalmercaderiaexento += inv_line.quantity * inv_line.price_unit
                        else:#se asume que si no tiene producto setrata como un type product
                            if impuestos_acumulados:
                                totalmercaderiagravado += inv_line.quantity * inv_line.price_unit
                            else:
                                totalmercaderiaexento += inv_line.quantity * inv_line.price_unit
                        line = {
                            'numero': numero,
                            'codigo': [{
                                'tipo': inv_line.product_id.code_type_id.code or '04',
                                'codigo': inv_line.product_id.default_code or '000',
                            }],
                            'cantidad': inv_line.quantity,
                            'unidad_medida': inv_line.uom_id.code or 'Sp',
                            'unidad_medida_comercial': inv_line.product_id.commercial_measurement,
                            'detalle': inv_line.name[:159],
                            'precio_unitario': inv_line.price_unit,
                            'monto_total': inv_line.quantity * inv_line.price_unit,
                            'descuento': (round(inv_line.quantity * inv_line.price_unit, 2) - round(inv_line.price_subtotal, 2)) or '',
                            'naturaleza_descuento': inv_line.discount_note,
                            'subtotal': inv_line.price_subtotal,
                            'impuestos': impuestos,
                            'montototallinea': inv_line.price_subtotal + impuestos_acumulados,
                        }
                        lines.append(line)
                    _logger.error('MAB - formando payload')
                    payload = {
                        'clave': {
                            'sucursal': '1',
                            'terminal': '1',
                            'tipo': TipoDocumento,
                            'comprobante': int(inv.number),
                            'pais': '506',
                            'dia': '%02d' % now_cr.day,
                            'mes': '%02d' % now_cr.month,
                            'anno': str(now_cr.year)[2:4],
                            'situacion_presentacion': '1',
                            'codigo_seguridad': inv.company_id.security_code,
                        },
                        'encabezado': {
                            'fecha': date_cr,
                            #'fecha': "2018-01-19T23:17:00+06:00",
                            'condicion_venta': sale_conditions,
                            'plazo_credito': '0',
                            'medio_pago': medio_pago
                        },
                        'emisor': {
                            'nombre': inv.company_id.name,
                            'identificacion': {
                                'tipo': inv.company_id.identification_id.code,
                                'numero': inv.company_id.vat,
                            },
                            'nombre_comercial': inv.company_id.commercial_name or '',
                            'ubicacion': {
                                'provincia': inv.company_id.state_id.code,
                                'canton': inv.company_id.county_id.code,
                                'distrito': inv.company_id.district_id.code,
                                'barrio': inv.company_id.neighborhood_id.code,
                                'sennas': inv.company_id.street,
                            },
                            'telefono': {
                                'cod_pais': inv.company_id.phone_code,
                                'numero': inv.company_id.phone,
                            },
                            'fax': {
                                'cod_pais': inv.company_id.fax_code,
                                'numero': inv.company_id.fax,
                            },
                            'correo_electronico': inv.company_id.email,
                        },
                        'receptor': {##
                            'nombre': inv.partner_id.name[:80],
                            'identificacion': receptor_identificacion,
                            'IdentificacionExtranjero': receptor_identificacion_extranjero,
                        },
                        'detalle': lines,
                        'resumen': {
                            'moneda': inv.currency_id.name,
                            'tipo_cambio': round(currency_rate, 5),
                            'totalserviciogravado': totalserviciogravado,
                            'totalservicioexento': totalservicioexento,
                            'totalmercaderiagravado': totalmercaderiagravado,
                            'totalmercaderiaexento': totalmercaderiaexento,
                            'totalgravado': totalserviciogravado + totalmercaderiagravado,
                            'totalexento': totalservicioexento + totalmercaderiaexento,
                            'totalventa': totalserviciogravado + totalmercaderiagravado + totalservicioexento + totalmercaderiaexento,
                            'totaldescuentos': round(base_total, 2) - round(inv.amount_untaxed, 2),
                            'totalventaneta': (totalserviciogravado + totalmercaderiagravado + totalservicioexento + totalmercaderiaexento) - (base_total - inv.amount_untaxed),
                            'totalimpuestos': inv.amount_tax,
                            'totalcomprobante': inv.amount_total,
                        },
                        'referencia':[{
                            'tipo_documento': tipo_documento_referencia,
                            'numero_documento': numero_documento_referencia,
                            'fecha_emision': fecha_emision_referencia,
                            'codigo': codigo_referencia,
                            'razon': razon_referencia,
                        }],
                        'otros': [{
                            'codigo': '',
                            'texto': '',
                            'contenido': ''
                        }],
                    }
                    headers = {
                        #'content-type': 'application/json',
                        #'authorization': "Bearer " + token['access_token'],
                    }
                    if inv.company_id.frm_ws_ambiente == 'stag':
                        requests_url = 'https://url_to_stag/makeXML'
                    else:
                        requests_url = 'https://url_to_prod/makeXML'
                    xdata = json.dumps(payload)
                    response_document = requests.post(requests_url,
                                                      headers=headers,
                                                      data=xdata)
                    _logger.error('MAB - JSON DATA:%s', xdata)
                    _logger.error('MAB - response:%s', response_document._content)
                    response_content = json.loads(response_document._content)
                    if response_content.get('code'):
                        if response_content.get('code') == 1:
                            inv.number_electronic = response_content.get('clave')
                            inv.date_issuance = date_cr
                        else:
                            raise UserError('No se pudo Crear la factura electrónica: \n' + str(response_document._content))
                    if response_document.status_code == 200:#TODO
                        if response_document._content:
                            #inv.electronic_invoice_return_message = response_document._content
                            inv.fname_xml_comprobante = 'comprobante_' + inv.number + '.xml'
                            inv.xml_comprobante = response_content.get('data')
                            if not inv.partner_id.opt_out:
                                email_template = self.env.ref('account.email_template_edi_invoice', False)
                                attachment = self.env['ir.attachment'].search([('res_model','=','account.invoice'),('res_id','=',inv.id),('res_field','=','xml_comprobante')], limit=1)
                                attachment.name = inv.fname_xml_comprobante
                                attachment.datas_fname = inv.fname_xml_comprobante
                                email_template.attachment_ids = [(6,0,[attachment.id])] # [(4, attachment.id)]
                                email_template.with_context(type='binary', default_type='binary').send_mail(inv.id, raise_exception=False, force_send=True)#default_type='binary'
                                email_template.attachment_ids = [(3, attachment.id)]
                            if response_document._content.split(',')[1][5:] == 'false':
                                raise UserError('No se pudo Crear la factura electrónica: \n' + str(response_document._content))
                    else:
                        raise UserError('No se pudo Crear la factura electrónica: \n'+str(response_document._content))
                        #inv.electronic_invoice_return_message = response_document._content
