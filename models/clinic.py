# -*- coding: utf-8 -*-

import logging
from datetime import timedelta
from datetime import datetime
from functools import partial
from odoo.osv import expression

import psycopg2
import pytz

from odoo import api, fields, models, tools, _
from odoo.tools import float_is_zero
from odoo.exceptions import UserError
from odoo.http import request
from odoo.addons import decimal_precision as dp
from odoo.tools.enlettres import convlettres

    

class PricelistItem(models.Model):
    _name = "product.pricelist.item"
    _description = "Pricelist Item"
    _inherit = "product.pricelist.item"

    plafond = fields.Float('Plafond', digits=dp.get_precision('Product Price'))

class ProductCategory(models.Model):
    _name = "product.category"
    _description = "Catégorie"
    _inherit = "product.category"

    code = fields.Char('Code')
class clinic_tauxass(models.Model):
    _name = "clinic.tauxass"
    _description = "Taux assurance"
        
    idpatient = fields.Many2one('clinic.patient', string='Assurance', required=True)
    categorie = fields.Many2one('product.category', string='Categorie', required=True)
    taux = fields.Float('Taux assurance(%)', required=True)

class Company(models.Model):
    _name = "res.company"
    _description = 'Companies'
    _inherit = "res.company"

    def compute_amount_text(self,montant):
        return convlettres(montant)

    def mtlettre(self,montant):
        return convlettres(montant)
    
    sequencecaisse = fields.Many2one('ir.sequence',string='Séquence caisse')
    sequencecaution = fields.Many2one('ir.sequence',string='Séquence caution')
    sequencerel = fields.Many2one('ir.sequence',string='Séquence Relevé')
    sequencetransfert = fields.Many2one('ir.sequence',string='Séquence Transfert')
    sequencerecette = fields.Many2one('ir.sequence',string='Séquence recettegarde')
    sequencefacture = fields.Many2one('ir.sequence',string='Séquence Facture')
    sequenceFactNonAssurer = fields.Many2one('ir.sequence',string='Séquence Facture Nom Assurée')
    sequenceFactAssurer = fields.Many2one('ir.sequence',string='Séquence Facture Assurée')
    tauxPersonnel = fields.Float('Taux Personnel (%)', digits=(16,0))



class clinic_societe(models.Model):
    _name = "clinic.societe"
    _description = "Societe"
        
    name = fields.Char('Société', required=True)
    idassurance = fields.Many2one('clinic.assurance', 'Assurance', required=True)

class clinic_assurance(models.Model):
    _name = "clinic.assurance"
    _description = "Assurance"
        
    name = fields.Char('Assurance', required=True)
    adresse = fields.Char('Adresse')
    phone = fields.Char('Téléphone')
    ifu = fields.Char('IFU')
    rccm = fields.Char('RCCM')
    regime = fields.Char('Régime fiscal')
    division = fields.Char('Division fiscale')
    pricelist_id = fields.Many2one('product.pricelist', 'Liste de prix')

