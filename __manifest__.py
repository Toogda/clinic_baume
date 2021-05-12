# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    'name' : 'clinic_baume',
    'version' : '1.2',
    'summary': 'Gestion des cliniques',
    'sequence': 100,
    'description': """
Gestion des cliniques
====================
    """,
    'category': 'Accounting',
    'author': 'HSN Consult',
    'website': 'http://www.hsnconsult.com',
    'depends': ['account','point_of_sale',],
    'data': [
        'data/ir_sequence_data.xml',
        'security/clinic_security.xml',
        'report_views/report_recucaisse.xml',
        'report_views/report_recucaisse_duplicata.xml',
        'report_views/report_recurecettegarde.xml',
        'report_views/report_recucaution.xml',
        'report_views/report_recureghospi.xml',
        'report_views/report_transfert.xml',
        #'report_views/report_etatjour.xml',
        #'report_views/report_etatjourbis.xml',
        'report_views/report_etatcloture.xml',
        #'report_views/report_resultatlab.xml',
        'report_views/report_facture.xml',
        'report_views/report_factureko.xml',
        'report_views/report_factureko_proforma.xml',
        'report_views/report_factureas.xml',
        'report_views/clinic_report.xml',
        'views/clinic_view.xml',
        'views/facture_hospi.xml',
        'views/pos_view.xml',
        'security/ir.model.access.csv',
        ],
    'installable': True,
    'application': True,
    'auto_install': False
}
