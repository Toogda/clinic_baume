# -*- coding: utf-8 -*-

import logging
from datetime import timedelta
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

class PosSession(models.Model):
    _name = 'pos.session'
    _inherit = 'pos.session'
   
    def reouvrir(self):
        for session in self:
            session.write({'state': 'opened'})

    @api.one
    def _create_bank_statement_line(self, record, montant, libelle, partenaire, reference):
        if record.state == 'confirm':
            raise UserError(_("You cannot put/take money in/out for a bank statement which is closed."))
        values = self._calculate_values_for_statement_line(record, montant, libelle, partenaire, reference)
        return record.write({'line_ids': [(0, False, values)]})
    @api.multi
    def _calculate_values_for_statement_line(self, record, montant, libelle, partenaire, reference):
        #if not record.journal_id.company_id.transfer_account_id:
        #    raise UserError(_("You should have defined an 'Internal Transfer Account' in your cash register's journal!"))
        return {
            'date': record.date,
            'statement_id': record.id,
            'journal_id': record.journal_id.id,
            'amount': montant or 0.0,
            'ref': reference or '',
            'partner_id': partenaire or '',
            'name': libelle,
        }

    @api.multi
    def action_pos_session_close(self):
        # Close CashBox
        for session in self:
            company_id = self.env.user.company_id
            ctx = dict(self.env.context, force_company=company_id, company_id=company_id)
            for st in session.statement_ids:
                if abs(st.difference) > st.journal_id.amount_authorized_diff:
                    # The pos manager can close statements with maximums.
                    if not self.user_has_groups("point_of_sale.group_pos_manager"):
                        raise UserError(_("Your ending balance is too different from the theoretical cash closing (%.2f), the maximum allowed is: %.2f. You can contact your manager to force it.") % (st.difference, st.journal_id.amount_authorized_diff))
                if (st.journal_id.type not in ['bank', 'cash']):
                    raise UserError(_("The journal type for your payment method should be bank or cash."))
                #st.with_context(ctx).sudo().button_confirm_bank()
                st.state = 'confirm'
        self.with_context(ctx)._confirm_orders()
        self.write({'state': 'closed'})
        return {
            'type': 'ir.actions.client',
            'name': 'Point of Sale Menu',
            'tag': 'reload',
            'params': {'menu_id': self.env.ref('point_of_sale.menu_point_root').id},
        }

    @api.multi
    def action_pos_session_closing_control(self):
        self._check_pos_session_balance()
        trouve = 0
        for record in self.ligne_opcaisse:
            if record.state == 'brouillon':
               trouve = 1
        for record in self.ligne_caution:
            if record.state == 'brouillon':
               trouve = 1
        #if trouve == 1:
        #   raise UserError('Vous devez valider toutes les transactions') 
        for session in self:
            session.write({'state': 'closing_control', 'stop_at': fields.Datetime.now()})
            if not session.config_id.cash_control:
                session.action_pos_session_close()

    def get_total(self):
        for record in self:
            jour = garde = caution = rembourse = transfert = 0
            for recordfilo in record.ligne_opcaisse:
                if recordfilo.state == 'valide':
                   jour = jour + recordfilo.montantpatient
                
            for recordfilh in record.ligne_reghospi:
                if recordfilh.state == 'valide':
                   jour = jour + recordfilh.montantcomp
            for recordfilg in record.ligne_recettegarde:
                if recordfilg.state == 'valide':
                   garde = garde + recordfilg.montant
            for recordfilc in record.ligne_caution:
                if recordfilc.state == 'valide' or recordfilc.state == 'solde':
                   if recordfilc.montant > 0 :
                      caution = caution +  recordfilc.montant
                   else:
                      rembourse = rembourse + recordfilc.montant
            for recordfilt in record.ligne_transfert:
                if recordfilt.state == 'valide':
                   transfert = transfert + recordfilt.montant
                
            for recordfilhr in record.ligne_reghospi:
                if recordfilhr.state == 'valide':
                   rembourse = rembourse + recordfilhr.montantremb
            record.total_jour = jour
            record.total_garde = garde
            record.total_caution = caution
            record.total_rembourse = rembourse
            record.total_transfert = transfert
            record.total_general = record.cash_register_balance_start + jour + garde + caution - rembourse - transfert
    total_jour = fields.Float('Total recette jour', digits=(16,0),compute = get_total)
    total_garde = fields.Float('Total garde', digits=(16,0),compute = get_total)
    total_caution = fields.Float('Total caution', digits=(16,0),compute = get_total)
    total_rembourse = fields.Float('Total rembourse', digits=(16,0),compute = get_total)
    total_transfert = fields.Float('Total transfert', digits=(16,0),compute = get_total)
    total_general = fields.Float('Total général', digits=(16,0),compute = get_total)
    ligne_opcaisse = fields.One2many('clinic.opcaisse','idopcaisse', string='Ligne operation caisse')
    ligne_caution = fields.One2many('clinic.caution','idcaution', string='Ligne caution')
    ligne_recettegarde = fields.One2many('clinic.recettegarde','idrecettegarde', string='Ligne recette garde')
    ligne_transfert = fields.One2many('clinic.transfert','idtransfert', string='Ligne transfert')
    ligne_reghospi = fields.One2many('clinic.reghospi','idreghospi', string='Ligne hospitalisation')


