# -*- coding: utf-8 -*-
# ajout des fonctionaites sur la facturation des hospitalisation

import logging
from datetime import timedelta
from datetime import datetime
from functools import partial
from odoo.osv import expression
import pytz

from odoo import api, fields, models, tools, _
from odoo.tools import float_is_zero
from odoo.exceptions import UserError
from odoo.http import request
from odoo.addons import decimal_precision as dp
from odoo.tools.enlettres import convlettres

class clinic_factureko(models.Model):
    _name = "clinic.factureko"
    _description = "factureko"
        
    def mtlettre(self,montant):
        return convlettres(montant)
    
    def validef(self):
        if ((self.montantass > 0 or self.remise > 0 or self.montantpatient > 0) and self.montant > 0) :
            self.write({'state':'valide'})
    
    def semi_valider(self):            
        company_id = self.env.user.company_id
        for frais in self:
            if frais.name == '':
                if len(frais.idassurance) == 0:
                    frais.name = company_id.sequenceFactNonAssurer.next_by_id()
                elif len(frais.idassurance) > 0:
                    frais.name = company_id.sequenceFactAssurer.next_by_id()       
        self.write({'state':'proforma'})
    
    def brouillon(self):            
        self.write({'state':'brouillon'})
                
    @api.depends('ligne_factureko.montant','ligne_factureko.montantpatient','ligne_factureko.montantass','remise', 'montantass')            
    def get_montant(self):
        for record in self:
            montant = montantpatient = montantass = 0
            for recordfil in record.ligne_factureko:
                montant = montant + recordfil.montant
                montantpatient = montantpatient + recordfil.montantpatient
                # montantass = montantass + recordfil.montantass
            record.montant = montant
            record.montantpatient = record.montant - record.montantass - record.remise
            # record.montantass = montantass

    def aannuler(self):
        self.write({'state':'aannuler'})
    def annuler(self):
        self.write({'state':'annule'})
        
    @api.depends('idpatient') 
    def get_assurance(self):
        for record in self:
            record.idassurance = record.idpatient.idassurance.id
            record.idsociete = record.idpatient.idsociete.id

    @api.multi
    def create_line(self):
        for line in self:
            if line.state == 'brouillon':
                tab = ["Acte Opératoire", "Consommable", "Viste médecin", "Soins infirmiers", "Produits hospitaliers", "Chambre"]
                for rec in tab:
                    for record in self.env['product.template'].search([('name', 'like', rec)])[0]:
                        if rec == "Acte Opératoire": 
                            line.ligne_factureko.create({
                                'idfacture': line.id,
                                'idarticle': record.id,
                                'qte': 1,
                                'pu': line.ko * line.valeur_ko * line.coeff,
                                'montant': line.ko * line.valeur_ko * line.coeff,
                            })
                        else: 
                            line.ligne_factureko.create({
                                'idfacture': line.id,
                                'idarticle': record.id,
                                'qte': 1,
                                'pu': record.list_price,
                                'montant': record.list_price,
                            })
            else: 
                raise UserError(_("Cet Objet est modifiable uniquement à l'état Brouillon."))
        
            
    idpatient = fields.Many2one('clinic.patient', string='Patient', required=True)
    date = fields.Date('Date', required=True, default=fields.Date.today)
    idmedecin = fields.Many2one('clinic.medecin', string='Medecin')
    idarticle = fields.Many2one('product.template', string='Article', required=True)
    name = fields.Char('Référence',copy=False, readonly=True, index=True, default='')
    montant = fields.Float('Montant', compute='get_montant', store=True,digits=(16,0))
    montantpatient = fields.Float('Part Patient Net', compute='get_montant', store=True,digits=(16,0))
    montantass = fields.Float('Part Assurance', digits=(16,0))
    remise = fields.Float('Remise',digits=(16,0))
    idassurance = fields.Many2one('clinic.assurance', string='Assurance', compute='get_assurance', store=True)
    idsociete = fields.Many2one('clinic.societe', string='Sociéte', compute='get_assurance', store=True)
    etatfact = fields.Selection([('facture','Facturée'),('afacturer','Non facturée')], string='Etat Facture', default = 'afacturer')
    ligne_factureko = fields.One2many('clinic.factureko.ligne','idfacture','Facture')
    
    ko = fields.Float('K.O', digits=(16,0))
    valeur_ko = fields.Float('Valeur K.O', digits=(16,0))
    coeff = fields.Float('Coef~3..', digits=(16,0))
    
    state = fields.Selection([
        ('brouillon','Brouillon'),
        ('proforma','Proforma'),
        ('valide','Validé'),
        ('aannuler','A annuler'),
        ('annule','Annulé'),
        ('reglep','Réglée patient'),
        ('reglea','Réglée assurance'),
        ('reglee','Réglée')
        ], 
        string='Etat', size=64, default='brouillon' ,track_visibility='onchange', readonly=True, required=True
    )
    