class clinic_patient(models.Model):
    _name='clinic.patient'

    MARITAL_STATUS = [
        ('celibataire', 'Célibataire'),
        ('marie', 'Marié'),
        ('veuf', 'Veuf(ve)'),
        ('divorce', 'Divorcé'),
    ]

    SEX = [
        ('homme', 'Homme'),
        ('femme', 'Femme'),
    ]

    BLOOD_TYPE = [
        ('A', 'A'),
        ('B', 'B'),
        ('AB', 'AB'),
        ('O', 'O'),
    ]

    RH = [
        ('+','+'),
        ('-','-'),
    ]


    @api.multi
    def _patient_age(self):
        def compute_age_from_dates(patient_dob, patient_deceased, patient_dod):
            now = datetime.now()
            if (patient_dob):
                dob = datetime.strptime(patient_dob.strftime('%Y-%m-%d'), '%Y-%m-%d')
                if patient_deceased:
                    dod = datetime.strptime(patient_dod.strftime('%Y-%m-%d'), '%Y-%m-%d')
                    delta = dod - dob
                    deceased = " (décédé)"
                    years_months_days = str(delta.days // 365) + " ans " + str(delta.days % 365) + " jours" + deceased
                else:
                    delta = now - dob
                    years_months_days = str(delta.days // 365) + " ans " + str(delta.days % 365) + " jours"
            else:
                years_months_days = "NA !"

            return years_months_days

        for patient_data in self:
            patient_data.age = compute_age_from_dates(patient_data.dob, patient_data.deceased, patient_data.dod)
        return True

    @api.multi
    def name_get(self):
        result = []
        for record in self:
            name = record.nom
            result.append((record.id, name))
        return result
    @api.model
    def name_search(self, name, args=None, operator='ilike', limit=100):
        args = args or []
        recs = self.browse()
        if name:
            recs = self.search(['|',('name', 'ilike', name),('nom', 'ilike', name)] + args, limit=limit)
            #raise ValidationError(recs)
        return recs.name_get()


    @api.onchange('idassurance')
    def onchange_name(self):
        values = {}
        self.ligne_taux=''
        #if not self.idassurance :
        values = self.onchange_name_values()
        return values


    @api.multi
    def onchange_name_values(self):
        categ_ids =[]
        res = {}
        #defaults
        res = {'value':{
                'ligne_taux':[],
            }
        }

        # Recuperation des categories
        query = _("select id from product_category")
        self.env.cr.execute(query)
        vals = self.env.cr.fetchall()
        if vals:
            for va in vals:
                specs = {
                          'categorie': va[0],
                        }
                categ_ids += [specs]

        res['value'].update({
            'ligne_taux': categ_ids,
        })
        return res
    name = fields.Char('ID', default='Nouveau')
    image = fields.Binary('image')
    dob = fields.Date(string='Date de naissance')
    age = fields.Char(compute=_patient_age, size=32, string='Age' )
    sex = fields.Selection(SEX, string='Genre', index=True)
    marital_status = fields.Selection(MARITAL_STATUS, string='Statut matrimonial')
    blood_type = fields.Selection(BLOOD_TYPE, string='Groupe sanguin')
    rh = fields.Selection(RH, string='Rh')
    critical_info = fields.Text(string='Maladies connues ou allergies')
    general_info = fields.Text(string='Informations générales')
    deceased = fields.Boolean(string='Patient Décédé ?')
    dod = fields.Date(string='Date de décès')
    cod = fields.Char(string='Cause du décès')

    nom = fields.Char('Nom', required=True)
    prenom = fields.Char('Prénoms')
    phone = fields.Char('Téléphone')
    adresse = fields.Char('Adresse')
    est_un_personnel = fields.Boolean(string="Personnel de la clinique", default=False)
    type = fields.Selection([('national','National'),('expatrie','Expatrié')], string='Type de patient', default='national')
    profession = fields.Char('Profession')
    idsociete = fields.Many2one('clinic.societe',string='Société')
    lieunaiss = fields.Char('Lieu de naissance')
    idassurance = fields.Many2one('clinic.assurance',string='Assurance')
    numass = fields.Char('N° Carte assurance')
    dateexp = fields.Date('Date expiration assurance')
    ligne_taux = fields.One2many('clinic.tauxass','idpatient','taux')
    

    @api.model
    def create(self, vals):
        sequence = self.env['ir.sequence'].next_by_code('clinic.patient')
        vals['name'] = sequence
        health_patient = super(clinic_patient, self).create(vals)
        return health_patient

class clinic_opcaisse(models.Model):
    _name = "clinic.opcaisse"
    _description = "Operations de caisse"

    def mtlettre(self,montant):
        return convlettres(montant)
    
    def validef(self):
        if self.idpatient.idassurance and self.idpatient.dateexp >= self.date:
           if not self.numficheas and self.montantass !=0 : 
              raise UserError(_("Vous devez entrer le numero de la fiche d\'assurance"))
        if self.montantpatient < 0 :
           raise UserError("Revoir la remise!") 
            
        company_id = self.env.user.company_id
        for frais in self:
            if frais.name == '':
                frais.name = company_id.sequencecaisse.next_by_id()
        self.write({'state':'valide'})
        self.calcule_cash()
        return {
        'context': self.env.context,
        'view_type': 'form',
        'view_mode': 'form',
        'res_model': 'clinic.opcaisse',
        'res_id': self.id,
        'view_id': False,
        'type': 'ir.actions.act_window',
        'target': 'new',
    }

    def calcule_cash(self):
        bank_statements = [session.statement_ids for session in self.idopcaisse if session.statement_ids]
        if not bank_statements:
                raise UserError(_("There is no cash register for this PoS Session"))
        for box in self:
            for record in bank_statements[0]:
                if not record.journal_id:
                    raise UserError(_("Please check that the field 'Journal' is set on the Bank Statement"))
                if not record.journal_id.company_id.transfer_account_id:
                    raise UserError(_("Please check that the field 'Transfer Account' is set on the company."))
                box.idopcaisse._create_bank_statement_line(record,self.montantpatient,self.idpatient.nom,None,box.name)
                
    @api.depends('ligne_opcaisse.montant','ligne_opcaisse.montantpatient','ligne_opcaisse.montantass','remise')            
    def get_montant(self):
        for record in self:
            montant = montantpatient = montantass = 0
            for recordfil in record.ligne_opcaisse:
                montant = montant + recordfil.montant
                montantpatient = montantpatient + recordfil.montantpatient
                montantass = montantass + recordfil.montantass
            record.montant = montant
            record.montantpatient = montantpatient - record.remise
            record.montantass = montantass
            

    def get_dateop(self):
        return fields.Date.to_string(datetime.now())

    def aannuler(self):
        self.write({'state':'aannuler'})
        return {
        'context': self.env.context,
        'view_type': 'form',
        'view_mode': 'form',
        'res_model': 'clinic.opcaisse',
        'res_id': self.id,
        'view_id': False,
        'type': 'ir.actions.act_window',
        'target': 'new',
    }
    def annuler(self):
        self.calcule_cash_annul()
        self.write({'state':'annule'})
        return {
        'context': self.env.context,
        'view_type': 'form',
        'view_mode': 'form',
        'res_model': 'clinic.opcaisse',
        'res_id': self.id,
        'view_id': False,
        'type': 'ir.actions.act_window',
        'target': 'new',
    }
        
    @api.depends('idpatient') 
    def get_assurance(self):
        for record in self:
            record.idassurance = record.idpatient.idassurance.id
            record.idsociete = record.idpatient.idsociete.id
    def calcule_cash_annul(self):
        bank_statements = [session.statement_ids for session in self.idopcaisse if session.statement_ids]
        if not bank_statements:
                raise UserError(_("There is no cash register for this PoS Session"))
        for box in self:
            for record in bank_statements[0]:
                if not record.journal_id:
                    raise UserError(_("Please check that the field 'Journal' is set on the Bank Statement"))
                if not record.journal_id.company_id.transfer_account_id:
                    raise UserError(_("Please check that the field 'Transfer Account' is set on the company."))
                box.idopcaisse._create_bank_statement_line(record,self.montantpatient*-1,'Annulation '+self.name,None,box.name)
    def revenir(self):
        self.write({'state':'valide'})
        return {
        'context': self.env.context,
        'view_type': 'form',
        'view_mode': 'form',
        'res_model': 'clinic.opcaisse',
        'res_id': self.id,
        'view_id': False,
        'type': 'ir.actions.act_window',
        'target': 'new',
    }
    idopcaisse = fields.Many2one('pos.session', string='op caisse', required=True)
    idpatient = fields.Many2one('clinic.patient', string='Patient', required=True)
    date = fields.Date('Date', required=True, default=get_dateop, readonly=True)
    name = fields.Char('Référence',copy=False, readonly=True, index=True, default='')
    montant = fields.Float('Montant', compute='get_montant', store=True,digits=(16,0))
    montantpatient = fields.Float('Part Patient Net', compute='get_montant', store=True,digits=(16,0))
    montantass = fields.Float('Part Assurance', compute='get_montant', store=True,digits=(16,0))
    remise = fields.Float('Remise', digits=(16,0))
    
    idassurance = fields.Many2one('clinic.assurance', string='Assurance', compute='get_assurance', store=True)
    idsociete = fields.Many2one('clinic.societe', string='Sociéte', compute='get_assurance', store=True)
    numficheas = fields.Char('N° Fiche assurance')
    etatfact = fields.Selection([('facture','Facturée'),('afacturer','Non facturée')], string='Etat Facture', default = 'afacturer')
    ligne_opcaisse = fields.One2many('clinic.opcaisse.ligne','idopcaisse', string='Lignes operations caisse')
    state = fields.Selection([('brouillon','Brouillon'),('valide','Validé'),('aannuler','A annuler'),('annule','Annulé')], string='Etat', size=64, default='brouillon' ,track_visibility='onchange', readonly=True, required=True)


    
class clinic_opcaisse_ligne(models.Model):
    _name = "clinic.opcaisse.ligne"
    _description = "Lignes Operations de caisse"
   
    @api.depends('qte','pu')
    def get_montantl(self):
        for record in self:
            taux = self.env['clinic.tauxass'].search([('idpatient','=',record.idopcaisse.idpatient.id),('categorie','=',record.idarticle.categ_id.id)]).taux/100
            #record.montant = record.qte * record.pu
            #record.montantass = record.qte * record.pu * taux
            #record.montantpatient = record.qte * record.pu * (1-taux)
            if record.idarticle.standard_price != 0 and record.idopcaisse.idpatient.idassurance.name == 'MAADO':
               #raise UserError("ok")
               record.montant = record.qte * record.pu
               record.montantass = record.qte * record.idarticle.standard_price
               record.montantpatient = record.qte * (record.pu - record.idarticle.standard_price)
            else :
               #raise UserError("ok2")
               record.montant = record.qte * record.pu
               record.montantass = record.qte * record.plafond * taux
               record.montantpatient = record.qte * (record.pu - record.plafond * taux )

    @api.onchange('idarticle')
    def onchange_idarticle(self):
        for rec in self:
            lp = 0
            for record in rec.idarticle.item_ids:
                if record.pricelist_id == rec.idopcaisse.idassurance.pricelist_id:
                   rec.plafond = record.plafond 
                   rec.pu = record.fixed_price
                   lp = 1
            if lp == 0 :
               if rec.idopcaisse.idpatient.type == 'national':
                  rec.plafond = rec.idarticle.list_price
                  rec.pu = rec.idarticle.list_price                 
               else:
                  rec.plafond = rec.idarticle.standard_price 
                  rec.pu = rec.idarticle.standard_price

    @api.onchange('pu')
    def onchange_pu(self):
        for rec in self:
            lp = 0
            for record in rec.idarticle.item_ids:
                if record.pricelist_id == rec.idopcaisse.idassurance.pricelist_id:
                   rec.plafond = record.plafond 
                   rec.pu = record.fixed_price
                   lp = 1
            if lp == 0 :
               if rec.idopcaisse.idpatient.type == 'national':
                  rec.plafond = rec.idarticle.list_price 
                  rec.pu = rec.idarticle.list_price
               else:
                  rec.plafond = rec.idarticle.standard_price 
                  rec.pu = rec.idarticle.standard_price
                  
            
    idopcaisse = fields.Many2one('clinic.opcaisse', string='Operation de caisse', required=True)
    idarticle = fields.Many2one('product.template', string='Article', required=True)
    idmedecin = fields.Many2one('clinic.medecin', string='Medecin')
    categorie = fields.Many2one('product.category', string='categorie', related='idarticle.categ_id', store=True)
    qte = fields.Float('Quantité', required=True, default=1.0,digits=(16,0))
    pu = fields.Float('Prix unitaire', required=True,digits=(16,0))
    plafond = fields.Float('Prix plafond', required=True,digits=(16,0))
    montant = fields.Float('Montant', compute='get_montantl',digits=(16,0), store=True)
    montantass = fields.Float('Montant assurance', compute='get_montantl',digits=(16,0), store=True)
    montantpatient = fields.Float('Montant patient', compute='get_montantl',digits=(16,0), store=True)

class clinic_caution(models.Model):
    _name = "clinic.caution"
    _description = "Caution"

    def mtlettre(self,montant):
        return convlettres(montant)
    def validef(self):
        company_id = self.env.user.company_id
        for frais in self:
            if frais.name == '':
                frais.name = company_id.sequencecaution.next_by_id()
        self.write({'state':'valide'})
        self.calcule_cash()
        return {
        'context': self.env.context,
        'view_type': 'form',
        'view_mode': 'form',
        'res_model': 'clinic.caution',
        'res_id': self.id,
        'view_id': False,
        'type': 'ir.actions.act_window',
        'target': 'new',
    }

    def calcule_cash(self):
        bank_statements = [session.statement_ids for session in self.idcaution if session.statement_ids]
        if not bank_statements:
                raise UserError(_("There is no cash register for this PoS Session"))
        for box in self:
            for record in bank_statements[0]:
                if not record.journal_id:
                    raise UserError(_("Please check that the field 'Journal' is set on the Bank Statement"))
                if not record.journal_id.company_id.transfer_account_id:
                    raise UserError(_("Please check that the field 'Transfer Account' is set on the company."))
                box.idcaution._create_bank_statement_line(record,self.montant,'Caution',None,None)
    def get_dateop(self):
        return fields.Date.to_string(datetime.now())
    def aannuler(self):
        self.write({'state':'aannuler'})
        return {
        'context': self.env.context,
        'view_type': 'form',
        'view_mode': 'form',
        'res_model': 'clinic.caution',
        'res_id': self.id,
        'view_id': False,
        'type': 'ir.actions.act_window',
        'target': 'new',
    }
    def annuler(self):
        self.calcule_cash_annul()
        self.write({'state':'annule'})
        return {
        'context': self.env.context,
        'view_type': 'form',
        'view_mode': 'form',
        'res_model': 'clinic.caution',
        'res_id': self.id,
        'view_id': False,
        'type': 'ir.actions.act_window',
        'target': 'new',
    }
    def calcule_cash_annul(self):
        bank_statements = [session.statement_ids for session in self.idcaution if session.statement_ids]
        if not bank_statements:
                raise UserError(_("There is no cash register for this PoS Session"))
        for box in self:
            for record in bank_statements[0]:
                if not record.journal_id:
                    raise UserError(_("Please check that the field 'Journal' is set on the Bank Statement"))
                if not record.journal_id.company_id.transfer_account_id:
                    raise UserError(_("Please check that the field 'Transfer Account' is set on the company."))
                box.idcaution._create_bank_statement_line(record,self.montant*-1,'Annulation Caution '+self.name,None,None)
    def revenir(self):
        self.write({'state':'valide'})
        return {
        'context': self.env.context,
        'view_type': 'form',
        'view_mode': 'form',
        'res_model': 'clinic.caution',
        'res_id': self.id,
        'view_id': False,
        'type': 'ir.actions.act_window',
        'target': 'new',
    }
    idcaution = fields.Many2one('pos.session', string='Caution', required=True)
    name = fields.Char('Référence',copy=False, readonly=True, index=True, default='')
    idpatient = fields.Many2one('clinic.patient', string='Patient', required=True)
    date = fields.Date('Date', required=True, default=get_dateop, readonly=True)
    objet = fields.Char('Objet', required=True)
    montant = fields.Float('Montant versé', required = True,digits=(16,0))
    state = fields.Selection([('brouillon','Brouillon'),('valide','Validée'),('solde','Soldée'),('aannuler','A annuler'),('annule','Annulé')], string='Etat', size=64, default='brouillon' ,track_visibility='onchange', readonly=True, required=True)

class clinic_recettegarde(models.Model):
    _name = "clinic.recettegarde"
    _description = "Recette garde"
    
    def validef(self):
        company_id = self.env.user.company_id
        for frais in self:
            if frais.name == '':
                frais.name = company_id.sequencerecette.next_by_id()
        for frais in self:
            self.write({'state':'valide'})
            self.calcule_cash()
        return {
        'context': self.env.context,
        'view_type': 'form',
        'view_mode': 'form',
        'res_model': 'clinic.recettegarde',
        'res_id': self.id,
        'view_id': False,
        'type': 'ir.actions.act_window',
        'target': 'new',
    }

    def calcule_cash(self):
        bank_statements = [session.statement_ids for session in self.idrecettegarde if session.statement_ids]
        if not bank_statements:
                raise UserError(_("There is no cash register for this PoS Session"))
        for box in self:
            for record in bank_statements[0]:
                if not record.journal_id:
                    raise UserError(_("Please check that the field 'Journal' is set on the Bank Statement"))
                if not record.journal_id.company_id.transfer_account_id:
                    raise UserError(_("Please check that the field 'Transfer Account' is set on the company."))
                box.idrecettegarde._create_bank_statement_line(record,self.montant,'Recette garde',None,None)
    def get_dateop(self):
        return fields.Date.to_string(datetime.now())
    def aannuler(self):
        self.write({'state':'aannuler'})
        return {
        'context': self.env.context,
        'view_type': 'form',
        'view_mode': 'form',
        'res_model': 'clinic.recettegarde',
        'res_id': self.id,
        'view_id': False,
        'type': 'ir.actions.act_window',
        'target': 'new',
    }
    def annuler(self):
        self.calcule_cash_annul()
        self.write({'state':'annule'})
        return {
        'context': self.env.context,
        'view_type': 'form',
        'view_mode': 'form',
        'res_model': 'clinic.recettegarde',
        'res_id': self.id,
        'view_id': False,
        'type': 'ir.actions.act_window',
        'target': 'new',
    }
    def calcule_cash_annul(self):
        bank_statements = [session.statement_ids for session in self.idrecettegarde if session.statement_ids]
        if not bank_statements:
                raise UserError(_("There is no cash register for this PoS Session"))
        for box in self:
            for record in bank_statements[0]:
                if not record.journal_id:
                    raise UserError(_("Please check that the field 'Journal' is set on the Bank Statement"))
                if not record.journal_id.company_id.transfer_account_id:
                    raise UserError(_("Please check that the field 'Transfer Account' is set on the company."))
                box.idrecettegarde._create_bank_statement_line(record,self.montant*-1,'Annulation Recette garde '+self.name,None,None)
    def revenir(self):
        self.write({'state':'valide'})
        return {
        'context': self.env.context,
        'view_type': 'form',
        'view_mode': 'form',
        'res_model': 'clinic.recettegarde',
        'res_id': self.id,
        'view_id': False,
        'type': 'ir.actions.act_window',
        'target': 'new',
    }
    idrecettegarde = fields.Many2one('pos.session', string='Recette garde', required=True)
    date = fields.Date('Date', required=True, default=get_dateop, readonly=True)
    name = fields.Char('Référence',copy=False, readonly=True, index=True, default='')
    montant = fields.Float('Montant reçu', required = True,digits=(16,0))
    deposant = fields.Char('Déposant', required = True)
    receptionniste = fields.Char('Réceptionniste', required = True)
    state = fields.Selection([('brouillon','Brouillon'),('valide','Validé'),('aannuler','A annuler'),('annule','Annulé')], string='Etat', size=64, default='brouillon' ,track_visibility='onchange', readonly=True, required=True)


#Factures
class clinic_facture(models.Model):
    _name = "clinic.facture"
    _description = "Factures"

    def mtlettre(self,montant):
        return convlettres(montant)
    
    def validef(self):            
        company_id = self.env.user.company_id
        for frais in self:
            if frais.name == '':
                if len(frais.idassurance) == 0:
                    frais.name = company_id.sequenceFactNonAssurer.next_by_id()
                elif len(frais.idassurance) > 0:
                    frais.name = company_id.sequenceFactAssurer.next_by_id()       
        self.write({'state':'valide'})
    
    def brouillon(self):            
        self.write({'state':'brouillon'})
                
    @api.depends('ligne_facture.montant','ligne_facture.montantpatient','ligne_facture.montantass','remise')            
    def get_montant(self):
        for record in self:
            montant = montantpatient = montantass = 0
            for recordfil in record.ligne_facture:
                montant = montant + recordfil.montant
                montantpatient = montantpatient + recordfil.montantpatient
                montantass = montantass + recordfil.montantass
            record.montant = montant
            record.montantpatient = montantpatient - record.remise
            record.montantass = montantass

    def aannuler(self):
        self.write({'state':'aannuler'})
    def annuler(self):
        self.write({'state':'annule'})
        
    @api.depends('idpatient') 
    def get_assurance(self):
        for record in self:
            record.idassurance = record.idpatient.idassurance.id
            record.idsociete = record.idpatient.idsociete.id

    idpatient = fields.Many2one('clinic.patient', string='Patient', required=True)
    date = fields.Date('Date', required=True)
    name = fields.Char('Référence',copy=False, readonly=True, index=True, default='')
    montant = fields.Float('Montant', compute='get_montant', store=True,digits=(16,0))
    montantpatient = fields.Float('Part Patient Net', compute='get_montant', store=True,digits=(16,0))
    montantass = fields.Float('Part Assurance', compute='get_montant', store=True,digits=(16,0))
    remise = fields.Float('Remise',digits=(16,0))
    idassurance = fields.Many2one('clinic.assurance', string='Assurance', compute='get_assurance', store=True)
    idsociete = fields.Many2one('clinic.societe', string='Sociéte', compute='get_assurance', store=True)
    etatfact = fields.Selection([('facture','Facturée'),('afacturer','Non facturée')], string='Etat Facture', default = 'afacturer')
    ligne_facture = fields.One2many('clinic.facture.ligne','idfacture', string='Lignes de facture')
    state = fields.Selection([('brouillon','Brouillon'),('valide','Validé'),('aannuler','A annuler'),('annule','Annulé'),('reglep','Réglée patient'),('reglea','Réglée assurance'),('reglee','Réglée')], string='Etat', size=64, default='brouillon' ,track_visibility='onchange', readonly=True, required=True)


    
class clinic_facture_ligne(models.Model):
    _name = "clinic.facture.ligne"
    _description = "Lignes de facture"
   
    @api.depends('qte','pu','plafond')
    def get_montantl(self):
        for record in self:
            taux = self.env['clinic.tauxass'].search([('idpatient','=',record.idfacture.idpatient.id),('categorie','=',record.idarticle.categ_id.id)]).taux/100
            #record.montant = record.qte * record.pu
            #record.montantass = record.qte * record.pu * taux
            #record.montantpatient = record.qte * record.pu * (1-taux)
            if record.idarticle.standard_price != 0 and record.idfacture.idpatient.idassurance.name == 'MAADO':
               record.montant = record.qte * record.pu
               record.montantass = record.qte * record.plafond
               record.montantpatient = record.qte * (record.pu - record.plafond)
            else :
               record.montant = record.qte * record.pu
               record.montantass = record.qte * record.plafond * taux
               record.montantpatient = record.qte * (record.pu - record.plafond * taux )


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

    @api.onchange('pu')
    def onchange_pu(self):
        if self.idarticle.available_in_pos:
           for recf in self:
               recf.plafond = recf.pu
           return 
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
            
    idfacture = fields.Many2one('clinic.facture', string='Facture', required=True)
    idarticle = fields.Many2one('product.template', string='Article', required=True)
    idmedecin = fields.Many2one('clinic.medecin', string='Medecin')
    qte = fields.Float('Quantité', required=True, default=1.0,digits=(16,0))
    pu = fields.Float('Prix unitaire', required=True,digits=(16,0))
    plafond = fields.Float('Prix plafond', required=True,digits=(16,0))
    montant = fields.Float('Montant', compute='get_montantl',digits=(16,0))
    montantass = fields.Float('Montant assurance', compute='get_montantl',digits=(16,0))
    montantpatient = fields.Float('Montant patient', compute='get_montantl',digits=(16,0))


class clinic_reghospi(models.Model):
    _name = "clinic.reghospi"
    _description = "Reglement Hospi"

    def mtlettre(self,montant):
        return convlettres(montant)
    def validef(self):
        company_id = self.env.user.company_id
        for frais in self:
            if frais.name == '':
                frais.name = company_id.sequencecaisse.next_by_id()
        self.write({'state':'valide'})
        self.calcule_cash()
        if self.idfacture.state == 'valide':
           if self.idfacture.montantass != 0: 
              self.idfacture.state = 'reglep'
           else:
              self.idfacture.state = 'reglee' 
        if self.idfacture.state == 'reglea':
           self.idfacture.state = 'reglee'
        return {
        'context': self.env.context,
        'view_type': 'form',
        'view_mode': 'form',
        'res_model': 'clinic.reghospi',
        'res_id': self.id,
        'view_id': False,
        'type': 'ir.actions.act_window',
        'target': 'new',
    }
    def calcule_cash(self):
        bank_statements = [session.statement_ids for session in self.idreghospi if session.statement_ids]
        if not bank_statements:
                raise UserError(_("There is no cash register for this PoS Session"))
        for box in self:
            for record in bank_statements[0]:
                if not record.journal_id:
                    raise UserError(_("Please check that the field 'Journal' is set on the Bank Statement"))
                if not record.journal_id.company_id.transfer_account_id:
                    raise UserError(_("Please check that the field 'Transfer Account' is set on the company."))
                if box.montantcomp > 0:
                      box.idreghospi._create_bank_statement_line(record,self.montantcomp,'Hospitalisation',None,box.name)
                if box.montantremb > 0:
                      box.idreghospi._create_bank_statement_line(record,self.montantremb*-1,'Remboursement caution',None,box.name)
                for caut in self.caution:
                       caut.state = 'solde'

    def get_dateop(self):
        return fields.Date.to_string(datetime.now())
    
    @api.depends('idfacture')
    def get_facture(self):
        for record in self:
            record.idpatient = record.idfacture.idpatient.id
            record.idsociete = record.idfacture.idpatient.idsociete.id
            record.idassurance = record.idfacture.idpatient.idassurance.id
            record.montant = record.idfacture.montant
            record.montantpatient = record.idfacture.montantpatient
            record.montantass = record.idfacture.montantass
    @api.depends('caution','montantpatient')
    def get_montantcaution(self):
        for record in self:
            montantcaution = 0
            for recordfil in record.caution:
                montantcaution = montantcaution + recordfil.montant
            record.montantcaution = montantcaution
            if montantcaution > record.montantpatient:
               record.montantremb = montantcaution - record.montantpatient
               record.montantcomp = 0
            else:
               record.montantremb = 0
               record.montantcomp = record.montantpatient - montantcaution
    def aannuler(self):
        self.write({'state':'aannuler'})
        return {
        'context': self.env.context,
        'view_type': 'form',
        'view_mode': 'form',
        'res_model': 'clinic.reghospi',
        'res_id': self.id,
        'view_id': False,
        'type': 'ir.actions.act_window',
        'target': 'new',
    }
    def annuler(self):
        self.calcule_cash_annul()
        self.write({'state':'annule'})
        return {
        'context': self.env.context,
        'view_type': 'form',
        'view_mode': 'form',
        'res_model': 'clinic.reghospi',
        'res_id': self.id,
        'view_id': False,
        'type': 'ir.actions.act_window',
        'target': 'new',
    }
    def calcule_cash_annul(self):
        bank_statements = [session.statement_ids for session in self.idreghospi if session.statement_ids]
        if not bank_statements:
                raise UserError(_("There is no cash register for this PoS Session"))
        for box in self:
            for record in bank_statements[0]:
                if not record.journal_id:
                    raise UserError(_("Please check that the field 'Journal' is set on the Bank Statement"))
                if not record.journal_id.company_id.transfer_account_id:
                    raise UserError(_("Please check that the field 'Transfer Account' is set on the company."))
                if box.montantcomp > 0:
                      box.idreghospi._create_bank_statement_line(record,self.montantcomp*-1,'Annulation Hospitalisation '+self.name,None,box.name)
                if box.montantremb > 0:
                      box.idreghospi._create_bank_statement_line(record,self.montantremb,'Annulation Remboursement caution '+self.name,None,box.name)
                for caut in self.caution:
                       caut.state = 'valide'

    def revenir(self):
        self.write({'state':'valide'})
        return {
        'context': self.env.context,
        'view_type': 'form',
        'view_mode': 'form',
        'res_model': 'clinic.reghospi',
        'res_id': self.id,
        'view_id': False,
        'type': 'ir.actions.act_window',
        'target': 'new',
    }
    idreghospi = fields.Many2one('pos.session', string='Caution', required=True)
    name = fields.Char('Référence',copy=False, readonly=True, index=True, default='')
    idfacture = fields.Many2one('clinic.factureko', string='Facture', required=True, domain="[('state','in',('valide','reglea'))]")
    idpatient = fields.Many2one('clinic.patient', string='Patient', compute='get_facture')
    idassurance = fields.Many2one('clinic.assurance', string='Assurance', compute='get_facture')
    idsociete = fields.Many2one('clinic.societe', string='Société', compute='get_facture')
    date = fields.Date('Date', required=True, default=get_dateop, readonly=True)
    montant = fields.Float('Montant Facture', digits=(16,0), compute = 'get_facture', store=True)
    montantpatient = fields.Float('Montant Patient',digits=(16,0), compute = 'get_facture', store=True)
    montantass = fields.Float('Montant Assurance', digits=(16,0), compute = 'get_facture', store=True)
    caution = fields.Many2many('clinic.caution', string='Cautions')
    montantcomp = fields.Float('Montant complété', compute='get_montantcaution', store=True,digits=(16,0))
    montantremb = fields.Float('Montant remboursé', compute='get_montantcaution', store=True,digits=(16,0))
    montantcaution = fields.Float('Montant caution', compute='get_montantcaution', store=True,digits=(16,0))
    state = fields.Selection([('brouillon','Brouillon'),('valide','Validée'),('aannuler','A annuler'),('annule','Annulé')], string='Etat', size=64, default='brouillon' ,track_visibility='onchange', readonly=True, required=True)

class clinic_recugarde(models.Model):
    _name = "clinic.recugarde"
    _description = "Recus de garde"
    _rec_name = "numrecu"
    
    def validef(self):
        for frais in self:
            self.write({'state':'valide'})
            
    def get_dateop(self):
        return fields.Date.to_string(datetime.now())

    @api.depends('idpatient') 
    def get_assurance(self):
        for record in self:
            record.idassurance = record.idpatient.idassurance.id
            record.idsociete = record.idpatient.idsociete.id

    @api.depends('montantpatient','montantass')
    def get_montant(self):
        for record in self:
            record.montant = record.montantpatient + record.montantass
            
    date = fields.Date('Date', required=True, default=get_dateop)
    idpatient = fields.Many2one('clinic.patient', string='Patient', required=True)
    montant = fields.Float('Montant', compute='get_montant', store=True,digits=(16,0))
    montantpatient = fields.Float('Part Patient Net',digits=(16,0))
    montantass = fields.Float('Part Assurance',digits=(16,0))  
    idassurance = fields.Many2one('clinic.assurance', string='Assurance', compute='get_assurance', store=True)
    idsociete = fields.Many2one('clinic.societe', string='Sociéte', compute='get_assurance', store=True)
    numficheas = fields.Char('N° Fiche assurance')
    etatfact = fields.Selection([('facture','Facturée'),('afacturer','Non facturée')], string='Etat Facture', default = 'afacturer')
    numrecu = fields.Char('N° Reçu', required=True)
    state = fields.Selection([('brouillon','Brouillon'),('valide','Validé')], string='Etat', size=64, default='brouillon' ,track_visibility='onchange', readonly=True, required=True)

class clinic_reglement(models.Model):
    _name = "clinic.reglement"
    _description = "Reglement"

    @api.depends('idfactures.montant')
    def get_montantfact(self):
        for record in self:
            montantfact = 0
            for recordfil in record.idfactures:
                montantfact = montantfact + recordfil.montant
            record.montantfact = montantfact
    @api.depends('ligne_facture.montant','montant')
    def get_montantres(self):
        for record in self:
            montant = 0
            for recordfil in record.ligne_facture:
                montant = montant + recordfil.montant
            record.montantres = record.montant - montant
            #record.montantres = record.montant - record.montantfact
    def validereg(self):
        self.write({'state':'valide'})
    def lettrer(self):
        if self.montantres < self.montantfact:
           raise UserError('Le montant est insuffisant') 
        for record in self.idfactures:
            if record.state == 'valide':
               record.state = 'regle'
               record.idreglement = self.id
        self.idfactures = ''
    date = fields.Date('Date', required=True)
    idassurance = fields.Many2one('clinic.assurance', string='Assurance', required=True)
    idbanque = fields.Many2one('account.journal', string='Banque', required=True)
    ref = fields.Char('Référence', required=True)
    idfactures = fields.Many2many('clinic.factureas', string='Factures', domain="([('state','=','valide')])")
    montant = fields.Float('Montant Réglé', digits=(16,0), required=True)
    montantres = fields.Float('Montant résiduel', digits=(16,0), compute='get_montantres')
    montantfact = fields.Float('Montant Factures', digits=(16,0), compute='get_montantfact')
    ligne_facture = fields.One2many('clinic.factureas','idreglement','Factures réglés')
    state = fields.Selection([('brouillon','Brouillon'),('valide','Validé')], string='Etat', size=64, default='brouillon' ,track_visibility='onchange', readonly=True, required=True)
    
class clinic_medecin(models.Model):
    _name = "clinic.medecin"
    _description = "Medecin"
        
    name = fields.Char('Code', required=True)
    nom = fields.Char('Nom et prénoms', required=True)
    specialite = fields.Char('Spécialité', required=True)
    phone = fields.Char('N° Téléphone')
    ligne_consult = fields.One2many('clinic.opcaisse.ligne','idmedecin','Consultations')
    ligne_consulthospi = fields.One2many('clinic.facture.ligne','idmedecin','Consultations')