class clinic_transfert(models.Model):
    _name = 'clinic.transfert'
    _description = 'Transfert'

    def mtlettre(self,montant):
        return convlettres(montant)
    idtransfert = fields.Many2one('pos.session', string='Transfert', required=True)
    datetrans = fields.Date('Date de transfert')
    destination = fields.Many2one('account.journal', 'Destination', required=True, domain="[('type','=','bank')]")
    montant = fields.Float('Montant', required=True)
    ref = fields.Char('N° BV', required=True)
    name = fields.Char('Référence',copy=False, readonly=True, index=True, default='')
    caissier_id = fields.Many2one(
        'res.users', string='Caissier',
        required=True,
        index=True,
        readonly=True,
        default=lambda self: self.env.uid)
    tresorier_id = fields.Char('Réceptionniste')
    state = fields.Selection([('ouvert','Ouvert'),('verrouille','Vérouillé'),('valide','Validé'),('aannuler','A annuler'),('annule','Annulé')], string='Etat', size=64, default='ouvert' ,track_visibility='onchange', readonly=True, required=True)

    def vertransfert(self):
        for record in self:
            record.write({'state':'verrouille'})
        return {
        'context': self.env.context,
        'view_type': 'form',
        'view_mode': 'form',
        'res_model': 'clinic.transfert',
        'res_id': self.id,
        'view_id': False,
        'type': 'ir.actions.act_window',
        'target': 'new',
     }
    def devertransfert(self):
        for record in self:
            record.write({'state':'ouvert'})
        return {
        'context': self.env.context,
        'view_type': 'form',
        'view_mode': 'form',
        'res_model': 'clinic.transfert',
        'res_id': self.id,
        'view_id': False,
        'type': 'ir.actions.act_window',
        'target': 'new',
    }
    @api.multi
    def validetransfert(self):
        company_id = self.env.user.company_id
        for frais in self:
            if frais.name == '':
                frais.name = company_id.sequencetransfert.next_by_id()
        self.write({'state':'valide','datetrans':fields.Datetime.now()})
        self.calcule_cash()
        return {
        'context': self.env.context,
        'view_type': 'form',
        'view_mode': 'form',
        'res_model': 'clinic.transfert',
        'res_id': self.id,
        'view_id': False,
        'type': 'ir.actions.act_window',
        'target': 'new',
    }

    def calcule_cash(self):
        bank_statements = [session.statement_ids for session in self.idtransfert if session.statement_ids]
        if not bank_statements:
                raise UserError(_("There is no cash register for this PoS Session"))
        for box in self:
            for record in bank_statements[0]:
                if not record.journal_id:
                    raise UserError(_("Please check that the field 'Journal' is set on the Bank Statement"))
                if not record.journal_id.company_id.transfer_account_id:
                    raise UserError(_("Please check that the field 'Transfer Account' is set on the company."))
                box.idtransfert._create_bank_statement_line(record,self.montant*-1,'Transfert '+box.name+'/'+box.ref,None,None)

    def aannuler(self):
        self.write({'state':'aannuler'})
        return {
        'context': self.env.context,
        'view_type': 'form',
        'view_mode': 'form',
        'res_model': 'clinic.transfert',
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
        'res_model': 'clinic.transfert',
        'res_id': self.id,
        'view_id': False,
        'type': 'ir.actions.act_window',
        'target': 'new',
    }
    def calcule_cash_annul(self):
        bank_statements = [session.statement_ids for session in self.idtransfert if session.statement_ids]
        if not bank_statements:
                raise UserError(_("There is no cash register for this PoS Session"))
        for box in self:
            for record in bank_statements[0]:
                if not record.journal_id:
                    raise UserError(_("Please check that the field 'Journal' is set on the Bank Statement"))
                if not record.journal_id.company_id.transfer_account_id:
                    raise UserError(_("Please check that the field 'Transfer Account' is set on the company."))
                box.idtransfert._create_bank_statement_line(record,self.montant,'Annulation Transfert '+box.name+'/'+box.ref,None,None)
    def revenir(self):
        self.write({'state':'valide'})
        return {
        'context': self.env.context,
        'view_type': 'form',
        'view_mode': 'form',
        'res_model': 'clinic.transfert',
        'res_id': self.id,
        'view_id': False,
        'type': 'ir.actions.act_window',
        'target': 'new',
    }

