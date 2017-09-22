from odoo import models, fields, api
from odoo.exceptions import UserError
from odoo.tools.translate import _
from odoo.tools.misc import DEFAULT_SERVER_DATE_FORMAT
from odoo.addons.stock.models.stock_production_lot import ProductionLot
import datetime

class StockPicking(models.Model):
	_inherit = "stock.picking"

	def _create_lots_for_picking(self):
		Lot = self.env['stock.production.lot']
		for pack_op_lot in self.mapped('pack_operation_ids').mapped('pack_lot_ids'):
			if not pack_op_lot.lot_id:
				lot = Lot.create({'name': pack_op_lot.lot_name, 'product_id': pack_op_lot.operation_id.product_id.id,'life_date':pack_op_lot.life_date})
				pack_op_lot.write({'lot_id': lot.id})
		# TDE FIXME: this should not be done here
		self.mapped('pack_operation_ids').mapped('pack_lot_ids').filtered(lambda op_lot: op_lot.qty == 0.0).unlink()



class StockQuant(models.Model):
	_inherit = 'stock.quant'

	removal_date = fields.Date(related='lot_id.removal_date', store=True)
	life_date = fields.Date(related='lot_id.life_date', store=True)
	expiry_state = fields.Selection(
		selection=[('expired', 'Expired'),
				   ('alert', 'In alert'),
				   ('normal', 'Normal'),
				   ('to_remove', 'To remove'),
				   ('best_before', 'After the best before')],
		string="Expiry State",
		related="lot_id.expiry_state",
		store=True)

class StockPackOperationLot(models.Model):
	""" Adding Production Date"""

	_inherit = 'stock.pack.operation.lot'
	
	life_date = fields.Date(
		string='Expiry Date',
		default=lambda self :fields.Date.today(),
	)

class StockProductionLotInherit1(models.Model):
	_inherit = 'stock.production.lot'

	@api.one
	@api.constrains('removal_date', 'alert_date', 'life_date', 'use_date')
	def _check_dates(self):
		dates = filter(lambda x: x, [self.alert_date, self.removal_date,self.life_date])
		sort_dates = list(dates)
		sort_dates.sort()
		if dates != sort_dates:
			raise UserError(
				_('Dates must be: Alert Date < Removal Date < Expiry Date'))

   

	def _get_dates(self, product_id=None,life_date=None):
		"""Returns dates based on number of days configured in current lot's product."""
		mapped_fields = {
			#'life_date': 'life_time',
			'use_date': 'use_time',
			'removal_date': 'removal_time',
			'alert_date': 'alert_time'
		}
		res = dict.fromkeys(mapped_fields.keys(), False)
		product = self.env['product.product'].browse(product_id) or self.product_id
		if product:
			for field in mapped_fields.keys():
				duration = getattr(product, mapped_fields[field])
				if duration:
					ldate = life_date or self.life_date
					date = datetime.datetime.strptime(ldate,DEFAULT_SERVER_DATE_FORMAT) - datetime.timedelta(days=duration)
					res[field] = fields.Date.to_string(date)
		return res

	@api.one
	@api.depends('removal_date', 'alert_date', 'life_date', 'use_date')
	def _get_product_state(self):
		now = fields.Date.today()
		self.expiry_state = 'normal'
		if self.life_date and self.life_date < now:
			self.expiry_state = 'expired'
		elif (self.alert_date and self.removal_date and
				self.removal_date >= now > self.alert_date):
			self.expiry_state = 'alert'
		elif (self.removal_date and self.life_date and
				self.life_date >= now > self.removal_date):
			self.expiry_state = 'to_remove'

	expiry_state = fields.Selection(
		compute=_get_product_state,
		selection=[('expired', 'Expired'),
				   ('alert', 'In alert'),
				   ('normal', 'Normal'),
				   ('to_remove', 'To remove'),
				   ('best_before', 'After the best before')],
		string='Expiry state',store=True)


	life_date = fields.Date(string='Expiry Date',
		help='This is the date on which the goods with this Serial Number may become dangerous and must not be consumed.')
	use_date = fields.Date(string='Best before Date',
		help='This is the date on which the goods with this Serial Number start deteriorating, without being dangerous yet.')
	removal_date = fields.Date(string='Removal Date',
		help='This is the date on which the goods with this Serial Number should be removed from the stock.')
	alert_date = fields.Date(string='Alert Date',
		help="This is the date on which an alert should be notified about the goods with this Serial Number.")

	@api.model
	def create(self, vals):
		dates = self._get_dates(vals.get('product_id'),vals.get('life_date'))
		for d in dates.keys():
			if not vals.get(d):
				vals[d] = dates[d]
		return super(ProductionLot, self).create(vals)

	@api.onchange('life_date')
	def change_dates_pro(self):
		dates_dict = self._get_dates()
		for field, value in dates_dict.items():
			setattr(self, field, value)