class clinic_factureko_ligne(models.Model):
    _name = "clinic.factureko.ligne"
    _description = "ligne factureko"

    @api.depends('ko', 'valeur_ko', 'coeff', 'qte','pu','plafond')
    def get_montantl(self):
        for record in self:
            taux = self.env['clinic.tauxass'].search([('idpatient','=',record.idfacture.idpatient.id),('categorie','=', record.idarticle.categ_id.id)]).taux/100
            if record.ko > 0:
                record.pu = record.ko * record.valeur_ko * record.coeff
                record.montant = record.qte * record.pu
                if record.idfacture.idpatient.idassurance.name != '':
                    record.montantass = record.qte * record.pu * taux
                    record.montantpatient = record.montant -  record.montantass
            else :
                record.montant = record.qte * record.pu
                if record.idfacture.idpatient.idassurance.name != '':
                    # raise UserError(_(taux))
                    record.montantass = record.montant * taux
                    record.montantpatient = record.montant -  record.montantass
                else: 
                    record.montantass = 0
                    record.montantpatient = record.montant


    @api.onchange('idarticle')
    def onchange_idarticle(self):
        for rec in self:
            lp = 0
            for record in rec.idarticle.item_ids:
                if record.pricelist_id == rec.idfacture.idassurance.pricelist_id:
                   rec.plafond = record.plafond 
                   rec.pu = record.fixed_price
                   lp = 1
            if lp == 0 :
               if rec.idfacture.idpatient.type == 'national':
                  rec.plafond = rec.idarticle.list_price
                  rec.pu = rec.idarticle.list_price                 
               else:
                  rec.plafond = rec.idarticle.standard_price 
                  rec.pu = rec.idarticle.standard_price

    @api.depends('pu', 'qte')
    def get_montant(self):
        for rec in self:
            rec.montant = rec.pu * rec.qte
        # if self.idarticle.available_in_pos:
        #    for recf in self:
        #        recf.plafond = recf.pu
        #    return 
        # for rec in self:
        #     lp = 0
        #     for record in rec.idarticle.item_ids:
        #         if record.pricelist_id == rec.idfacture.idassurance.pricelist_id:
        #            rec.plafond = record.plafond 
        #            rec.pu = record.fixed_price
        #            lp = 1
        #     if lp == 0 :
        #        if rec.idfacture.idpatient.type == 'national':
        #           rec.plafond = rec.idarticle.list_price 
        #           rec.pu = rec.idarticle.list_price
        #        else:
        #           rec.plafond = rec.idarticle.standard_price 
        #           rec.pu = rec.idarticle.standard_price
    
    idfacture = fields.Many2one('clinic.factureko', string='Facture', required=True)
    idarticle = fields.Many2one('product.template', string='Article', required=True)
    ko = fields.Float('K.O', digits=(16,0)) #-----------------
    valeur_ko = fields.Float('Valeur K.O', digits=(16,0)) #-----------------
    coeff = fields.Float('Coef~3..', digits=(16,0)) #-----------------
    pu = fields.Float('Prix unitaire', default=1.0, required=True, digits=(16,0))
    qte = fields.Float('Quantité', required=True, default=1.0, digits=(16,0))
    plafond = fields.Float('Prix plafond', digits=(16,0)) #-----------------
    montantass = fields.Float('Montant assurance', compute='get_montant',digits=(16,0)) #-----------------
    montantpatient = fields.Float('Montant patient', compute='get_montant',digits=(16,0)) #-----------------
    montant = fields.Float('Montant', compute="get_montant", digits=(16,0))