class clinic_factureas(models.Model):
    _name = 'clinic.factureas'
    _description = 'facture assurance'

    def genrecapopcaisse(self):
        commands = []
        for record in self.env['clinic.opcaisse'].search([('idassurance','=',self.idassurance.id),('date','>=',self.debut),('date','<=',self.fin),('etatfact','=','afacturer')]):
            vals = {
                   'idopcaisse':record.id, 
                   'date':record.date,
                   'idpatient':record.idpatient.id,
                   'montant':record.montant,
                   'montantpatient':record.montantpatient,
                   'montantass':record.montantass,
                   'numficheas':record.numficheas,
                   }
            commands.append((0, False, vals))
        return commands
    def genrecapcatas(self):
        commands = []
        #result = self.env['clinic.opcaisse.ligne'].read_group([('idopcaisse.idassurance','=',self.idassurance.id),('idopcaisse.date','>=',self.debut),('idopcaisse.date','<=',self.fin),('idopcaisse.etatfact','=','afacturer')],('montant','montantpatient','montantass','categorie','idopcaisse','idarticle','qte','pu'),('montantass','categorie'))
        requete = "SELECT l.categorie, sum(l.montantass) as montantass " \
                  "FROM clinic_opcaisse_ligne l, clinic_assurance a, clinic_opcaisse o " \
                  "WHERE l.idopcaisse = o.id " \
                  "AND o.idassurance = a.id " \
                  "AND o.date BETWEEN '"+str(self.debut)+"' AND '"+str(self.fin)+"' " \
                  "AND o.etatfact = 'afacturer' " \
                  "AND a.id = "+str(self.idassurance.id)+" " \
                  "GROUP BY l.categorie"
        self.env.cr.execute(requete)
        result = self.env.cr.fetchall()
        for record in result:
            
            vals = {
                   'categorie':record[0],
                   'montant':record[1],
                   }
            #raise UserError(vals)
            commands.append((0, False, vals))
        return commands
    def genelementsfact(self):
        commands = [(2, line_id.id, False) for line_id in self.ligne_recapopcaisse]
        commandsr = [(2, line_id.id, False) for line_id in self.ligne_recapcatas]
        self.write({'ligne_recapopcaisse': commands})
        self.write({'ligne_recapcatas': commandsr})
        commands = self.genrecapopcaisse()
        self.write({'ligne_recapopcaisse': commands})
        commands = self.genrecapcatas()
        self.write({'ligne_recapcatas': commands})
        return True

    def genfacture(self):
        if len(self.ligne_recapopcaisse) == 0:
           raise UserError(_("Aucunne operation facturable!"))  
        for record in self.ligne_recapopcaisse:
            if record.idopcaisse.etatfact == 'facture':
               raise UserError(_("Il y a des operations deja facturees!")) 
        for record in self.ligne_recapopcaisse:
            record.idopcaisse.etatfact = 'facture'
        company_id = self.env.user.company_id
        for frais in self:
            if frais.name == '':
                frais.name = company_id.sequencefacture.next_by_id()
        self.write({'state':'valide'})

    @api.depends('ligne_recapcatas.montant')
    def get_montant(self):
        for record in self:
            montant = 0
            for recordfil in record.ligne_recapcatas:
                montant = montant + recordfil.montant
            record.montant = montant
    def delettrer(self):
        self.write({'state':'valide','idreglement':0})
    idassurance = fields.Many2one('clinic.assurance','Assurance', required=True)
    name = fields.Char('Référence',copy=False, readonly=True, index=True, default='')
    datefact = fields.Date('Date facturation',required=True)
    debut = fields.Date('Période du', required=True)
    fin = fields.Date('Au', required=True)
    montant = fields.Float('Montant', digits=(16,0), compute = 'get_montant', store = True)
    ligne_recapopcaisse = fields.One2many('clinic.recapopcaisse','idfacture','Lignes de recap')
    ligne_recapcatas = fields.One2many('clinic.recapcatas','idfacture','Lignes de recap categ')
    idreglement = fields.Many2one('clinic.reglement','Règlement')
    state = fields.Selection([('brouillon','Brouillon'),('valide','Validée'),('regle','Réglée')], string='Etat', size=64, default='brouillon' ,track_visibility='onchange', readonly=True, required=True)

class clinic_recapopcaisse(models.Model):
    _name = 'clinic.recapopcaisse'
    _description = 'Operations de caisse'

    idfacture = fields.Many2one('clinic.factureas', 'Facture', required=True)
    idopcaisse = fields.Many2one('clinic.opcaisse', 'opcaisse', required=True)
    date = fields.Date('Date', required=True)
    idpatient = fields.Many2one('clinic.patient', string='Patient', required=True)
    montant = fields.Float('Montant')
    montantpatient = fields.Float('Part Patient')
    montantass = fields.Float('Part Assurance')
    numficheas = fields.Char('N° Fiche assurance')

class clinic_recapcatas(models.Model):
    _name = 'clinic.recapcatas'
    _description = 'Assurance par categorie'

    idfacture = fields.Many2one('clinic.factureas', 'Facture', required=True)
    categorie = fields.Many2one('product.category',string='Type operation', required=True)
    montant = fields.Float('Montant')




