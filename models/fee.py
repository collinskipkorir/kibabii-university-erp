from odoo import models, fields, api
from odoo.exceptions import ValidationError


class UniversityFee(models.Model):
    _name = 'university.fee'
    _description = 'University Fee'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'

    name = fields.Char(
        string="Fee Description",
        required=True,
        tracking=True
    )

    student_id = fields.Many2one(
        'student.university',
        string="Student",
        required=True,
        ondelete='cascade'
    )

    amount = fields.Float(
        string="Total Fee",
        required=True
    )

    paid_amount = fields.Float(
        string="Amount Paid",
        default=0.0
    )

    university_id = fields.Many2one(
        'university.management',
        string='University Management',
        ondelete='cascade'
    )

    balance = fields.Float(
        string="Balance",
        compute="_compute_balance",
        store=True
    )

    payment_date = fields.Date(string="Payment Date")

    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('partial', 'Partially Paid'),
            ('paid', 'Paid')
        ],
        default='draft',
        string="Status",
        tracking=True
    )

    @api.depends('amount', 'paid_amount')
    def _compute_balance(self):
        for rec in self:
            rec.balance = rec.amount - rec.paid_amount

            if rec.paid_amount == 0:
                rec.state = 'draft'
            elif rec.paid_amount < rec.amount:
                rec.state = 'partial'
            else:
                rec.state = 'paid'

    @api.constrains('paid_amount')
    def _check_paid_amount(self):
        for rec in self:
            if rec.paid_amount < 0:
                raise ValidationError("Paid amount cannot be negative.")
            if rec.paid_amount > rec.amount:
                raise ValidationError("Paid amount cannot exceed total fee.")